"""Monta os casos de uso para cada requisição (injeção de dependências do FastAPI).

É o único ponto da API que conhece a implementação concreta da persistência.
"""

from fastapi import Depends
from sqlmodel import Session

from app.application.amostras_libras import ServicoAmostrasLibras
from app.application.atendimentos import ServicoAtendimento
from app.application.recepcao import ServicoRecepcao
from app.application.senhas import ServicoSenhas
from app.config import settings
from app.domain.repositorios import UnidadeDeTrabalho
from app.persistence.db import get_session
from app.persistence.unidade_de_trabalho import UnidadeDeTrabalhoSql


def unidade_de_trabalho(session: Session = Depends(get_session)) -> UnidadeDeTrabalho:
    return UnidadeDeTrabalhoSql(session)


def servico_atendimento(uow: UnidadeDeTrabalho = Depends(unidade_de_trabalho)) -> ServicoAtendimento:
    return ServicoAtendimento(uow, limiar_confianca=settings.limiar_confianca)


def servico_senhas(uow: UnidadeDeTrabalho = Depends(unidade_de_trabalho)) -> ServicoSenhas:
    return ServicoSenhas(uow)


def servico_recepcao(uow: UnidadeDeTrabalho = Depends(unidade_de_trabalho)) -> ServicoRecepcao:
    return ServicoRecepcao(uow)


def servico_amostras_libras(uow: UnidadeDeTrabalho = Depends(unidade_de_trabalho)) -> ServicoAmostrasLibras:
    fontes = frozenset(f.strip() for f in settings.fontes_amostras_libras.split(",") if f.strip())
    return ServicoAmostrasLibras(uow, fontes_aceitas=fontes)
