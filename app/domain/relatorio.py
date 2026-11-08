"""Relatório da triagem para a recepção e a enfermagem.

Gerado ao finalizar o atendimento. Com IA, a LIA escreve o relatório a partir das
respostas; sem IA (ou se ela falhar), sai um relatório por regras com as mesmas
informações. Nos dois casos:
- nome e CPF nunca vão para a IA (o contexto só tem as respostas da triagem);
- não há diagnóstico nem classificação de risco, que é da enfermagem;
- os alertas das regras fixas sempre aparecem, a IA só pode acrescentar.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from app.domain.conferencia import resposta_legivel
from app.domain.enums import ModoAcessibilidade
from app.domain.perguntas_da_lia import MAX_PERGUNTAS
from app.domain.resumo import DESCRICAO_MODO, gerar_alertas
from app.domain.triagem import OrigemPergunta, Pergunta, buscar, posicao_no_fluxo

CANAL_LEGIVEL = {
    ModoAcessibilidade.libras.value: "Libras",
    ModoAcessibilidade.voz.value: "voz",
    ModoAcessibilidade.toque.value: "toque",
}
CANAIS_COM_RECONHECIMENTO = (ModoAcessibilidade.libras.value, ModoAcessibilidade.voz.value)


@dataclass(frozen=True)
class RespostaDoPaciente:
    pergunta_id: str
    titulo: str  # "Onde dói"
    pergunta: str  # "Onde é a dor?"
    resposta: str  # "Peito", "9 de 10"
    canal: str | None  # libras | voz | toque
    da_lia: bool  # pergunta complementar feita pela LIA


@dataclass(frozen=True)
class ContextoTriagem:
    """Tudo que a IA recebe sobre o atendimento. Não inclui nome nem CPF."""

    modo: ModoAcessibilidade
    respostas: tuple[RespostaDoPaciente, ...]
    alertas: tuple[str, ...]  # das regras fixas e das perguntas da LIA
    perguntas_da_lia: int  # quantas a LIA já fez
    max_perguntas_da_lia: int = MAX_PERGUNTAS


@dataclass(frozen=True)
class ConteudoRelatorio:
    queixa_principal: str
    resumo: str
    sinais_de_alerta: tuple[str, ...]
    pontos_a_confirmar: tuple[str, ...]
    orientacao_recepcao: str


def montar_contexto(
    modo: ModoAcessibilidade,
    respostas: dict[str, Any],
    canais: dict[str, str],
    extras: Sequence[Pergunta],
) -> ContextoTriagem:
    """Respostas na ordem da triagem, com textos legíveis, e os alertas por regra."""
    itens = []
    for pergunta_id in sorted(respostas, key=lambda pid: posicao_no_fluxo(pid, extras)):
        pergunta = buscar(pergunta_id, extras)
        if pergunta is None:
            continue
        itens.append(
            RespostaDoPaciente(
                pergunta_id=pergunta_id,
                titulo=pergunta.titulo,
                pergunta=pergunta.texto,
                resposta=resposta_legivel(pergunta, respostas[pergunta_id]),
                canal=canais.get(pergunta_id),
                da_lia=pergunta.origem == OrigemPergunta.lia,
            )
        )
    return ContextoTriagem(
        modo=modo,
        respostas=tuple(itens),
        alertas=tuple(gerar_alertas(respostas, extras)),
        perguntas_da_lia=len(extras),
    )


def juntar_alertas(*listas: Sequence[str]) -> list[str]:
    """Une listas de alertas na ordem, sem repetir (ignora maiúsculas e espaços)."""
    vistos: set[str] = set()
    unidos = []
    for alerta in (a.strip() for lista in listas for a in lista):
        chave = alerta.casefold()
        if alerta and chave not in vistos:
            vistos.add(chave)
            unidos.append(alerta)
    return unidos


# --- Relatório por regras (sem IA) --------------------------------------------


def _queixa_principal(contexto: ContextoTriagem) -> str:
    por_id = {r.pergunta_id: r for r in contexto.respostas}
    if "sintoma" not in por_id:
        motivo = por_id.get("motivo")
        return f"Motivo da vinda: {motivo.resposta}" if motivo else "Triagem sem queixa informada"
    queixa = por_id["sintoma"].resposta
    if "local_dor" in por_id:
        queixa += f" ({por_id['local_dor'].resposta.lower()})"
    detalhes = [por_id[pid].resposta.lower() for pid in ("desde_quando",) if pid in por_id]
    if "intensidade" in por_id:
        detalhes.append(f"intensidade {por_id['intensidade'].resposta}")
    return ", ".join([queixa, *detalhes])


def _pontos_a_confirmar(contexto: ContextoTriagem) -> list[str]:
    pontos = []
    canais = {r.canal for r in contexto.respostas}
    if canais & set(CANAIS_COM_RECONHECIMENTO):
        pontos.append(
            "Parte das respostas veio por reconhecimento automático de Libras ou voz: confirmar com o paciente."
        )
    if any(r.resposta in ("Outro", "Outro lugar") for r in contexto.respostas):
        pontos.append("Paciente escolheu “Outro” em alguma resposta: perguntar o que sente.")
    if any(r.resposta == "Não sei" for r in contexto.respostas):
        pontos.append("Paciente respondeu “Não sei” a alguma pergunta.")
    return pontos


def relatorio_por_regras(contexto: ContextoTriagem) -> ConteudoRelatorio:
    """Relatório montado só com as respostas, para quando a IA não está disponível."""
    linhas = [f"{r.titulo}: {r.resposta}." for r in contexto.respostas]
    resumo = " ".join(["Triagem feita no totem.", *linhas]) if linhas else "Nenhuma resposta registrada."
    orientacao = DESCRICAO_MODO[contexto.modo]
    if contexto.alertas:
        orientacao += " Há sinais de alerta: avisar a enfermagem para o acolhimento o quanto antes."
    return ConteudoRelatorio(
        queixa_principal=_queixa_principal(contexto),
        resumo=resumo,
        sinais_de_alerta=contexto.alertas,
        pontos_a_confirmar=tuple(_pontos_a_confirmar(contexto)),
        orientacao_recepcao=orientacao,
    )
