"""Monta os casos de uso para cada requisição (injeção de dependências do FastAPI).

É o único ponto da API que conhece a implementação concreta da persistência e da IA.
"""

from collections.abc import Callable, Iterator
from contextlib import AbstractContextManager, contextmanager
from functools import lru_cache

from fastapi import Depends
from sqlmodel import Session

from app.application.amostras_libras import ServicoAmostrasLibras
from app.application.atendimentos import ServicoAtendimento
from app.application.recepcao import ServicoRecepcao
from app.application.relatorios import ServicoRelatorio
from app.application.senhas import ServicoSenhas
from app.config import settings
from app.domain.assistente import AssistenteTriagem
from app.domain.repositorios import UnidadeDeTrabalho
from app.persistence.db import engine, get_session
from app.persistence.unidade_de_trabalho import UnidadeDeTrabalhoSql

AbrirUnidade = Callable[[], AbstractContextManager[UnidadeDeTrabalho]]


def unidade_de_trabalho(session: Session = Depends(get_session)) -> UnidadeDeTrabalho:
    return UnidadeDeTrabalhoSql(session)


def fabrica_de_unidades() -> AbrirUnidade:
    """Abre unidades de trabalho fora da requisição (o relatório é gerado depois da resposta)."""

    @contextmanager
    def abrir() -> Iterator[UnidadeDeTrabalho]:
        with Session(engine) as session:
            yield UnidadeDeTrabalhoSql(session)

    return abrir


@lru_cache
def _assistente_configurado(
    api_key: str, modelo: str, esforco_pergunta: str, esforco_relatorio: str
) -> AssistenteTriagem | None:
    if not api_key:
        return None
    from app.ia.gpt import AssistenteGPT

    return AssistenteGPT(
        api_key=api_key, modelo=modelo, esforco_pergunta=esforco_pergunta, esforco_relatorio=esforco_relatorio
    )


def assistente_triagem() -> AssistenteTriagem | None:
    """A LIA com IA, ou None se OPENAI_API_KEY não estiver configurada."""
    return _assistente_configurado(
        settings.openai_api_key.strip(),
        settings.ia_modelo.strip(),
        settings.ia_esforco_pergunta.strip(),
        settings.ia_esforco_relatorio.strip(),
    )


def servico_atendimento(
    uow: UnidadeDeTrabalho = Depends(unidade_de_trabalho),
    assistente: AssistenteTriagem | None = Depends(assistente_triagem),
) -> ServicoAtendimento:
    return ServicoAtendimento(uow, limiar_confianca=settings.limiar_confianca, assistente=assistente)


def servico_senhas(uow: UnidadeDeTrabalho = Depends(unidade_de_trabalho)) -> ServicoSenhas:
    return ServicoSenhas(uow)


def servico_recepcao(uow: UnidadeDeTrabalho = Depends(unidade_de_trabalho)) -> ServicoRecepcao:
    return ServicoRecepcao(uow)


def servico_relatorio(
    uow: UnidadeDeTrabalho = Depends(unidade_de_trabalho),
    assistente: AssistenteTriagem | None = Depends(assistente_triagem),
) -> ServicoRelatorio:
    return ServicoRelatorio(uow, assistente)


def servico_amostras_libras(uow: UnidadeDeTrabalho = Depends(unidade_de_trabalho)) -> ServicoAmostrasLibras:
    fontes = frozenset(f.strip() for f in settings.fontes_amostras_libras.split(",") if f.strip())
    return ServicoAmostrasLibras(uow, fontes_aceitas=fontes)
