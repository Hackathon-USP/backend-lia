"""Ponto de entrada: monta a aplicação FastAPI e liga as camadas.

Camadas (as dependências só apontam para dentro):
    api          -> rotas HTTP, schemas e injeção de dependências
    application  -> casos de uso
    domain       -> entidades, regras de negócio e contratos dos repositórios
    persistence  -> banco de dados (implementa os contratos do domínio)
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.documentacao import DESCRICAO, TAGS
from app.api.erros import registrar_tratamento_de_erros
from app.api.routers import atendimentos, conteudo, infra, recepcao, senhas
from app.config import settings
from app.persistence.db import init_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(
    title="Totem de Atendimento Acessível",
    version="0.1.0",
    description=DESCRICAO,
    openapi_tags=TAGS,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.cors_origens.split(",")],
    allow_methods=["*"],
    allow_headers=["*"],
)

registrar_tratamento_de_erros(app)

app.include_router(senhas.router)
app.include_router(atendimentos.router)
app.include_router(conteudo.router)
app.include_router(recepcao.router)
app.include_router(infra.router)
