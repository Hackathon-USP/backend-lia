"""Entidades do totem. Objetos Python puros: não sabem como são gravados."""

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any

from app.domain import resumo, triagem
from app.domain.enums import ModoAcessibilidade, StatusAtendimento, StatusSenha, TipoSenha
from app.domain.erros import AtendimentoJaFinalizado, RespostaInvalida
from app.domain.identificacao import normalizar_cpf, normalizar_nome

PREFIXOS = {TipoSenha.normal: "N", TipoSenha.preferencial: "P"}
CANAIS_COM_RECONHECIMENTO = (ModoAcessibilidade.libras, ModoAcessibilidade.voz)
_ORDEM_STATUS = {StatusSenha.aguardando: 0, StatusSenha.em_atendimento: 1, StatusSenha.finalizada: 2}


# --- Senha --------------------------------------------------------------------


@dataclass
class Senha:
    codigo: str  # ex.: "P012" — único dentro do dia
    tipo: TipoSenha
    numero: int
    data_ref: date  # dia (no fuso local) em que a senha foi emitida
    criada_em: datetime
    status: StatusSenha = StatusSenha.aguardando
    id: int | None = None

    @classmethod
    def emitir(cls, tipo: TipoSenha, numero: int, agora: datetime) -> "Senha":
        return cls(
            codigo=f"{PREFIXOS[tipo]}{numero:03d}",
            tipo=tipo,
            numero=numero,
            data_ref=agora.date(),
            criada_em=agora,
        )

    @property
    def preferencial(self) -> bool:
        return self.tipo == TipoSenha.preferencial

    @property
    def ordem_na_fila(self) -> tuple:
        """Aguardando primeiro; dentro dele, preferenciais (Lei 10.048/2000) e depois as mais antigas."""
        return (_ORDEM_STATUS[self.status], not self.preferencial, self.criada_em, self.numero)


# --- Atendimento --------------------------------------------------------------


