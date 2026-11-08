from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.domain.enums import ModoAcessibilidade, StatusAtendimento, StatusSenha, TipoSenha
from app.domain.entidades import RelatorioTriagem
from app.domain.triagem import OrigemPergunta, Pergunta, TipoPergunta


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
    titulo: str = Field(description="Rótulo curto da pergunta, usado no resumo de conferência.")
    tipo: TipoPergunta
    opcoes: list[OpcaoLeitura] = []
    minimo: int | None = None
    maximo: int | None = None
    origem: OrigemPergunta = Field(
        default=OrigemPergunta.triagem,
        description=(
            "`triagem` = pergunta fixa; `lia` = pergunta complementar criada pela LIA (IA) para este paciente."
        ),
    )

    @classmethod
    def de(cls, pergunta: Pergunta | None) -> "PerguntaLeitura | None":
        if pergunta is None:
            return None
        return cls(
            id=pergunta.id,
            texto=pergunta.texto,
            titulo=pergunta.titulo,
            tipo=pergunta.tipo,
            opcoes=[
                OpcaoLeitura(id=o.id, rotulo=o.rotulo, sinais=list(o.sinais))
                for o in pergunta.opcoes
            ],
            minimo=pergunta.minimo,
            maximo=pergunta.maximo,
            origem=pergunta.origem,
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


class IdentificacaoCriar(BaseModel):
    nome: str = Field(description="Nome completo do paciente.")
    cpf: str = Field(description="CPF com ou sem máscara (ex.: '123.456.789-09').")


class AtendimentoLeitura(BaseModel):
    id: int
    modo: ModoAcessibilidade
    status: StatusAtendimento
    respostas: dict[str, Any]
    canais: dict[str, str] = {}
    proxima_pergunta: PerguntaLeitura | None
    # false = falta PUT /identificacao (nome e CPF) antes de poder finalizar.
    identificado: bool = False
    # true = a última resposta não foi entendida; o totem mostra `mensagem` e repete a pergunta.
    repetir: bool = False
    mensagem: str | None = None
    criado_em: datetime


class ItemConferenciaLeitura(BaseModel):
    pergunta_id: str
    titulo: str = Field(description="Ex.: 'Onde dói'.")
    pergunta: str
    resposta: str = Field(description="Texto legível da resposta (ex.: 'Peito', '9 de 10').")


class ConferenciaLeitura(BaseModel):
    atendimento_id: int
    itens: list[ItemConferenciaLeitura] = Field(description="Respostas na ordem da triagem.")
    texto: str = Field(description="Resumo completo numa frase, para VLibras e síntese de voz.")
    pode_finalizar: bool = Field(
        description="true = triagem completa e nome/CPF informados; o paciente pode confirmar e finalizar."
    )


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
    nome: str | None = None
    cpf: str | None = None
    alertas: list[str] = []


class AtendimentoResumo(BaseModel):
    id: int
    modo: ModoAcessibilidade
    status: StatusAtendimento
    senha: str | None = None
    nome: str | None = None
    cpf: str | None = Field(default=None, description="Formatado: 123.456.789-09.")
    alertas: list[str] = []
    criado_em: datetime
    finalizado_em: datetime | None = None


class RespostaRotulada(BaseModel):
    pergunta_id: str
    pergunta: str
    valor: Any
    resposta: str = Field(description="Texto legível da opção escolhida (ex.: 'Falta de ar').")
    canal: str | None = None
    da_lia: bool = Field(default=False, description="Pergunta complementar feita pela LIA (IA).")


class QueixaLeitura(BaseModel):
    sintoma: str
    local: str | None = None
    intensidade: int | None = None
    desde_quando: str | None = None


class RelatorioLeitura(BaseModel):
    """Relatório da triagem para a recepção e a enfermagem.

    Não é diagnóstico nem classificação de risco (que é da enfermagem).
    """

    queixa_principal: str
    resumo: str = Field(description="De 2 a 4 frases com o que o paciente relatou.")
    sinais_de_alerta: list[str] = Field(description="Sempre inclui os alertas automáticos da triagem.")
    pontos_a_confirmar: list[str] = Field(description="O que a equipe deve conferir com o paciente.")
    orientacao_recepcao: str = Field(description="Como receber o paciente no guichê.")
    gerado_por: Literal["ia", "regras"] = Field(
        description="`ia` = escrito pela LIA (GPT); `regras` = montado sem IA, só com as respostas."
    )
    modelo: str | None = Field(default=None, description="Modelo de IA usado, quando `gerado_por` = `ia`.")
    gerado_em: datetime

    @classmethod
    def de(cls, relatorio: RelatorioTriagem | None) -> "RelatorioLeitura | None":
        return cls.model_validate(relatorio, from_attributes=True) if relatorio else None


class AtendimentoDetalhe(AtendimentoResumo):
    senha_detalhe: SenhaLeitura | None = None
    resumo: str | None = None
    respostas: list[RespostaRotulada]
    queixa: QueixaLeitura | None = None
    relatorio: RelatorioLeitura | None = Field(
        default=None, description="null enquanto o relatório é preparado (sai segundos depois da senha)."
    )


class Chamada(BaseModel):
    senha: SenhaLeitura
    atendimento_id: int | None = None
    modo: ModoAcessibilidade | None = None
    nome: str | None = None
    cpf: str | None = None
    alertas: list[str] = []
    resumo: str | None = None
    relatorio: RelatorioLeitura | None = None


class SenhaStatusAtualizar(BaseModel):
    status: StatusSenha


# --- Amostras de Libras (treino do reconhecimento) --------------------------


class AmostraLia(BaseModel):
    """Uma gravação de sinal no formato do front (`lia-raw-1`). Os nomes dos campos seguem o
    arquivo de dataset do front, para o totem importar a resposta sem conversão."""

    id: str
    gloss: str = Field(description="Glosa em maiúsculas, ex.: 'DOR'.")
    source: str = Field(description="De onde veio: 'vlibras' para o avatar do VLibras.")
    signer: str = Field(description="Quem sinalizou, ex.: 'vlibras-hosana'.")
    createdAt: str
    origin: str | None = None
    format: Literal["lia-raw-1"] = "lia-raw-1"
    width: int
    height: int
    frames: list[list[float]] = Field(description="152 números por quadro (tempo, flags, tronco e mãos).")
    quality: dict[str, float] = {}


class EnvioAmostras(BaseModel):
    amostras: list[dict[str, Any]] = Field(
        description="Até 100 amostras no formato de `AmostraLia`. Cada uma é validada separadamente."
    )


class AmostraRecusada(BaseModel):
    indice: int = Field(description="Posição da amostra na lista enviada.")
    motivo: str


class EnvioAmostrasResultado(BaseModel):
    adicionadas: int
    ignoradas: int = Field(description="Já estavam no servidor (mesmo id).")
    invalidas: list[AmostraRecusada] = []


class DatasetLia(BaseModel):
    """Mesmo formato do arquivo exportado pelo front: dá para passar direto a `dataset.import()`."""

    kind: Literal["lia-dataset"] = "lia-dataset"
    version: Literal[1] = 1
    format: Literal["lia-raw-1"] = "lia-raw-1"
    exportedAt: datetime
    cursor: int = Field(description="Use em `depois_de` para buscar só o que chegou depois.")
    tem_mais: bool = Field(description="true = há mais amostras; peça de novo com `depois_de=cursor`.")
    samples: list[AmostraLia]


class ResumoAmostrasLeitura(BaseModel):
    total: int
    por_glosa: dict[str, int]
    por_fonte: dict[str, int]
    por_sinalizante: dict[str, int]


class RemocaoAmostras(BaseModel):
    removidas: int
