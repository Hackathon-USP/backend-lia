"""Perguntas complementares da LIA, feitas depois das perguntas fixas da triagem.

A IA sugere a pergunta (texto e opções curtas) a partir do que o paciente já
respondeu. Este módulo transforma a sugestão numa `Pergunta` comum, com ids
estáveis e opções que funcionam em Libras, voz e toque, e decide quando ainda
cabe perguntar. Daí em diante as respostas são validadas e gravadas como as das
perguntas fixas.

Sem IA (chave não configurada, fora do ar ou demorando), a triagem termina nas
perguntas fixas, como antes.
"""

import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from app.domain.enums import ModoAcessibilidade
from app.domain.triagem import Opcao, OrigemPergunta, Pergunta, TipoPergunta, normalizar, proxima_pergunta

MAX_PERGUNTAS = 3
# Consulta marcada, exame e retorno não precisam de mais detalhes na triagem.
MOTIVOS_COM_PERGUNTAS = ("sintoma", "outro")
MIN_OPCOES = 2
MAX_OPCOES = 4  # sugeridas pela IA; "Não sei" é acrescentada depois
NAO_SEI = "Não sei"
NAO_SEI_ID = "nao_sei"

LIMITE_TEXTO = 200
LIMITE_TITULO = 40
LIMITE_ROTULO = 40
LIMITE_ALERTA = 80


class SugestaoInvalida(ValueError):
    """A IA sugeriu algo que não dá para perguntar no totem (sem texto, opções de menos...)."""


@dataclass(frozen=True)
class OpcaoSugerida:
    rotulo: str
    # Rótulo do alerta para a recepção se o paciente escolher esta opção (None = não é alerta).
    alerta: str | None = None


@dataclass(frozen=True)
class PerguntaSugerida:
    texto: str
    titulo: str  # rótulo curto para o resumo (ex.: "Suor frio")
    opcoes: tuple[OpcaoSugerida, ...]


def _limpar(texto: str | None, limite: int) -> str:
    return re.sub(r"\s+", " ", texto or "").strip()[:limite].strip()


def criar_pergunta(sugestao: PerguntaSugerida, ordem: int) -> Pergunta:
    """A `ordem`-ésima pergunta da LIA neste atendimento (id `lia_<ordem>`).

    Levanta SugestaoInvalida se a sugestão não servir para o totem.
    """
    texto = _limpar(sugestao.texto, LIMITE_TEXTO)
    if not texto:
        raise SugestaoInvalida("Pergunta sem texto")
    titulo = _limpar(sugestao.titulo, LIMITE_TITULO) or f"Pergunta da LIA {ordem}"

    opcoes: list[Opcao] = []
    alertas: dict[str, str] = {}
    for sugerida in sugestao.opcoes:
        rotulo = _limpar(sugerida.rotulo, LIMITE_ROTULO)
        opcao_id = normalizar(rotulo).lower()
        if not opcao_id or opcao_id in {o.id for o in opcoes}:
            continue
        if len(opcoes) == MAX_OPCOES and opcao_id != NAO_SEI_ID:
            continue
        # Palavra única ("Sim", "Não") vira o nome do sinal que a câmera reconhece.
        sinais = (normalizar(rotulo),) if " " not in rotulo else ()
        opcoes.append(Opcao(opcao_id, rotulo, sinais))
        alerta = _limpar(sugerida.alerta, LIMITE_ALERTA)
        if alerta:
            alertas[opcao_id] = alerta

    if len([o for o in opcoes if o.id != NAO_SEI_ID]) < MIN_OPCOES:
        raise SugestaoInvalida("A pergunta precisa de pelo menos duas opções")
    if not any(o.id == NAO_SEI_ID for o in opcoes):
        opcoes.append(Opcao(NAO_SEI_ID, NAO_SEI))

    return Pergunta(
        id=f"lia_{ordem}",
        texto=texto,
        titulo=titulo,
        tipo=TipoPergunta.opcoes,
        opcoes=tuple(opcoes),
        origem=OrigemPergunta.lia,
        alertas=alertas,
    )


def pode_perguntar_mais(respostas: dict[str, Any], modo: ModoAcessibilidade, extras: Sequence[Pergunta]) -> bool:
    """Perguntas fixas respondidas, motivo que pede detalhes e ainda dentro do limite."""
    return (
        respostas.get("motivo") in MOTIVOS_COM_PERGUNTAS
        and len(extras) < MAX_PERGUNTAS
        and proxima_pergunta(respostas, modo, extras) is None
    )


def alertas_das_respostas(respostas: dict[str, Any], extras: Sequence[Pergunta]) -> list[str]:
    """Alertas das opções escolhidas nas perguntas da LIA."""
    return [p.alertas[respostas[p.id]] for p in extras if respostas.get(p.id) in p.alertas]


# --- Gravação (coluna JSON) ---------------------------------------------------


def para_dict(pergunta: Pergunta) -> dict[str, Any]:
    return {
        "id": pergunta.id,
        "texto": pergunta.texto,
        "titulo": pergunta.titulo,
        "opcoes": [{"id": o.id, "rotulo": o.rotulo, "sinais": list(o.sinais)} for o in pergunta.opcoes],
        "alertas": dict(pergunta.alertas),
    }


def de_dict(dados: dict[str, Any]) -> Pergunta:
    return Pergunta(
        id=dados["id"],
        texto=dados["texto"],
        titulo=dados["titulo"],
        tipo=TipoPergunta.opcoes,
        opcoes=tuple(Opcao(o["id"], o["rotulo"], tuple(o.get("sinais", ()))) for o in dados["opcoes"]),
        origem=OrigemPergunta.lia,
        alertas=dict(dados.get("alertas", {})),
    )
