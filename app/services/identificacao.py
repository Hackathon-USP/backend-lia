"""Nome e CPF do paciente, informados no totem antes de emitir a senha."""

import re
from datetime import datetime

from sqlmodel import Session, select

from app.models import Atendimento, Identificacao, StatusAtendimento
from app.services import fila
from app.services.atendimento import AtendimentoJaFinalizado, obter as obter_atendimento


def normalizar_cpf(texto: str) -> str:
    """'123.456.789-09' -> '12345678909'. Levanta ValueError se o CPF for inválido."""
    digitos = re.sub(r"\D", "", texto or "")
    if len(digitos) != 11:
        raise ValueError("CPF deve ter 11 dígitos")
    if digitos == digitos[0] * 11:
        raise ValueError("CPF inválido")
    for tamanho in (9, 10):
        soma = sum(int(d) * peso for d, peso in zip(digitos[:tamanho], range(tamanho + 1, 1, -1)))
        verificador = (soma * 10) % 11 % 10
        if verificador != int(digitos[tamanho]):
            raise ValueError("CPF inválido")
    return digitos


def formatar_cpf(cpf: str) -> str:
    """'12345678909' -> '123.456.789-09'."""
    return f"{cpf[:3]}.{cpf[3:6]}.{cpf[6:9]}-{cpf[9:]}"


def normalizar_nome(texto: str) -> str:
    nome = " ".join((texto or "").split())
    if not (2 <= len(nome) <= 120) or not any(c.isalpha() for c in nome):
        raise ValueError("Informe o nome completo")
    return nome


def obter(session: Session, atendimento_id: int) -> Identificacao | None:
    return session.get(Identificacao, atendimento_id)


def por_atendimentos(session: Session, ids: list[int]) -> dict[int, Identificacao]:
    """Identificações de vários atendimentos numa só consulta."""
    if not ids:
        return {}
    linhas = session.exec(select(Identificacao).where(Identificacao.atendimento_id.in_(ids))).all()
    return {i.atendimento_id: i for i in linhas}


def registrar(
    session: Session, atendimento_id: int, nome: str, cpf: str, agora: datetime | None = None
) -> Atendimento:
    """Grava (ou corrige, antes de finalizar) o nome e o CPF. Levanta ValueError se inválidos."""
    atendimento = obter_atendimento(session, atendimento_id)
    if atendimento.status == StatusAtendimento.finalizado:
        raise AtendimentoJaFinalizado
    nome, cpf = normalizar_nome(nome), normalizar_cpf(cpf)

    identificacao = obter(session, atendimento_id) or Identificacao(
        atendimento_id=atendimento_id, nome=nome, cpf=cpf, criada_em=agora or fila.agora_local()
    )
    identificacao.nome, identificacao.cpf = nome, cpf
    session.add(identificacao)
    session.commit()
    session.refresh(atendimento)
    return atendimento
