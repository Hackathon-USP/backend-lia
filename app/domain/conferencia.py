"""Resumo das respostas para o próprio paciente conferir antes de receber a senha.

Gerado por template (sem IA generativa): o texto repete exatamente o que foi
respondido, e o front o entrega ao VLibras e à síntese de voz. Nome e CPF ficam
de fora porque a tela do totem é pública.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from app.domain.textos import TEXTOS
from app.domain.triagem import PERGUNTAS, Pergunta, TipoPergunta


@dataclass(frozen=True)
class ItemConferencia:
    pergunta_id: str
    titulo: str
    pergunta: str
    resposta: str


@dataclass(frozen=True)
class Conferencia:
    itens: list[ItemConferencia]
    texto: str  # tudo numa frase só, pronto para VLibras/TTS


def resposta_legivel(pergunta: Pergunta, valor: Any) -> str:
    """'Peito' para uma opção, '9 de 10' para a escala."""
    if pergunta.tipo == TipoPergunta.escala:
        return f"{valor} de {pergunta.maximo}"
    return pergunta.rotulo_de(valor)


def gerar_conferencia(respostas: dict[str, Any], extras: Sequence[Pergunta] = ()) -> Conferencia:
    """Itens na ordem da triagem (fixas e depois as da LIA) e o texto falado:
    'Vamos conferir... Motivo da vinda: Exame. ...'."""
    itens = [
        ItemConferencia(
            pergunta_id=pergunta.id,
            titulo=pergunta.titulo,
            pergunta=pergunta.texto,
            resposta=resposta_legivel(pergunta, respostas[pergunta.id]),
        )
        for pergunta in (*PERGUNTAS, *extras)
        if pergunta.id in respostas
    ]
    frases = [TEXTOS["conferir_inicio"], *(f"{i.titulo}: {i.resposta}." for i in itens), TEXTOS["conferir_fim"]]
    return Conferencia(itens=itens, texto=" ".join(frases))
