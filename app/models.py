from datetime import date, datetime
from enum import Enum

from typing import Any

from sqlalchemy import JSON, Column, UniqueConstraint
from sqlmodel import Field, SQLModel


class TipoSenha(str, Enum):
    normal = "normal"
    preferencial = "preferencial"


class StatusSenha(str, Enum):
    aguardando = "aguardando"
    em_atendimento = "em_atendimento"
    finalizada = "finalizada"


PREFIXOS = {TipoSenha.normal: "N", TipoSenha.preferencial: "P"}


class Senha(SQLModel, table=True):
    __table_args__ = (UniqueConstraint("data_ref", "codigo"),)

    id: int | None = Field(default=None, primary_key=True)
    codigo: str = Field(index=True)  # ex.: "P012" — único dentro do dia
    tipo: TipoSenha
    numero: int
    data_ref: date = Field(index=True)  # dia (no fuso local) em que a senha foi emitida
    status: StatusSenha = StatusSenha.aguardando
    criada_em: datetime


class ContadorSenha(SQLModel, table=True):
    """Último número emitido por dia e tipo. Incrementado de forma atômica."""

    data_ref: date = Field(primary_key=True)
    tipo: TipoSenha = Field(primary_key=True)
    valor: int = 0


class ModoAcessibilidade(str, Enum):
    libras = "libras"
    voz = "voz"
    toque = "toque"


class StatusAtendimento(str, Enum):
    em_andamento = "em_andamento"
    finalizado = "finalizado"


class Atendimento(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    modo: ModoAcessibilidade
    consentimento_em: datetime
    # {pergunta_id: valor}. Ao alterar, atribua um dict novo (mutação in-place não é detectada).
    respostas: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON, nullable=False))
    # {pergunta_id: canal} — por onde cada resposta chegou (libras, voz ou toque).
    canais: dict[str, str] = Field(default_factory=dict, sa_column=Column(JSON, nullable=False))
    status: StatusAtendimento = StatusAtendimento.em_andamento
    senha_id: int | None = Field(default=None, foreign_key="senha.id")
    resumo: str | None = None
    alertas: list[str] = Field(default_factory=list, sa_column=Column(JSON, nullable=False))
    criado_em: datetime
    finalizado_em: datetime | None = None


class Identificacao(SQLModel, table=True):
    """Nome e CPF informados pelo paciente no totem. Tabela separada para que o
    `create_all` a crie em bancos já existentes sem precisar de ALTER TABLE."""

    atendimento_id: int = Field(foreign_key="atendimento.id", primary_key=True)
    nome: str
    cpf: str = Field(index=True)  # só os 11 dígitos
    criada_em: datetime


class Queixa(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    atendimento_id: int = Field(foreign_key="atendimento.id", index=True)
    sintoma: str
    local: str | None = None
    intensidade: int | None = None
    desde_quando: str | None = None
    criada_em: datetime
