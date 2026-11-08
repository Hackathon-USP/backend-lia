from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session

from app.conteudo.textos import TEXTOS
from app.db import get_session
from app.models import Atendimento
from app.schemas import (
    AtendimentoCriar,
    AtendimentoLeitura,
    FinalizacaoLeitura,
    IdentificacaoCriar,
    PerguntaLeitura,
    RespostaCriar,
    SenhaLeitura,
)
from app.services import atendimento as svc
from app.services import identificacao

router = APIRouter(prefix="/atendimentos", tags=["atendimentos"])


def _leitura(session: Session, atendimento: Atendimento, repetir: bool = False) -> AtendimentoLeitura:
    return AtendimentoLeitura(
        id=atendimento.id,
        modo=atendimento.modo,
        status=atendimento.status,
        respostas=atendimento.respostas,
        canais=atendimento.canais,
        proxima_pergunta=PerguntaLeitura.de(svc.proxima_pergunta(atendimento)),
        identificado=identificacao.obter(session, atendimento.id) is not None,
        repetir=repetir,
        mensagem=TEXTOS["repetir"] if repetir else None,
        criado_em=atendimento.criado_em,
    )


def _nao_encontrado():
    return HTTPException(status.HTTP_404_NOT_FOUND, "Atendimento não encontrado")


def _ja_finalizado():
    return HTTPException(status.HTTP_409_CONFLICT, "Atendimento já finalizado")


@router.post("", response_model=AtendimentoLeitura, status_code=status.HTTP_201_CREATED)
def iniciar(dados: AtendimentoCriar, session: Session = Depends(get_session)):
    """Inicia a triagem após o consentimento. Devolve a primeira pergunta."""
    return _leitura(session, svc.iniciar(session, dados.modo))


@router.get("/{atendimento_id}", response_model=AtendimentoLeitura)
def consultar(atendimento_id: int, session: Session = Depends(get_session)):
    """Estado atual (útil para retomar se a tela do totem recarregar)."""
    try:
        return _leitura(session, svc.obter(session, atendimento_id))
    except svc.AtendimentoNaoEncontrado:
        raise _nao_encontrado() from None


@router.post("/{atendimento_id}/respostas", response_model=AtendimentoLeitura)
def responder(atendimento_id: int, dados: RespostaCriar, session: Session = Depends(get_session)):
    """Grava a resposta da pergunta atual e devolve a próxima (`null` = pode finalizar).

    Aceita o nome do sinal reconhecido em Libras (ex.: `"DOR"`) ou a palavra falada.
    Se vier por Libras/voz com `confianca` abaixo do limiar, ou com um sinal que não
    corresponde a nenhuma opção, nada é gravado e a resposta vem com `repetir: true`.
    """
    try:
        atendimento, repetir = svc.registrar_resposta(
            session, atendimento_id, dados.pergunta_id, dados.valor, dados.canal, dados.confianca
        )
    except svc.AtendimentoNaoEncontrado:
        raise _nao_encontrado() from None
    except svc.AtendimentoJaFinalizado:
        raise _ja_finalizado() from None
    except svc.RespostaInvalida as erro:
        raise HTTPException(422, str(erro)) from None
    return _leitura(session, atendimento, repetir)


@router.put("/{atendimento_id}/identificacao", response_model=AtendimentoLeitura)
def identificar(atendimento_id: int, dados: IdentificacaoCriar, session: Session = Depends(get_session)):
    """Grava nome e CPF do paciente (obrigatórios para finalizar). Pode ser chamado de
    novo para corrigir, enquanto o atendimento não foi finalizado. Não devolve os dados
    de volta: o totem é público."""
    try:
        atendimento = identificacao.registrar(session, atendimento_id, dados.nome, dados.cpf)
    except svc.AtendimentoNaoEncontrado:
        raise _nao_encontrado() from None
    except svc.AtendimentoJaFinalizado:
        raise _ja_finalizado() from None
    except ValueError as erro:
        raise HTTPException(422, str(erro)) from None
    return _leitura(session, atendimento)


@router.post("/{atendimento_id}/finalizar", response_model=FinalizacaoLeitura)
def finalizar(atendimento_id: int, session: Session = Depends(get_session)):
    """Emite a senha, gera o resumo para a recepção e devolve a mensagem final do totem."""
    try:
        atendimento, senha, mensagem = svc.finalizar(session, atendimento_id)
    except svc.AtendimentoNaoEncontrado:
        raise _nao_encontrado() from None
    except svc.AtendimentoJaFinalizado:
        raise _ja_finalizado() from None
    except svc.TriagemIncompleta:
        raise HTTPException(status.HTTP_409_CONFLICT, "Ainda há perguntas sem resposta") from None
    except svc.IdentificacaoPendente:
        raise HTTPException(status.HTTP_409_CONFLICT, "Informe nome e CPF antes de finalizar") from None
    return FinalizacaoLeitura(
        atendimento_id=atendimento.id,
        senha=SenhaLeitura.model_validate(senha, from_attributes=True),
        mensagem_final=mensagem,
    )
