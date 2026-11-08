"""Contrato da IA da LIA: o que a triagem pede a ela.

A implementação com o GPT (OpenAI) fica em `app.ia`. Os casos de uso dependem só deste
protocolo, então a triagem funciona igual sem IA (nos testes, ou sem a chave) e
trocar de modelo/fornecedor não mexe em regra de negócio.
"""

from typing import Protocol

from app.domain.perguntas_da_lia import PerguntaSugerida
from app.domain.relatorio import ConteudoRelatorio, ContextoTriagem


class AssistenteIndisponivel(Exception):
    """A IA não respondeu a tempo, deu erro, recusou ou respondeu algo inutilizável."""


class AssistenteTriagem(Protocol):
    modelo: str  # registrado no relatório (ex.: "gpt-6-luna")

    def sugerir_pergunta(self, contexto: ContextoTriagem) -> PerguntaSugerida | None:
        """Próxima pergunta complementar, ou None se não precisa perguntar mais.

        Levanta AssistenteIndisponivel em caso de falha.
        """

    def escrever_relatorio(self, contexto: ContextoTriagem) -> ConteudoRelatorio:
        """Relatório da triagem para a recepção. Levanta AssistenteIndisponivel em caso de falha."""
