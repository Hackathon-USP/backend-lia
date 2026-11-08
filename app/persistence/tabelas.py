"""Tabelas do banco (SQLModel). Só a camada de persistência conhece estas classes.

Os nomes das tabelas são fixos (`__tablename__`) para continuar compatível com
bancos criados antes da separação em camadas.
"""

from datetime import date, datetime
from typing import Any

from sqlalchemy import JSON, Column, UniqueConstraint
from sqlmodel import Field, SQLModel

from app.domain.enums import ModoAcessibilidade, StatusAtendimento, StatusSenha, TipoSenha


class SenhaTabela(SQLModel, table=True):
    __tablename__ = "senha"
    __table_args__ = (UniqueConstraint("data_ref", "codigo"),)

    id: int | None = Field(default=None, primary_key=True)
    codigo: str = Field(index=True)
    tipo: TipoSenha
    numero: int
    data_ref: date = Field(index=True)
    status: StatusSenha = StatusSenha.aguardando
    criada_em: datetime


class ContadorSenhaTabela(SQLModel, table=True):
    """Último número emitido por dia e tipo. Incrementado de forma atômica."""

    __tablename__ = "contadorsenha"

    data_ref: date = Field(primary_key=True)
    tipo: TipoSenha = Field(primary_key=True)
    valor: int = 0


class AtendimentoTabela(SQLModel, table=True):
    __tablename__ = "atendimento"

    id: int | None = Field(default=None, primary_key=True)
    modo: ModoAcessibilidade
    consentimento_em: datetime
    # Colunas JSON: atribua um objeto novo ao alterar (mutação in-place não é detectada).
    respostas: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON, nullable=False))
    canais: dict[str, str] = Field(default_factory=dict, sa_column=Column(JSON, nullable=False))
    status: StatusAtendimento = StatusAtendimento.em_andamento
    senha_id: int | None = Field(default=None, foreign_key="senha.id")
    resumo: str | None = None
    alertas: list[str] = Field(default_factory=list, sa_column=Column(JSON, nullable=False))
    criado_em: datetime
    finalizado_em: datetime | None = None


class IdentificacaoTabela(SQLModel, table=True):
    """Tabela separada para que o `create_all` a crie em bancos já existentes sem ALTER TABLE."""

    __tablename__ = "identificacao"

    atendimento_id: int = Field(foreign_key="atendimento.id", primary_key=True)
    nome: str
    cpf: str = Field(index=True)
    criada_em: datetime


class QueixaTabela(SQLModel, table=True):
    __tablename__ = "queixa"

    id: int | None = Field(default=None, primary_key=True)
    atendimento_id: int = Field(foreign_key="atendimento.id", index=True)
    sintoma: str
    local: str | None = None
    intensidade: int | None = None
    desde_quando: str | None = None
    criada_em: datetime
