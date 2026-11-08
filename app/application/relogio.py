"""Hora local do totem. O "dia" da fila e dos filtros é sempre o do fuso configurado."""

from datetime import date, datetime
from zoneinfo import ZoneInfo

from app.config import settings


def fuso_local() -> ZoneInfo:
    return ZoneInfo(settings.fuso_horario)


def agora_local() -> datetime:
    return datetime.now(fuso_local())


def dia_local(momento: datetime) -> date:
    """Dia no fuso local (o banco devolve UTC: quem chega às 22h ainda é do mesmo dia)."""
    return momento.astimezone(fuso_local()).date()
