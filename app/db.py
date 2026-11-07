from collections.abc import Iterator

from sqlmodel import Session, SQLModel, create_engine

from app.config import settings


def criar_engine(url: str):
    connect_args = {}
    if url.startswith("sqlite"):
        # Permite uso entre threads e espera o lock em vez de falhar na hora.
        connect_args = {"check_same_thread": False, "timeout": 30}
    return create_engine(url, connect_args=connect_args)


engine = criar_engine(settings.database_url)


def init_db(eng=None) -> None:
    # Importa os modelos para registrá-los no metadata antes do create_all.
    from app import models  # noqa: F401

    SQLModel.metadata.create_all(eng or engine)


def get_session() -> Iterator[Session]:
    with Session(engine) as session:
        yield session
