"""Conversão entre entidades do domínio (dataclasses) e linhas das tabelas.

Cada entidade tem os mesmos nomes de campo que a sua tabela, então um mapeador
genérico basta. As cópias profundas evitam que a entidade e a linha do ORM
compartilhem os mesmos dicts/listas das colunas JSON.
"""

from copy import deepcopy
from dataclasses import fields
from typing import TypeVar

from sqlmodel import SQLModel

Entidade = TypeVar("Entidade")
Linha = TypeVar("Linha", bound=SQLModel)


def para_entidade(classe: type[Entidade], linha: SQLModel) -> Entidade:
    return classe(**{campo.name: deepcopy(getattr(linha, campo.name)) for campo in fields(classe)})


def copiar_para_linha(entidade: object, linha: Linha) -> Linha:
    for campo in fields(entidade):
        setattr(linha, campo.name, deepcopy(getattr(entidade, campo.name)))
    return linha
