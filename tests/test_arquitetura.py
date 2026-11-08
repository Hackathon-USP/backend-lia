"""Garante a regra de dependência da Clean Architecture: as camadas só importam para dentro.

    api -> application -> domain <- persistence
"""

import ast
from pathlib import Path

import pytest

APP = Path(__file__).resolve().parent.parent / "app"

PROIBIDOS = {
    "domain": ("app.application", "app.persistence", "app.api", "app.config", "fastapi", "sqlmodel", "sqlalchemy"),
    "application": ("app.persistence", "app.api", "fastapi", "sqlmodel", "sqlalchemy"),
    "persistence": ("app.application", "app.api", "fastapi"),
}


def _imports(arquivo: Path) -> set[str]:
    modulos = set()
    for no in ast.walk(ast.parse(arquivo.read_text(encoding="utf-8"))):
        if isinstance(no, ast.Import):
            modulos.update(alias.name for alias in no.names)
        elif isinstance(no, ast.ImportFrom) and no.module:
            modulos.add(no.module)
    return modulos


@pytest.mark.parametrize("camada", sorted(PROIBIDOS))
def test_camada_nao_importa_camadas_externas(camada):
    violacoes = [
        f"{arquivo.relative_to(APP)} importa {modulo}"
        for arquivo in sorted((APP / camada).rglob("*.py"))
        for modulo in _imports(arquivo)
        if any(modulo == p or modulo.startswith(p + ".") for p in PROIBIDOS[camada])
    ]
    assert not violacoes, "\n".join(violacoes)
