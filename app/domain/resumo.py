"""Resumo do paciente para a recepção, gerado por regras/templates.

Não faz diagnóstico nem classificação de risco: só organiza o que o paciente
informou e destaca sinais que pedem atenção imediata da equipe.
"""

from collections.abc import Sequence
from typing import Any

from app.domain.enums import ModoAcessibilidade
from app.domain.perguntas_da_lia import alertas_das_respostas
from app.domain.triagem import POR_ID, Pergunta

DESCRICAO_MODO = {
    ModoAcessibilidade.libras: "Paciente surdo — comunica-se em Libras. Providenciar intérprete ou recurso visual.",
    ModoAcessibilidade.voz: "Paciente usou voz — possível deficiência visual. Chamar pelo nome/voz e oferecer auxílio.",
    ModoAcessibilidade.toque: "Paciente usou a tela de toque.",
}


INTENSIDADE_ALTA = 8


def gerar_alertas(respostas: dict[str, Any], extras: Sequence[Pergunta] = ()) -> list[str]:
    """Sinais que a recepção deve ver primeiro. Não é classificação de risco.

    Inclui os alertas das opções escolhidas nas perguntas da LIA (`extras`).
    """
    alertas = []
    if respostas.get("sintoma") == "dor" and respostas.get("local_dor") == "peito":
        alertas.append("Dor no peito")
    if respostas.get("sintoma") == "falta_de_ar":
        alertas.append("Falta de ar")
    intensidade = respostas.get("intensidade")
    if isinstance(intensidade, int) and intensidade >= INTENSIDADE_ALTA:
        alertas.append(f"Intensidade alta ({intensidade}/10)")
    return alertas + [a for a in alertas_das_respostas(respostas, extras) if a not in alertas]


def _rotulo(pergunta_id: str, respostas: dict[str, Any]) -> str:
    return POR_ID[pergunta_id].rotulo_de(respostas[pergunta_id])


def _queixa_principal(respostas: dict[str, Any]) -> str:
    """'Dor (peito)', ou só 'Febre' quando não há local."""
    queixa = _rotulo("sintoma", respostas)
    if "local_dor" in respostas:
        queixa += f" ({_rotulo('local_dor', respostas).lower()})"
    return queixa


def gerar_resumo(
    codigo_senha: str,
    modo: ModoAcessibilidade,
    respostas: dict[str, Any],
    alertas: list[str],
    nome: str | None = None,
    extras: Sequence[Pergunta] = (),
) -> str:
    linhas = [f"Senha: {codigo_senha}"]
    if nome:
        linhas.append(f"Paciente: {nome}")
    linhas.append(f"Comunicação: {DESCRICAO_MODO[modo]}")
    if alertas:
        linhas.append("ATENÇÃO: " + "; ".join(alertas))
    if "motivo" in respostas:
        linhas.append(f"Motivo: {_rotulo('motivo', respostas)}")
    if "sintoma" in respostas:
        linhas.append(f"Queixa principal: {_queixa_principal(respostas)}")
    if "intensidade" in respostas:
        linhas.append(f"Intensidade: {respostas['intensidade']}/10")
    if "desde_quando" in respostas:
        linhas.append(f"Duração: {_rotulo('desde_quando', respostas)}")
    if respostas.get("prioridade") == "sim":
        linhas.append("Declarou direito a atendimento prioritário.")
    for pergunta in extras:
        if pergunta.id in respostas:
            linhas.append(f"{pergunta.titulo}: {pergunta.rotulo_de(respostas[pergunta.id])}")
    return "\n".join(linhas)
