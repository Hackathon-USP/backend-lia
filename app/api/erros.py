"""Tradução dos erros de negócio do domínio em respostas HTTP."""

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

from app.domain.erros import Conflito, DadosInvalidos, ErroDeNegocio, NaoEncontrado

STATUS_POR_ERRO: dict[type[ErroDeNegocio], int] = {
    NaoEncontrado: status.HTTP_404_NOT_FOUND,
    Conflito: status.HTTP_409_CONFLICT,
    DadosInvalidos: status.HTTP_422_UNPROCESSABLE_ENTITY,
}


def status_http(erro: ErroDeNegocio) -> int:
    for familia, codigo in STATUS_POR_ERRO.items():
        if isinstance(erro, familia):
            return codigo
    return status.HTTP_400_BAD_REQUEST


async def _responder_erro_de_negocio(_request: Request, erro: ErroDeNegocio) -> JSONResponse:
    """Mesmo formato do HTTPException do FastAPI: `{"detail": "<mensagem>"}`."""
    return JSONResponse(status_code=status_http(erro), content={"detail": str(erro)})


def registrar_tratamento_de_erros(app: FastAPI) -> None:
    app.add_exception_handler(ErroDeNegocio, _responder_erro_de_negocio)
