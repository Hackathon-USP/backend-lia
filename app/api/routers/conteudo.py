from fastapi import APIRouter

from app.api.schemas import PerguntaLeitura
from app.domain.textos import TEXTOS
from app.domain.triagem import PERGUNTAS

router = APIRouter(prefix="/conteudo", tags=["conteudo"])


@router.get("/textos", response_model=dict[str, str])
def textos():
    """Textos fixos do totem (boas-vindas, consentimento, avisos) para VLibras e TTS.

    `{senha}` nos textos de finalização é preenchido pelo back end ao finalizar.
    """
    return TEXTOS


@router.get("/perguntas", response_model=list[PerguntaLeitura])
def perguntas():
    """Todas as perguntas da triagem (para o front pré-carregar). A ordem e a
    ramificação são decididas pelo back end em `/atendimentos/{id}/respostas`."""
    return [PerguntaLeitura.de(p) for p in PERGUNTAS]
