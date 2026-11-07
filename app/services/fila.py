from datetime import date, datetime
from zoneinfo import ZoneInfo

from sqlmodel import Session, select

from app.config import settings
from app.models import PREFIXOS, ContadorSenha, Senha, TipoSenha


def agora_local() -> datetime:
    return datetime.now(ZoneInfo(settings.fuso_horario))


def _proximo_numero(session: Session, data_ref: date, tipo: TipoSenha) -> int:
    """Incrementa e devolve o contador em um único comando (UPSERT ... RETURNING).

    Por ser um só comando no banco, dois totens emitindo ao mesmo tempo nunca
    recebem o mesmo número (o banco serializa o acesso à linha do contador).
    """
    tabela = ContadorSenha.__table__
    dialeto = session.get_bind().dialect.name
    if dialeto == "postgresql":
        from sqlalchemy.dialects.postgresql import insert
    elif dialeto == "sqlite":
        from sqlalchemy.dialects.sqlite import insert
    else:
        raise RuntimeError(f"Banco não suportado: {dialeto}")

    stmt = (
        insert(tabela)
        .values(data_ref=data_ref, tipo=tipo, valor=1)
        .on_conflict_do_update(
            index_elements=["data_ref", "tipo"],
            set_={"valor": tabela.c.valor + 1},
        )
        .returning(tabela.c.valor)
    )
    return session.connection().execute(stmt).scalar_one()


def emitir_senha(session: Session, tipo: TipoSenha, agora: datetime | None = None) -> Senha:
    agora = agora or agora_local()
    data_ref = agora.date()
    numero = _proximo_numero(session, data_ref, tipo)
    senha = Senha(
        codigo=f"{PREFIXOS[tipo]}{numero:03d}",
        tipo=tipo,
        numero=numero,
        data_ref=data_ref,
        criada_em=agora,
    )
    session.add(senha)
    session.commit()
    session.refresh(senha)
    return senha


def buscar_senha_do_dia(session: Session, codigo: str, agora: datetime | None = None) -> Senha | None:
    data_ref = (agora or agora_local()).date()
    return session.exec(
        select(Senha).where(Senha.codigo == codigo.upper(), Senha.data_ref == data_ref)
    ).first()
