from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.db import init_db
from app.routers import atendimentos, conteudo, senhas


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


DESCRICAO = """
API da **tela do paciente** do totem de atendimento acessível.

O front cuida de VLibras (texto → avatar em Libras), do reconhecimento de sinais
(MediaPipe) e da voz (Web Speech API). O back end guarda o atendimento, decide a
ramificação das perguntas, emite a senha e monta o resumo para a recepção.

### Fluxo da tela do paciente
1. `GET /conteudo/textos` e `GET /conteudo/perguntas` — pré-carrega textos fixos e o
   vocabulário de sinais aceito em cada opção.
2. `POST /atendimentos` `{modo, consentimento: true}` — inicia e devolve a 1ª pergunta.
3. `POST /atendimentos/{id}/respostas` `{pergunta_id, valor, canal?, confianca?}` —
   grava a resposta e devolve `proxima_pergunta` (ou `null` quando pode finalizar).
   O `valor` pode ser o id da opção, o rótulo ou o **nome do sinal** reconhecido
   (ex.: `"DOR"`). Se vier por Libras/voz com `confianca` baixa, ou com um sinal que
   não casa com nenhuma opção, nada é gravado e a resposta vem com `repetir: true`.
4. `POST /atendimentos/{id}/finalizar` — emite a senha e devolve a mensagem final.
5. `GET /atendimentos/{id}` — estado atual, para retomar se a tela recarregar.

Modos `libras` e `voz` recebem senha **preferencial** automaticamente (Lei 10.048/2000).
"""

TAGS = [
    {"name": "conteudo", "description": "Textos e perguntas fixas, pré-carregadas pelo front."},
    {"name": "atendimentos", "description": "Sessão de triagem do paciente, da abertura à senha."},
    {"name": "senhas", "description": "Emissão e consulta de senhas da fila."},
    {"name": "infra", "description": "Verificação de saúde do serviço."},
]

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

app.include_router(senhas.router)
app.include_router(atendimentos.router)
app.include_router(conteudo.router)


@app.get("/saude", tags=["infra"])
def saude():
    return {"status": "ok"}
