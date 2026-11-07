import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, create_engine

from app.db import get_session, init_db
from app.main import app


@pytest.fixture
def engine():
    eng = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    init_db(eng)
    yield eng
    eng.dispose()


@pytest.fixture
def session(engine):
    with Session(engine) as s:
        yield s


@pytest.fixture
def client(engine):
    def _session():
        with Session(engine) as s:
            yield s

    app.dependency_overrides[get_session] = _session
    # Sem `with`: não dispara o lifespan, que criaria o banco real (totem.db).
    yield TestClient(app)
    app.dependency_overrides.clear()
