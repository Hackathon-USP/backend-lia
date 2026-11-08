"""Resumo do paciente para a recepção, gerado por regras/templates.

Não faz diagnóstico nem classificação de risco: só organiza o que o paciente
informou e destaca sinais que pedem atenção imediata da equipe.
"""

from typing import Any

from app.conteudo.fluxo import POR_ID
from app.models import ModoAcessibilidade

DESCRICAO_MODO = {
    ModoAcessibilidade.libras: "Paciente surdo — comunica-se em Libras. Providenciar intérprete ou recurso visual.",
    ModoAcessibilidade.voz: "Paciente usou voz — possível deficiência visual. Chamar pelo nome/voz e oferecer auxílio.",
    ModoAcessibilidade.toque: "Paciente usou a tela de toque.",
}


def gerar_alertas(respostas: dict[str, Any]) -> list[str]:
    alertas = []
    if respostas.get("sintoma") == "dor" and respostas.get("local_dor") == "peito":
        alertas.append("Dor no peito")
    if respostas.get("sintoma") == "falta_de_ar":
        alertas.append("Falta de ar")
    intensidade = respostas.get("intensidade")
    if isinstance(intensidade, int) and intensidade >= 8:
        alertas.append(f"Intensidade alta ({intensidade}/10)")
    return alertas


def _rotulo(pergunta_id: str, respostas: dict[str, Any]) -> str:
    return POR_ID[pergunta_id].rotulo_de(respostas[pergunta_id])


def gerar_resumo(
    codigo_senha: str,
    modo: ModoAcessibilidade,
    respostas: dict[str, Any],
    alertas: list[str],
    nome: str | None = None,
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
        queixa = _rotulo("sintoma", respostas)
        if "local_dor" in respostas:
            queixa += f" ({_rotulo('local_dor', respostas).lower()})"
        linhas.append(f"Queixa principal: {queixa}")
    if "intensidade" in respostas:
        linhas.append(f"Intensidade: {respostas['intensidade']}/10")
    if "desde_quando" in respostas:
        linhas.append(f"Duração: {_rotulo('desde_quando', respostas)}")
    if respostas.get("prioridade") == "sim":
        linhas.append("Declarou direito a atendimento prioritário.")
    return "\n".join(linhas)