@dataclass
class Atendimento:
    modo: ModoAcessibilidade
    consentimento_em: datetime
    criado_em: datetime
    respostas: dict[str, Any] = field(default_factory=dict)  # {pergunta_id: valor}
    canais: dict[str, str] = field(default_factory=dict)  # {pergunta_id: canal da resposta}
    status: StatusAtendimento = StatusAtendimento.em_andamento
    senha_id: int | None = None
    resumo: str | None = None
    alertas: list[str] = field(default_factory=list)
    finalizado_em: datetime | None = None
    id: int | None = None

    @classmethod
    def iniciar(cls, modo: ModoAcessibilidade, agora: datetime) -> "Atendimento":
        """Só existe atendimento depois do consentimento, por isso ele é registrado agora."""
        return cls(modo=modo, consentimento_em=agora, criado_em=agora)

    @property
    def finalizado(self) -> bool:
        return self.status == StatusAtendimento.finalizado

    def garantir_em_andamento(self) -> None:
        if self.finalizado:
            raise AtendimentoJaFinalizado

    def proxima_pergunta(self) -> triagem.Pergunta | None:
        if self.finalizado:
            return None
        return triagem.proxima_pergunta(self.respostas, self.modo)

    def _pergunta_esperada(self, pergunta_id: str) -> triagem.Pergunta:
        esperada = self.proxima_pergunta()
        if esperada is None:
            raise RespostaInvalida("A triagem já terminou; finalize o atendimento")
        if pergunta_id != esperada.id:
            raise RespostaInvalida(f"Pergunta esperada agora: {esperada.id}")
        return esperada

    def responder(
        self,
        pergunta_id: str,
        valor: Any,
        canal: ModoAcessibilidade | None,
        confianca: float | None,
        limiar_confianca: float,
    ) -> bool:
        """Registra a resposta da pergunta atual. Devolve False se o totem deve pedir de novo.

        Pedir de novo (nada é gravado) acontece quando o reconhecimento de Libras/voz
        vem com confiança baixa ou com um sinal que não corresponde a nenhuma opção.
        Pelo toque, um valor inválido é erro do front e levanta RespostaInvalida.
        """
        self.garantir_em_andamento()
        pergunta = self._pergunta_esperada(pergunta_id)

        canal = canal or self.modo
        veio_por_reconhecimento = canal in CANAIS_COM_RECONHECIMENTO
        confianca_baixa = confianca is not None and confianca < limiar_confianca
        if veio_por_reconhecimento and confianca_baixa:
            return False
        try:
            valor_gravado = triagem.validar_valor(pergunta, valor)
        except RespostaInvalida:
            if veio_por_reconhecimento:
                return False
            raise

        self.respostas = {**self.respostas, pergunta_id: valor_gravado}
        self.canais = {**self.canais, pergunta_id: canal.value}
        return True

    def voltar_para(self, pergunta_id: str) -> None:
        """Apaga a resposta de `pergunta_id` e as de todas as perguntas depois dela,
        para o paciente responder de novo a partir dali (as seguintes dependem desta)."""
        self.garantir_em_andamento()
        if pergunta_id not in self.respostas:
            raise RespostaInvalida(f"Pergunta ainda não respondida: {pergunta_id}")
        inicio = triagem.posicao_no_fluxo(pergunta_id)
        mantidas = [pid for pid in self.respostas if triagem.posicao_no_fluxo(pid) < inicio]
        self.respostas = {pid: self.respostas[pid] for pid in mantidas}
        self.canais = {pid: canal for pid, canal in self.canais.items() if pid in mantidas}

    def tipo_de_senha(self) -> TipoSenha:
        """Libras e voz são sempre preferenciais (Lei 10.048/2000); no toque, quem declarou."""
        usa_recurso_de_acessibilidade = self.modo != ModoAcessibilidade.toque
        declarou_prioridade = self.respostas.get("prioridade") == "sim"
        if usa_recurso_de_acessibilidade or declarou_prioridade:
            return TipoSenha.preferencial
        return TipoSenha.normal

    def concluir(self, senha: "Senha", nome_paciente: str, agora: datetime) -> None:
        """Vincula a senha, gera alertas e resumo para a recepção e encerra a triagem."""
        self.alertas = resumo.gerar_alertas(self.respostas)
        self.resumo = resumo.gerar_resumo(
            senha.codigo, self.modo, self.respostas, self.alertas, nome=nome_paciente
        )
        self.senha_id = senha.id
        self.status = StatusAtendimento.finalizado
        self.finalizado_em = agora


# --- Identificação ------------------------------------------------------------


@dataclass
class Identificacao:
    atendimento_id: int
    nome: str
    cpf: str  # só os 11 dígitos
    criada_em: datetime

    @classmethod
    def criar(cls, atendimento_id: int, nome: str, cpf: str, agora: datetime) -> "Identificacao":
        """Valida e normaliza. Levanta IdentificacaoInvalida se nome ou CPF forem inválidos."""
        return cls(atendimento_id, normalizar_nome(nome), normalizar_cpf(cpf), agora)

    def corrigir(self, nome: str, cpf: str) -> None:
        self.nome, self.cpf = normalizar_nome(nome), normalizar_cpf(cpf)


# --- Queixa -------------------------------------------------------------------


@dataclass
class Queixa:
    atendimento_id: int
    sintoma: str
    criada_em: datetime
    local: str | None = None
    intensidade: int | None = None
    desde_quando: str | None = None
    id: int | None = None

    @classmethod
    def das_respostas(cls, atendimento: Atendimento, agora: datetime) -> "Queixa | None":
        """Queixa estruturada a partir da triagem; None se o paciente não relatou sintoma."""
        respostas = atendimento.respostas
        if "sintoma" not in respostas:
            return None
        return cls(
            atendimento_id=atendimento.id,
            sintoma=respostas["sintoma"],
            local=respostas.get("local_dor"),
            intensidade=respostas.get("intensidade"),
            desde_quando=respostas.get("desde_quando"),
            criada_em=agora,
        )
