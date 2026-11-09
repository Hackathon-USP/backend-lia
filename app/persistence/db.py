"""Conexão com o banco: engine, criação das tabelas e sessão por requisição."""

from collections.abc import Iterator

from sqlalchemy import Engine
from sqlmodel import Session, SQLModel, create_engine

from app.config import settings


def normalizar_url(url: str) -> str:
    """Usa o driver psycopg (v3) nas URLs de Postgres.

    O Render (e outros provedores) entregam `postgres://...` ou `postgresql://...`; o
    SQLAlchemy não aceita o primeiro e, no segundo, procuraria o psycopg2.
    """
    url = url.strip()
    for prefixo in ("postgres://", "postgresql://"):
        if url.startswith(prefixo):
            return "postgresql+psycopg://" + url[len(prefixo) :]
    return url


def criar_engine(url: str) -> Engine:
    url = normalizar_url(url)
    if url.startswith("sqlite"):
        # Permite uso entre threads e espera o lock em vez de falhar na hora.
        return create_engine(url, connect_args={"check_same_thread": False, "timeout": 30})
    # Testa a conexão antes de usar: o Postgres do Render fecha conexões paradas.
    return create_engine(url, pool_pre_ping=True)


engine = criar_engine(settings.database_url)


def init_db(eng: Engine | None = None) -> None:
    # Importa as tabelas para registrá-las no metadata antes do create_all.
    from app.persistence import tabelas  # noqa: F401

    SQLModel.metadata.create_all(eng or engine)


def get_session() -> Iterator[Session]:
    with Session(engine) as session:
        yield session
