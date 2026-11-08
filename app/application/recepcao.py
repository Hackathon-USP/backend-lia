"""Casos de uso da tela da recepção: fila do dia, chamada de senhas e consulta de atendimentos."""

from dataclasses import dataclass
from datetime import date, datetime

from app.application.relogio import agora_local, dia_local
from app.application.senhas import ServicoSenhas
from app.domain.entidades import Atendimento, Identificacao, Queixa, Senha
from app.domain.enums import ModoAcessibilidade, StatusAtendimento, StatusSenha
from app.domain.erros import AtendimentoNaoEncontrado, FilaVazia
from app.domain.identificacao import apenas_digitos
from app.domain.repositorios import UnidadeDeTrabalho
from app.domain.triagem import POR_ID, posicao_no_fluxo


@dataclass
class SenhaNaFila:
    senha: Senha
    atendimento: Atendimento | None  # None para senhas emitidas direto em POST /senhas
    identificacao: Identificacao | None


@dataclass
class AtendimentoListado:
    atendimento: Atendimento
    senha: Senha | None
    identificacao: Identificacao | None


@dataclass
class RespostaRotulada:
    pergunta_id: str
    pergunta: str
    valor: object
    resposta: str
    canal: str | None


@dataclass
class DetalheAtendimento(AtendimentoListado):
    queixa: Queixa | None
    respostas: list[RespostaRotulada]


def _rotular(atendimento: Atendimento, pergunta_id: str, valor: object) -> RespostaRotulada:
    pergunta = POR_ID.get(pergunta_id)
    return RespostaRotulada(
        pergunta_id=pergunta_id,
        pergunta=pergunta.texto if pergunta else pergunta_id,
        valor=valor,
        resposta=pergunta.rotulo_de(valor) if pergunta else str(valor),
        canal=atendimento.canais.get(pergunta_id),
    )


def rotular_respostas(atendimento: Atendimento) -> list[RespostaRotulada]:
    """Respostas na ordem das perguntas, com o texto legível de cada opção."""
    itens = [_rotular(atendimento, pid, valor) for pid, valor in atendimento.respostas.items()]
    return sorted(itens, key=lambda item: posicao_no_fluxo(item.pergunta_id))


class ServicoRecepcao:
    def __init__(self, uow: UnidadeDeTrabalho):
        self.uow = uow

    # --- Fila -----------------------------------------------------------------

    def listar_fila(self, data_ref: date | None = None, status: StatusSenha | None = None) -> list[SenhaNaFila]:
        """Senhas do dia na ordem de chamada."""
        data_ref = data_ref or agora_local().date()
        senhas = sorted(self.uow.senhas.listar_do_dia(data_ref, status), key=lambda s: s.ordem_na_fila)
        atendimento_da_senha = self.uow.atendimentos.por_senhas([s.id for s in senhas])
        identificacoes = self.uow.identificacoes.por_atendimentos(
            [a.id for a in atendimento_da_senha.values()]
        )
        itens = []
        for senha in senhas:
            atendimento = atendimento_da_senha.get(senha.id)
            identificacao = identificacoes.get(atendimento.id) if atendimento else None
            itens.append(SenhaNaFila(senha, atendimento, identificacao))
        return itens

    def chamar_proxima(self, agora: datetime | None = None) -> SenhaNaFila:
        """Passa a próxima senha aguardando do dia para `em_atendimento`. Levanta FilaVazia."""
        data_ref = (agora or agora_local()).date()
        for item in self.listar_fila(data_ref, StatusSenha.aguardando):
            conseguiu = self.uow.senhas.tirar_da_espera(item.senha, StatusSenha.em_atendimento)
            self.uow.commit()
            if conseguiu:
                return item
            # Outro guichê chamou esta senha no meio do caminho: tenta a seguinte.
        raise FilaVazia

    def atualizar_status_senha(
        self, codigo: str, novo_status: StatusSenha, agora: datetime | None = None
    ) -> Senha:
        senha = ServicoSenhas(self.uow).obter_do_dia(codigo, agora)
        senha.status = novo_status
        senha = self.uow.senhas.salvar(senha)
        self.uow.commit()
        return senha

    # --- Atendimentos ---------------------------------------------------------

    def listar_atendimentos(
        self,
        data_ref: date | None = None,
        status: StatusAtendimento | None = None,
        modo: ModoAcessibilidade | None = None,
        cpf: str | None = None,
    ) -> list[AtendimentoListado]:
        """Mais recentes primeiro. `cpf` aceita máscara; um CPF que não existe só devolve lista vazia."""
        atendimentos = self.uow.atendimentos.listar(
            status, modo, apenas_digitos(cpf) if cpf is not None else None
        )
        if data_ref is not None:
            atendimentos = [a for a in atendimentos if dia_local(a.criado_em) == data_ref]
        senhas = self.uow.senhas.por_ids([a.senha_id for a in atendimentos if a.senha_id is not None])
        identificacoes = self.uow.identificacoes.por_atendimentos([a.id for a in atendimentos])
        return [
            AtendimentoListado(a, senhas.get(a.senha_id), identificacoes.get(a.id))
            for a in atendimentos
        ]

    def detalhar_atendimento(self, atendimento_id: int) -> DetalheAtendimento:
        atendimento = self.uow.atendimentos.obter(atendimento_id)
        if atendimento is None:
            raise AtendimentoNaoEncontrado
        return DetalheAtendimento(
            atendimento=atendimento,
            senha=self.uow.senhas.obter(atendimento.senha_id) if atendimento.senha_id else None,
            identificacao=self.uow.identificacoes.obter(atendimento_id),
            queixa=self.uow.queixas.do_atendimento(atendimento_id),
            respostas=rotular_respostas(atendimento),
        )
