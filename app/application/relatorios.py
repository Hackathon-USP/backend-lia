"""Caso de uso do relatório da triagem: escrever (com IA ou por regras) e consultar.

O relatório sai logo depois que o atendimento é finalizado, sem fazer o paciente
esperar (a API dispara a geração depois de devolver a senha). A recepção também
pode pedir para gerar de novo.
"""

import logging
from datetime import datetime

from app.application.relogio import agora_local
from app.domain.assistente import AssistenteIndisponivel, AssistenteTriagem
from app.domain.entidades import RelatorioTriagem
from app.domain.erros import AtendimentoNaoEncontrado, RelatorioIndisponivel
from app.domain.relatorio import ConteudoRelatorio, ContextoTriagem, montar_contexto, relatorio_por_regras
from app.domain.repositorios import UnidadeDeTrabalho

logger = logging.getLogger(__name__)


class ServicoRelatorio:
    def __init__(self, uow: UnidadeDeTrabalho, assistente: AssistenteTriagem | None = None):
        self.uow = uow
        self.assistente = assistente  # None = relatório só por regras

    def obter(self, atendimento_id: int) -> RelatorioTriagem | None:
        return self.uow.relatorios.obter(atendimento_id)

    def _escrever(self, atendimento_id: int, contexto: ContextoTriagem) -> tuple[ConteudoRelatorio, str | None]:
        """(conteúdo, modelo usado). Sem IA, ou se ela falhar, o relatório sai por regras."""
        if self.assistente is not None:
            try:
                return self.assistente.escrever_relatorio(contexto), self.assistente.modelo
            except AssistenteIndisponivel as erro:
                logger.warning("Atendimento %s: relatório por regras (%s)", atendimento_id, erro)
        return relatorio_por_regras(contexto), None

    def gerar(self, atendimento_id: int, agora: datetime | None = None) -> RelatorioTriagem:
        """Escreve (ou reescreve) o relatório de um atendimento finalizado."""
        atendimento = self.uow.atendimentos.obter(atendimento_id)
        if atendimento is None:
            raise AtendimentoNaoEncontrado
        if not atendimento.finalizado:
            raise RelatorioIndisponivel
        lia = self.uow.perguntas_da_lia.obter(atendimento_id)
        extras = lia.lista if lia else ()
        contexto = montar_contexto(atendimento.modo, atendimento.respostas, atendimento.canais, extras)

        conteudo, modelo = self._escrever(atendimento_id, contexto)
        relatorio = RelatorioTriagem.criar(atendimento, conteudo, agora or agora_local(), modelo)
        relatorio = self.uow.relatorios.salvar(relatorio)
        self.uow.commit()
        return relatorio
