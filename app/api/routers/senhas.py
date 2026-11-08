from fastapi import APIRouter, Depends, status

from app.api.dependencias import servico_senhas
from app.api.schemas import SenhaCriar, SenhaLeitura
from app.application.senhas import ServicoSenhas

router = APIRouter(prefix="/senhas", tags=["senhas"])


@router.post("", response_model=SenhaLeitura, status_code=status.HTTP_201_CREATED)
def emitir(dados: SenhaCriar, servico: ServicoSenhas = Depends(servico_senhas)):
    """Emite uma nova senha. Pessoas com deficiência devem receber `preferencial`."""
    return SenhaLeitura.model_validate(servico.emitir(dados.tipo), from_attributes=True)


@router.get("/{codigo}", response_model=SenhaLeitura)
def consultar(codigo: str, servico: ServicoSenhas = Depends(servico_senhas)):
    """Consulta uma senha emitida hoje pelo código (ex.: `P012`)."""
    return SenhaLeitura.model_validate(servico.obter_do_dia(codigo), from_attributes=True)
