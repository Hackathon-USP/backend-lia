"""Perguntas da triagem guiada.

Todas têm respostas fechadas (lista de opções ou escala numérica): o vocabulário
pequeno facilita o reconhecimento em Libras e por voz feito no front.

Cada opção lista os `sinais` aceitos: nomes (glosas) que o reconhecedor de Libras
do front pode devolver, e palavras que a fala pode produzir. A comparação ignora
maiúsculas, acentos e espaços/hífens, então "CABEÇA", "cabeca" e "Cabeça" valem igual.
"""

import re
import unicodedata
from collections.abc import Sequence
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from app.domain.enums import ModoAcessibilidade
from app.domain.erros import RespostaInvalida


class TipoPergunta(str, Enum):
    opcoes = "opcoes"
    escala = "escala"


class OrigemPergunta(str, Enum):
    triagem = "triagem"  # pergunta fixa, definida abaixo
    lia = "lia"  # pergunta complementar criada pela LIA (IA) para este paciente


def normalizar(texto: str) -> str:
    """'Falta de ar' -> 'FALTA_DE_AR'; 'CABEÇA' -> 'CABECA'."""
    sem_acento = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    return re.sub(r"[^A-Z0-9]+", "_", sem_acento.upper()).strip("_")


@dataclass(frozen=True)
class Opcao:
    id: str
    rotulo: str
    sinais: tuple[str, ...] = ()

    def aceita(self, valor_normalizado: str) -> bool:
        candidatos = (self.id, self.rotulo, *self.sinais)
        return valor_normalizado in {normalizar(c) for c in candidatos}


@dataclass(frozen=True)
class Pergunta:
    id: str
    texto: str
    titulo: str  # rótulo curto usado no resumo de conferência (ex.: "Onde dói")
    tipo: TipoPergunta
    opcoes: tuple[Opcao, ...] = ()
    minimo: int | None = None
    maximo: int | None = None
    # Só aparece se a resposta de `pergunta_id` estiver em `valores`.
    mostrar_se: dict[str, tuple[str, ...]] = field(default_factory=dict)
    # Não aparece para estes modos de acessibilidade.
    pular_para_modos: tuple[ModoAcessibilidade, ...] = ()
    origem: OrigemPergunta = OrigemPergunta.triagem
    # {opcao_id: alerta}: escolher a opção gera este alerta para a recepção.
    alertas: dict[str, str] = field(default_factory=dict)

    def rotulo_de(self, valor: Any) -> str:
        for opcao in self.opcoes:
            if opcao.id == valor:
                return opcao.rotulo
        return str(valor)


SIM_NAO = (Opcao("sim", "Sim", ("SIM",)), Opcao("nao", "Não", ("NAO",)))

NUMEROS_POR_EXTENSO = {
    "ZERO": 0, "NADA": 0, "UM": 1, "UMA": 1, "DOIS": 2, "DUAS": 2, "TRES": 3,
    "QUATRO": 4, "CINCO": 5, "SEIS": 6, "MEIA": 6, "SETE": 7, "OITO": 8,
    "NOVE": 9, "DEZ": 10,
}

PERGUNTAS: tuple[Pergunta, ...] = (
    Pergunta(
        id="motivo",
        titulo="Motivo da vinda",
        texto="Qual o motivo da sua vinda hoje?",
        tipo=TipoPergunta.opcoes,
        opcoes=(
            Opcao("consulta", "Consulta marcada", ("CONSULTA", "MEDICO")),
            Opcao("exame", "Exame", ("EXAME",)),
            Opcao("retorno", "Retorno", ("RETORNO", "VOLTAR")),
            Opcao("sintoma", "Estou sentindo algo", ("SENTIR", "DOENTE", "MAL")),
            Opcao("outro", "Outro", ("OUTRO",)),
        ),
    ),
    Pergunta(
        id="sintoma",
        titulo="O que sente",
        texto="O que você está sentindo?",
        tipo=TipoPergunta.opcoes,
        opcoes=(
            Opcao("dor", "Dor", ("DOR", "DOER")),
            Opcao("febre", "Febre", ("FEBRE", "QUENTE")),
            Opcao("falta_de_ar", "Falta de ar", ("RESPIRAR", "AR", "CANSACO")),
            Opcao("tosse", "Tosse", ("TOSSE", "TOSSIR")),
            Opcao("tontura", "Tontura", ("TONTURA", "TONTO")),
            Opcao("vomito", "Vômito", ("VOMITO", "VOMITAR", "ENJOO")),
            Opcao("outro", "Outro", ("OUTRO",)),
        ),
        mostrar_se={"motivo": ("sintoma",)},
    ),
    Pergunta(
        id="local_dor",
        titulo="Onde dói",
        texto="Onde é a dor?",
        tipo=TipoPergunta.opcoes,
        opcoes=(
            Opcao("cabeca", "Cabeça", ("CABECA",)),
            Opcao("peito", "Peito", ("PEITO", "CORACAO")),
            Opcao("barriga", "Barriga", ("BARRIGA", "ESTOMAGO")),
            Opcao("costas", "Costas", ("COSTAS",)),
            Opcao("outro", "Outro lugar", ("OUTRO",)),
        ),
        mostrar_se={"sintoma": ("dor",)},
    ),
    Pergunta(
        id="intensidade",
        titulo="Intensidade",
        texto="De 0 a 10, quanto está incomodando? 0 é nada e 10 é o pior possível.",
        tipo=TipoPergunta.escala,
        minimo=0,
        maximo=10,
        mostrar_se={"motivo": ("sintoma",)},
    ),
    Pergunta(
        id="desde_quando",
        titulo="Desde quando",
        texto="Desde quando você está assim?",
        tipo=TipoPergunta.opcoes,
        opcoes=(
            Opcao("hoje", "Desde hoje", ("HOJE",)),
            Opcao("1_3_dias", "De 1 a 3 dias", ("ONTEM", "POUCOS_DIAS")),
            Opcao("mais_3_dias", "Mais de 3 dias", ("VARIOS_DIAS", "MUITOS_DIAS")),
            Opcao("mais_1_semana", "Mais de 1 semana", ("SEMANA", "MES")),
        ),
        mostrar_se={"motivo": ("sintoma",)},
    ),
    Pergunta(
        id="prioridade",
        titulo="Atendimento prioritário",
        texto=(
            "Você tem direito a atendimento prioritário? Pessoa com deficiência, "
            "60 anos ou mais, gestante, lactante, com criança de colo ou com autismo."
        ),
        tipo=TipoPergunta.opcoes,
        opcoes=SIM_NAO,
        # Quem usa Libras ou voz já recebe senha preferencial (Lei 10.048/2000).
        pular_para_modos=(ModoAcessibilidade.libras, ModoAcessibilidade.voz),
    ),
)

