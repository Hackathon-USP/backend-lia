from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session

from app.db import get_session
from app.schemas import SenhaCriar, SenhaLeitura
from app.services import fila

router = APIRouter(prefix="/senhas", tags=["senhas"])


@router.post("", response_model=SenhaLeitura, status_code=status.HTTP_201_CREATED)
def emitir(dados: SenhaCriar, session: Session = Depends(get_session)):
    """Emite uma nova senha. Pessoas com deficiência devem receber `preferencial`."""
    return fila.emitir_senha(session, dados.tipo)


@router.get("/{codigo}", response_model=SenhaLeitura)
def consultar(codigo: str, session: Session = Depends(get_session)):
    """Consulta uma senha emitida hoje pelo código (ex.: `P012`)."""
    senha = fila.buscar_senha_do_dia(session, codigo)
    if senha is None:
        raise HTTPException(status_code=404, detail="Senha não encontrada hoje")
    return senha
