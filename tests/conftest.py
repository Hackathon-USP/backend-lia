import os
from contextlib import contextmanager

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from app.api.dependencias import assistente_triagem, fabrica_de_unidades
from app.main import app
from app.persistence.db import criar_engine, get_session, init_db
from app.persistence.unidade_de_trabalho import UnidadeDeTrabalhoSql


@pytest.fixture
def engine():
    # TEST_DATABASE_URL=postgresql://... roda a mesma suíte num Postgres (banco descartável:
    # as tabelas são apagadas antes e depois de cada teste). Sem ela, SQLite em memória.
    url = os.environ.get("TEST_DATABASE_URL")
    if url:
        eng = criar_engine(url)
        SQLModel.metadata.drop_all(eng)
    else:
        eng = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    init_db(eng)
    yield eng
    if url:
        SQLModel.metadata.drop_all(eng)
    eng.dispose()


@pytest.fixture
def session(engine):
    with Session(engine) as s:
        yield s


@pytest.fixture
def uow(session):
    return UnidadeDeTrabalhoSql(session)


@pytest.fixture
def client(engine):
    def _session():
        with Session(engine) as s:
            yield s

    @contextmanager
    def _abrir_unidade():
        with Session(engine) as s:
            yield UnidadeDeTrabalhoSql(s)

    app.dependency_overrides[get_session] = _session
    app.dependency_overrides[fabrica_de_unidades] = lambda: _abrir_unidade
    # Sem IA por padrão, mesmo com OPENAI_API_KEY no ambiente: os testes nunca chamam a API.
    # Os testes da LIA trocam por um assistente falso com `usar_assistente`.
    app.dependency_overrides[assistente_triagem] = lambda: None
    # Sem `with`: não dispara o lifespan, que criaria o banco real (totem.db).
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture
def usar_assistente(client):
    """Liga um assistente (falso) na API: `usar_assistente(meu_assistente)`."""

    def _usar(assistente):
        app.dependency_overrides[assistente_triagem] = lambda: assistente
        return assistente

    return _usar
