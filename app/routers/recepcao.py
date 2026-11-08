"""Endpoints da tela da recepção.

TODO: proteger antes de uso real — devolvem nome, CPF e dados de saúde dos pacientes (LGPD).
"""

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlmodel import Session

from app.db import get_session
from app.models import ModoAcessibilidade, StatusAtendimento, StatusSenha
from app.schemas import (
    AtendimentoDetalhe,
    AtendimentoResumo,
    Chamada,
    ItemFila,
    QueixaLeitura,
    RespostaRotulada,
    SenhaLeitura,
    SenhaStatusAtualizar,
)
from app.services import identificacao
from app.services import recepcao as svc
from app.services.atendimento import AtendimentoNaoEncontrado

router = APIRouter(prefix="/recepcao", tags=["recepcao"])


def _senha(senha) -> SenhaLeitura | None:
    return SenhaLeitura.model_validate(senha, from_attributes=True) if senha else None


def _nome_cpf(ident) -> dict:
    """Campos `nome` e `cpf` (formatado); vazios para atendimentos sem identificação."""
    if ident is None:
        return {"nome": None, "cpf": None}
    return {"nome": ident.nome, "cpf": identificacao.formatar_cpf(ident.cpf)}


def _resumo(atendimento, senha, ident) -> AtendimentoResumo:
    return AtendimentoResumo(
        id=atendimento.id,
        modo=atendimento.modo,
        status=atendimento.status,
        senha=senha.codigo if senha else None,
        **_nome_cpf(ident),
        alertas=atendimento.alertas,
        criado_em=atendimento.criado_em,
        finalizado_em=atendimento.finalizado_em,
    )


def _item_fila(item: svc.ItemFila, ident) -> ItemFila:
    a = item.atendimento
    return ItemFila(
        codigo=item.senha.codigo,
        tipo=item.senha.tipo,
        status=item.senha.status,
        criada_em=item.senha.criada_em,
        atendimento_id=a.id if a else None,
        modo=a.modo if a else None,
        **_nome_cpf(ident),
        alertas=a.alertas if a else [],
    )


@router.get("/fila", response_model=list[ItemFila])
def fila(
    data: date | None = None,
    status_senha: StatusSenha | None = Query(None, alias="status"),
    session: Session = Depends(get_session),
):
    """Senhas do dia (padrão: hoje). Ordem: aguardando primeiro, preferenciais antes,
    depois por horário de emissão. Inclui os alertas da triagem de cada paciente."""
    itens = svc.listar_fila(session, data, status_senha)
    idents = identificacao.por_atendimentos(session, [i.atendimento.id for i in itens if i.atendimento])
    return [_item_fila(i, idents.get(i.atendimento.id) if i.atendimento else None) for i in itens]


@router.get("/atendimentos", response_model=list[AtendimentoResumo])
def listar_atendimentos(
    data: date | None = None,
    status_atendimento: StatusAtendimento | None = Query(None, alias="status"),
    modo: ModoAcessibilidade | None = None,
    cpf: str | None = Query(None, description="Com ou sem máscara. Traz o histórico do paciente."),
    session: Session = Depends(get_session),
):
    """Atendimentos cadastrados, mais recentes primeiro. Todos os filtros são opcionais."""
    linhas = svc.listar_atendimentos(session, data, status_atendimento, modo, cpf)
    idents = identificacao.por_atendimentos(session, [a.id for a, _ in linhas])
    return [_resumo(a, s, idents.get(a.id)) for a, s in linhas]


@router.get("/atendimentos/{atendimento_id}", response_model=AtendimentoDetalhe)
def detalhar_atendimento(atendimento_id: int, session: Session = Depends(get_session)):
    """Tudo que o paciente informou, com textos legíveis, resumo e alertas."""
    try:
        d = svc.detalhar_atendimento(session, atendimento_id)
    except AtendimentoNaoEncontrado:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Atendimento não encontrado") from None
    return AtendimentoDetalhe(
        **_resumo(d.atendimento, d.senha, identificacao.obter(session, atendimento_id)).model_dump(),
        senha_detalhe=_senha(d.senha),
        resumo=d.atendimento.resumo,
        respostas=[RespostaRotulada(**vars(r)) for r in d.respostas],
        queixa=QueixaLeitura.model_validate(d.queixa, from_attributes=True) if d.queixa else None,
    )


@router.post("/chamar", response_model=Chamada)
def chamar(session: Session = Depends(get_session)):
    """Chama a próxima senha aguardando (preferenciais primeiro) e a marca como
    `em_atendimento`. Dois guichês chamando juntos nunca recebem a mesma senha."""
    item = svc.chamar_proxima(session)
    if item is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Fila vazia")
    a = item.atendimento
    return Chamada(
        senha=_senha(item.senha),
        atendimento_id=a.id if a else None,
        modo=a.modo if a else None,
        **_nome_cpf(identificacao.obter(session, a.id) if a else None),
        alertas=a.alertas if a else [],
        resumo=a.resumo if a else None,
    )


@router.patch("/senhas/{codigo}", response_model=SenhaLeitura)
def atualizar_senha(codigo: str, dados: SenhaStatusAtualizar, session: Session = Depends(get_session)):
    """Muda o status de uma senha de hoje (ex.: chamar uma específica, ou `finalizada`)."""
    try:
        return _senha(svc.atualizar_status(session, codigo, dados.status))
    except svc.SenhaNaoEncontrada:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Senha não encontrada hoje") from None