POR_ID: dict[str, Pergunta] = {p.id: p for p in PERGUNTAS}


def posicao_no_fluxo(pergunta_id: str, extras: Sequence[Pergunta] = ()) -> int:
    """Índice da pergunta na triagem (fixas e depois as da LIA); ids desconhecidos vão para o fim."""
    fluxo = (*PERGUNTAS, *extras)
    for indice, pergunta in enumerate(fluxo):
        if pergunta.id == pergunta_id:
            return indice
    return len(fluxo)


def buscar(pergunta_id: str, extras: Sequence[Pergunta] = ()) -> Pergunta | None:
    """Pergunta fixa ou da LIA com esse id."""
    return POR_ID.get(pergunta_id) or next((p for p in extras if p.id == pergunta_id), None)


def _aplicavel(pergunta: Pergunta, respostas: dict[str, Any], modo: ModoAcessibilidade) -> bool:
    if modo in pergunta.pular_para_modos:
        return False
    return all(respostas.get(pid) in valores for pid, valores in pergunta.mostrar_se.items())


def proxima_pergunta(
    respostas: dict[str, Any], modo: ModoAcessibilidade, extras: Sequence[Pergunta] = ()
) -> Pergunta | None:
    """Primeira pergunta aplicável ainda não respondida, ou None se a triagem acabou.

    As perguntas da LIA (`extras`) só vêm depois de todas as fixas.
    """
    for pergunta in PERGUNTAS:
        if pergunta.id not in respostas and _aplicavel(pergunta, respostas, modo):
            return pergunta
    return next((p for p in extras if p.id not in respostas), None)


def _interpretar_numero(valor: Any) -> int | None:
    """7, "7" ou "SETE" -> 7. None se não for um número reconhecível."""
    if isinstance(valor, int) and not isinstance(valor, bool):
        return valor
    if isinstance(valor, str):
        texto = normalizar(valor)
        if texto.isdigit():
            return int(texto)
        return NUMEROS_POR_EXTENSO.get(texto)
    return None


def _validar_escala(pergunta: Pergunta, valor: Any) -> int:
    numero = _interpretar_numero(valor)
    if numero is None:
        raise RespostaInvalida("Valor deve ser um número inteiro")
    if not (pergunta.minimo <= numero <= pergunta.maximo):
        raise RespostaInvalida(f"Valor deve estar entre {pergunta.minimo} e {pergunta.maximo}")
    return numero


def _validar_opcao(pergunta: Pergunta, valor: Any) -> str:
    normalizado = normalizar(str(valor))
    for opcao in pergunta.opcoes:
        if opcao.aceita(normalizado):
            return opcao.id
    ids = ", ".join(o.id for o in pergunta.opcoes)
    raise RespostaInvalida(f"Opção não reconhecida: {valor!r}. Use uma de: {ids}")


def validar_valor(pergunta: Pergunta, valor: Any) -> int | str:
    """Converte o que o front mandou (id, rótulo, número ou nome do sinal) no valor gravado.

    Levanta RespostaInvalida com uma mensagem amigável se não reconhecer.
    """
    if pergunta.tipo == TipoPergunta.escala:
        return _validar_escala(pergunta, valor)
    return _validar_opcao(pergunta, valor)
