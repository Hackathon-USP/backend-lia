"""Entidades do totem. Objetos Python puros: não sabem como são gravados."""

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any

from app.domain import perguntas_da_lia, resumo, triagem
from app.domain.enums import ModoAcessibilidade, StatusAtendimento, StatusSenha, TipoSenha
from app.domain.erros import AtendimentoJaFinalizado, RespostaInvalida
from app.domain.identificacao import normalizar_cpf, normalizar_nome
from app.domain.relatorio import ConteudoRelatorio, juntar_alertas

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

    def proxima_pergunta(self, extras: Sequence[triagem.Pergunta] = ()) -> triagem.Pergunta | None:
        """`extras` são as perguntas da LIA deste atendimento, feitas depois das fixas."""
        if self.finalizado:
            return None
        return triagem.proxima_pergunta(self.respostas, self.modo, extras)

    def _pergunta_esperada(self, pergunta_id: str, extras: Sequence[triagem.Pergunta]) -> triagem.Pergunta:
        esperada = self.proxima_pergunta(extras)
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
        extras: Sequence[triagem.Pergunta] = (),
    ) -> bool:
        """Registra a resposta da pergunta atual. Devolve False se o totem deve pedir de novo.

        Pedir de novo (nada é gravado) acontece quando o reconhecimento de Libras/voz
        vem com confiança baixa ou com um sinal que não corresponde a nenhuma opção.
        Pelo toque, um valor inválido é erro do front e levanta RespostaInvalida.
        """
        self.garantir_em_andamento()
        pergunta = self._pergunta_esperada(pergunta_id, extras)

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

    def voltar_para(self, pergunta_id: str, extras: Sequence[triagem.Pergunta] = ()) -> None:
        """Apaga a resposta de `pergunta_id` e as de todas as perguntas depois dela,
        para o paciente responder de novo a partir dali (as seguintes dependem desta)."""
        self.garantir_em_andamento()
        if pergunta_id not in self.respostas:
            raise RespostaInvalida(f"Pergunta ainda não respondida: {pergunta_id}")
        inicio = triagem.posicao_no_fluxo(pergunta_id, extras)
        mantidas = [pid for pid in self.respostas if triagem.posicao_no_fluxo(pid, extras) < inicio]
        self.respostas = {pid: self.respostas[pid] for pid in mantidas}
        self.canais = {pid: canal for pid, canal in self.canais.items() if pid in mantidas}

    def tipo_de_senha(self) -> TipoSenha:
        """Libras e voz são sempre preferenciais (Lei 10.048/2000); no toque, quem declarou."""
        usa_recurso_de_acessibilidade = self.modo != ModoAcessibilidade.toque
        declarou_prioridade = self.respostas.get("prioridade") == "sim"
        if usa_recurso_de_acessibilidade or declarou_prioridade:
            return TipoSenha.preferencial
        return TipoSenha.normal

    def concluir(
        self, senha: "Senha", nome_paciente: str, agora: datetime, extras: Sequence[triagem.Pergunta] = ()
    ) -> None:
        """Vincula a senha, gera alertas e resumo para a recepção e encerra a triagem."""
        self.alertas = resumo.gerar_alertas(self.respostas, extras)
        self.resumo = resumo.gerar_resumo(
            senha.codigo, self.modo, self.respostas, self.alertas, nome=nome_paciente, extras=extras
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


# --- Perguntas da LIA ---------------------------------------------------------


@dataclass
class PerguntasDaLia:
    """Perguntas complementares que a LIA (IA) criou para este atendimento, na ordem."""

    atendimento_id: int
    perguntas: list[dict[str, Any]] = field(default_factory=list)  # `Pergunta` serializada (coluna JSON)
    # A LIA não tem mais o que perguntar (ela decidiu, chegou ao limite ou a IA não respondeu).
    encerradas: bool = False

    @property
    def lista(self) -> tuple[triagem.Pergunta, ...]:
        return tuple(perguntas_da_lia.de_dict(p) for p in self.perguntas)

    def adicionar(self, pergunta: triagem.Pergunta) -> None:
        self.perguntas = [*self.perguntas, perguntas_da_lia.para_dict(pergunta)]

    def encerrar(self) -> None:
        self.encerradas = True

    def recomecar_a_partir_de(self, pergunta_id: str) -> None:
        """O paciente vai corrigir `pergunta_id`: as perguntas da LIA feitas depois dela
        partiram da resposta antiga e saem (ela mesma fica, para ser respondida de novo)."""
        ids = [p["id"] for p in self.perguntas]
        manter = ids.index(pergunta_id) + 1 if pergunta_id in ids else 0
        self.perguntas = self.perguntas[:manter]
        self.encerradas = False


# --- Relatório da triagem -----------------------------------------------------


@dataclass
class RelatorioTriagem:
    """Relatório para a recepção e a enfermagem, gerado ao finalizar a triagem."""

    atendimento_id: int
    queixa_principal: str
    resumo: str
    sinais_de_alerta: list[str]
    pontos_a_confirmar: list[str]
    orientacao_recepcao: str
    gerado_por: str  # "ia" ou "regras"
    gerado_em: datetime
    modelo: str | None = None  # modelo de IA usado, quando gerado_por == "ia"

    @classmethod
    def criar(
        cls,
        atendimento: Atendimento,
        conteudo: ConteudoRelatorio,
        agora: datetime,
        modelo: str | None = None,
    ) -> "RelatorioTriagem":
        """Os alertas do atendimento (regras fixas e perguntas da LIA) nunca ficam de fora."""
        return cls(
            atendimento_id=atendimento.id,
            queixa_principal=conteudo.queixa_principal.strip(),
            resumo=conteudo.resumo.strip(),
            sinais_de_alerta=juntar_alertas(atendimento.alertas, conteudo.sinais_de_alerta),
            pontos_a_confirmar=[p.strip() for p in conteudo.pontos_a_confirmar if p.strip()],
            orientacao_recepcao=conteudo.orientacao_recepcao.strip(),
            gerado_por="ia" if modelo else "regras",
            gerado_em=agora,
            modelo=modelo,
        )
