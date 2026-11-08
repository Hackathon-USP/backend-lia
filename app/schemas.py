from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.conteudo.fluxo import Pergunta
from app.models import ModoAcessibilidade, StatusAtendimento, StatusSenha, TipoSenha


class SenhaCriar(BaseModel):
    tipo: TipoSenha


class SenhaLeitura(BaseModel):
    codigo: str
    tipo: TipoSenha
    numero: int
    status: StatusSenha
    criada_em: datetime


class OpcaoLeitura(BaseModel):
    id: str
    rotulo: str
    # Nomes de sinal/palavras aceitos como resposta para esta opção.
    sinais: list[str] = []


class PerguntaLeitura(BaseModel):
    id: str
    texto: str
    tipo: Literal["opcoes", "escala"]
    opcoes: list[OpcaoLeitura] = []
    minimo: int | None = None
    maximo: int | None = None

    @classmethod
    def de(cls, pergunta: Pergunta | None) -> "PerguntaLeitura | None":
        if pergunta is None:
            return None
        return cls(
            id=pergunta.id,
            texto=pergunta.texto,
            tipo=pergunta.tipo,
            opcoes=[
                OpcaoLeitura(id=o.id, rotulo=o.rotulo, sinais=list(o.sinais))
                for o in pergunta.opcoes
            ],
            minimo=pergunta.minimo,
            maximo=pergunta.maximo,
        )


class AtendimentoCriar(BaseModel):
    modo: ModoAcessibilidade
    consentimento: Literal[True] = Field(
        description="Precisa ser true: o paciente aceitou o uso dos dados para o atendimento."
    )


class RespostaCriar(BaseModel):
    pergunta_id: str
    valor: str | int = Field(
        description="Id da opção, rótulo ou nome do sinal reconhecido (ex.: 'DOR', 'CABEÇA', 'SETE')."
    )
    canal: ModoAcessibilidade | None = Field(
        default=None, description="Por onde veio a resposta. Se omitido, usa o modo do atendimento."
    )
    confianca: float | None = Field(
        default=None, ge=0, le=1, description="Confiança do reconhecimento de Libras/voz (0 a 1)."
    )


class AtendimentoLeitura(BaseModel):
    id: int
    modo: ModoAcessibilidade
    status: StatusAtendimento
    respostas: dict[str, Any]
    canais: dict[str, str] = {}
    proxima_pergunta: PerguntaLeitura | None
    # true = a última resposta não foi entendida; o totem mostra `mensagem` e repete a pergunta.
    repetir: bool = False
    mensagem: str | None = None
    criado_em: datetime


class FinalizacaoLeitura(BaseModel):
    atendimento_id: int
    senha: SenhaLeitura
    mensagem_final: str


# --- Recepção ---------------------------------------------------------------


class ItemFila(BaseModel):
    codigo: str
    tipo: TipoSenha
    status: StatusSenha
    criada_em: datetime
    # Vazios quando a senha foi emitida direto em POST /senhas, sem triagem.
    atendimento_id: int | None = None
    modo: ModoAcessibilidade | None = None
    alertas: list[str] = []


class AtendimentoResumo(BaseModel):
    id: int
    modo: ModoAcessibilidade
    status: StatusAtendimento
    senha: str | None = None
    alertas: list[str] = []
    criado_em: datetime
    finalizado_em: datetime | None = None


class RespostaRotulada(BaseModel):
    pergunta_id: str
    pergunta: str
    valor: Any
    resposta: str = Field(description="Texto legível da opção escolhida (ex.: 'Falta de ar').")
    canal: str | None = None


class QueixaLeitura(BaseModel):
    sintoma: str
    local: str | None = None
    intensidade: int | None = None
    desde_quando: str | None = None


class AtendimentoDetalhe(AtendimentoResumo):
    senha_detalhe: SenhaLeitura | None = None
    resumo: str | None = None
    respostas: list[RespostaRotulada]
    queixa: QueixaLeitura | None = None


class Chamada(BaseModel):
    senha: SenhaLeitura
    atendimento_id: int | None = None
    modo: ModoAcessibilidade | None = None
    alertas: list[str] = []
    resumo: str | None = None


class SenhaStatusAtualizar(BaseModel):
    status: StatusSenha
