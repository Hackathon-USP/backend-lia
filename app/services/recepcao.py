"""Consultas e ações da tela da recepção: fila do dia, detalhe do atendimento e chamada de senhas."""

from dataclasses import dataclass
from datetime import date, datetime
from zoneinfo import ZoneInfo

from sqlalchemy import update
from sqlmodel import Session, select

from app.config import settings
from app.conteudo.fluxo import POR_ID
from app.models import (
    Atendimento,
    ModoAcessibilidade,
    Queixa,
    Senha,
    StatusAtendimento,
    StatusSenha,
    TipoSenha,
)
from app.services import fila
from app.services.atendimento import AtendimentoNaoEncontrado


class SenhaNaoEncontrada(Exception):
    pass


@dataclass
class ItemFila:
    senha: Senha
    atendimento: Atendimento | None  # None para senhas emitidas direto em POST /senhas


_ORDEM_STATUS = {StatusSenha.aguardando: 0, StatusSenha.em_atendimento: 1, StatusSenha.finalizada: 2}


def _chave_fila(senha: Senha):
    # Aguardando primeiro; dentro dele, preferenciais (Lei 10.048/2000) e depois as mais antigas.
    return (_ORDEM_STATUS[senha.status], senha.tipo != TipoSenha.preferencial, senha.criada_em, senha.numero)


def _atendimentos_por_senha(session: Session, senhas: list[Senha]) -> dict[int, Atendimento]:
    ids = [s.id for s in senhas]
    if not ids:
        return {}
    atendimentos = session.exec(select(Atendimento).where(Atendimento.senha_id.in_(ids))).all()
    return {a.senha_id: a for a in atendimentos}


def listar_fila(session: Session, data_ref: date | None = None, status: StatusSenha | None = None) -> list[ItemFila]:
    data_ref = data_ref or fila.agora_local().date()
    consulta = select(Senha).where(Senha.data_ref == data_ref)
    if status is not None:
        consulta = consulta.where(Senha.status == status)
    senhas = sorted(session.exec(consulta).all(), key=_chave_fila)
    por_senha = _atendimentos_por_senha(session, senhas)
    return [ItemFila(senha=s, atendimento=por_senha.get(s.id)) for s in senhas]


def listar_atendimentos(
    session: Session,
    data_ref: date | None = None,
    status: StatusAtendimento | None = None,
    modo: ModoAcessibilidade | None = None,
) -> list[tuple[Atendimento, Senha | None]]:
    consulta = select(Atendimento)
    if status is not None:
        consulta = consulta.where(Atendimento.status == status)
    if modo is not None:
        consulta = consulta.where(Atendimento.modo == modo)
    atendimentos = session.exec(consulta.order_by(Atendimento.criado_em.desc(), Atendimento.id.desc())).all()
    if data_ref is not None:
        # O banco devolve UTC; o "dia" é o do fuso local (quem chega às 22h é do mesmo dia).
        fuso = ZoneInfo(settings.fuso_horario)
        atendimentos = [a for a in atendimentos if a.criado_em.astimezone(fuso).date() == data_ref]
    senha_ids = [a.senha_id for a in atendimentos if a.senha_id is not None]
    senhas = {s.id: s for s in session.exec(select(Senha).where(Senha.id.in_(senha_ids))).all()} if senha_ids else {}
    return [(a, senhas.get(a.senha_id)) for a in atendimentos]


@dataclass
class RespostaRotulada:
    pergunta_id: str
    pergunta: str
    valor: object
    resposta: str
    canal: str | None


@dataclass
class DetalheAtendimento:
    atendimento: Atendimento
    senha: Senha | None
    queixa: Queixa | None
    respostas: list[RespostaRotulada]


def rotular_respostas(atendimento: Atendimento) -> list[RespostaRotulada]:
    """Respostas na ordem das perguntas, com o texto legível de cada opção."""
    itens = []
    for pid, valor in atendimento.respostas.items():
        pergunta = POR_ID.get(pid)
        itens.append(
            RespostaRotulada(
                pergunta_id=pid,
                pergunta=pergunta.texto if pergunta else pid,
                valor=valor,
                resposta=pergunta.rotulo_de(valor) if pergunta else str(valor),
                canal=atendimento.canais.get(pid),
            )
        )
    ordem = list(POR_ID)
    itens.sort(key=lambda r: ordem.index(r.pergunta_id) if r.pergunta_id in POR_ID else len(ordem))
    return itens


def detalhar_atendimento(session: Session, atendimento_id: int) -> DetalheAtendimento:
    atendimento = session.get(Atendimento, atendimento_id)
    if atendimento is None:
        raise AtendimentoNaoEncontrado
    senha = session.get(Senha, atendimento.senha_id) if atendimento.senha_id else None
    queixa = session.exec(select(Queixa).where(Queixa.atendimento_id == atendimento.id)).first()
    return DetalheAtendimento(atendimento, senha, queixa, rotular_respostas(atendimento))


def _marcar_se_aguardando(session: Session, senha: Senha, novo: StatusSenha) -> bool:
    """UPDATE condicional: só um guichê consegue tirar a senha de `aguardando`."""
    resultado = session.connection().execute(
        update(Senha)
        .where(Senha.id == senha.id, Senha.status == StatusSenha.aguardando)
        .values(status=novo)
    )
    session.commit()
    session.refresh(senha)
    return resultado.rowcount == 1


def chamar_proxima(session: Session, agora: datetime | None = None) -> ItemFila | None:
    """Passa a próxima senha aguardando do dia para `em_atendimento`. None = fila vazia."""
    data_ref = (agora or fila.agora_local()).date()
    for item in listar_fila(session, data_ref, StatusSenha.aguardando):
        if _marcar_se_aguardando(session, item.senha, StatusSenha.em_atendimento):
            return item
        # Outro guichê chamou esta senha no meio do caminho: tenta a seguinte.
    return None


def atualizar_status(
    session: Session, codigo: str, novo: StatusSenha, agora: datetime | None = None
) -> Senha:
    senha = fila.buscar_senha_do_dia(session, codigo, agora)
    if senha is None:
        raise SenhaNaoEncontrada
    senha.status = novo
    session.add(senha)
    session.commit()
    session.refresh(senha)
    return senha
