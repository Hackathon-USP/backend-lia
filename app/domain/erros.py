"""Erros de negócio do totem.

Não sabem nada de HTTP: a camada `api` decide o status de cada família de erro
(NaoEncontrado, Conflito, DadosInvalidos) e devolve `mensagem` ao front.
"""


class ErroDeNegocio(Exception):
    mensagem_padrao: str = "Operação inválida"

    def __init__(self, mensagem: str | None = None):
        super().__init__(mensagem or self.mensagem_padrao)


# --- Recurso inexistente ------------------------------------------------------


class NaoEncontrado(ErroDeNegocio):
    pass


class AtendimentoNaoEncontrado(NaoEncontrado):
    mensagem_padrao = "Atendimento não encontrado"


class SenhaNaoEncontrada(NaoEncontrado):
    mensagem_padrao = "Senha não encontrada hoje"


class FilaVazia(NaoEncontrado):
    mensagem_padrao = "Fila vazia"


# --- Estado não permite a operação --------------------------------------------


class Conflito(ErroDeNegocio):
    pass


class AtendimentoJaFinalizado(Conflito):
    mensagem_padrao = "Atendimento já finalizado"


class TriagemIncompleta(Conflito):
    mensagem_padrao = "Ainda há perguntas sem resposta"


class IdentificacaoPendente(Conflito):
    mensagem_padrao = "Informe nome e CPF antes de finalizar"


class RelatorioIndisponivel(Conflito):
    mensagem_padrao = "O relatório sai depois que a triagem é finalizada"


# --- Dado enviado não passa na validação --------------------------------------


class DadosInvalidos(ErroDeNegocio, ValueError):
    pass


class RespostaInvalida(DadosInvalidos):
    pass


class IdentificacaoInvalida(DadosInvalidos):
    pass
