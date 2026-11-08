"""Amostras de Libras para treinar o reconhecimento de sinais do totem.

Cada amostra é uma gravação de um sinal no formato `lia-raw-1` do módulo de
reconhecimento do front (`src/lib/libras`): por quadro, 152 números com os pontos
das mãos e do tronco. O treino acontece no navegador; o back só guarda as amostras
e as devolve para que todos os totens usem o mesmo conjunto.

O caso principal são as amostras geradas com o avatar do VLibras (fonte `vlibras`):
o front faz o avatar sinalizar cada glosa e extrai os pontos do vídeo dele.
"""

import math
import unicodedata
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from app.domain.erros import DadosInvalidos

FORMATO = "lia-raw-1"
NUMEROS_POR_QUADRO = 152
# 20 s a 30 quadros por segundo: bem mais que qualquer sinal isolado.
MAX_QUADROS = 600
MAX_GLOSA = 60
MAX_TEXTO = 200

# Posições dentro de cada quadro (ver src/lib/libras/raw-frame.ts no front).
_TEMPO = 0
_FLAGS = 1
_FLAG_CORPO = 1
_FLAG_MAOS = 2 | 4


class AmostraInvalida(DadosInvalidos):
    mensagem_padrao = "Amostra inválida"


def normalizar_glosa(texto: str) -> str:
    """Mesma padronização do front: maiúsculas, acentos em NFC e espaços simples."""
    return " ".join(unicodedata.normalize("NFC", texto).upper().split())


def calcular_qualidade(quadros: list[list[float]]) -> dict[str, float]:
    """Indicadores recalculados a partir dos quadros (nunca confiamos no que vem de fora)."""
    n = len(quadros)
    com_maos = sum(1 for q in quadros if int(q[_FLAGS]) & _FLAG_MAOS)
    com_corpo = sum(1 for q in quadros if int(q[_FLAGS]) & _FLAG_CORPO)
    duracao = quadros[-1][_TEMPO] - quadros[0][_TEMPO]
    return {
        "handsRatio": round(com_maos / n, 3),
        "bodyRatio": round(com_corpo / n, 3),
        "durationMs": duracao,
        "fps": round((n - 1) * 1000 / duracao, 1) if duracao > 0 else 0,
    }


@dataclass
class AmostraLibras:
    id: str  # UUID gerado no front: o mesmo id nunca é gravado duas vezes
    glosa: str
    fonte: str
    sinalizante: str
    formato: str
    largura: int
    altura: int
    quadros: list[list[float]]
    gravada_em: str  # ISO 8601, como o front mandou ("createdAt")
    recebida_em: datetime
    qualidade: dict[str, float] = field(default_factory=dict)
    origem: str | None = None
    seq: int | None = None  # ordem de chegada no servidor (cursor da sincronização)


def _texto(dados: Mapping[str, Any], chave: str, obrigatorio: bool = True) -> str | None:
    valor = dados.get(chave)
    if valor is None and not obrigatorio:
        return None
    if not isinstance(valor, str) or not valor.strip():
        raise AmostraInvalida(f"{chave} ausente")
    valor = valor.strip()
    if len(valor) > MAX_TEXTO:
        raise AmostraInvalida(f"{chave} longo demais")
    return valor


def _quadros(valor: Any) -> list[list[float]]:
    if not isinstance(valor, list) or not valor:
        raise AmostraInvalida("sem quadros")
    if len(valor) > MAX_QUADROS:
        raise AmostraInvalida(f"mais de {MAX_QUADROS} quadros")
    quadros = []
    for i, quadro in enumerate(valor):
        if not isinstance(quadro, list) or len(quadro) != NUMEROS_POR_QUADRO:
            raise AmostraInvalida(f"quadro {i} com tamanho errado")
        if not all(
            isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v) for v in quadro
        ):
            raise AmostraInvalida(f"quadro {i} com valor inválido")
        quadros.append([float(v) for v in quadro])
    return quadros


def _dimensao(dados: Mapping[str, Any], chave: str) -> int:
    valor = dados.get(chave)
    if isinstance(valor, bool) or not isinstance(valor, (int, float)) or not 0 < valor <= 10_000:
        raise AmostraInvalida("width/height inválidos")
    return int(valor)


def _data_iso(valor: Any, padrao: datetime) -> str:
    if isinstance(valor, str):
        try:
            datetime.fromisoformat(valor.replace("Z", "+00:00"))
            return valor
        except ValueError:
            pass
    return padrao.isoformat()


def validar_amostra(dados: Any, fontes_aceitas: frozenset[str], agora: datetime) -> AmostraLibras:
    """Confere uma amostra no formato do front (`id`, `gloss`, `source`, `signer`, `frames`...).

    Levanta AmostraInvalida com o motivo. `fontes_aceitas` limita o que o servidor guarda:
    gravações de pessoas são dados pessoais (LGPD) e as do V-LIBRASIL não podem ser
    redistribuídas, então por padrão só entra o avatar do VLibras.
    """
    if not isinstance(dados, Mapping):
        raise AmostraInvalida("não é um objeto")
    fonte = dados.get("source")
    if fonte not in fontes_aceitas:
        aceitas = ", ".join(sorted(fontes_aceitas)) or "nenhuma"
        raise AmostraInvalida(f"fonte não aceita pelo servidor: {fonte!r} (aceitas: {aceitas})")
    if dados.get("format") != FORMATO:
        raise AmostraInvalida(f"formato não suportado: {dados.get('format')!r}")

    glosa = normalizar_glosa(_texto(dados, "gloss"))
    if len(glosa) > MAX_GLOSA:
        raise AmostraInvalida("glosa longa demais")
    quadros = _quadros(dados.get("frames"))
    return AmostraLibras(
        id=_texto(dados, "id"),
        glosa=glosa,
        fonte=fonte,
        sinalizante=_texto(dados, "signer"),
        origem=_texto(dados, "origin", obrigatorio=False),
        formato=FORMATO,
        largura=_dimensao(dados, "width"),
        altura=_dimensao(dados, "height"),
        quadros=quadros,
        qualidade=calcular_qualidade(quadros),
        gravada_em=_data_iso(dados.get("createdAt"), agora),
        recebida_em=agora,
    )
