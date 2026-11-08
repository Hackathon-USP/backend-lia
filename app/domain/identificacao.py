"""Regras de nome e CPF do paciente (validação e formatação). Sem acesso a banco."""

import re

from app.domain.erros import IdentificacaoInvalida

TAMANHO_CPF = 11
TAMANHO_MINIMO_NOME = 2
TAMANHO_MAXIMO_NOME = 120


# --- CPF ----------------------------------------------------------------------


def apenas_digitos(texto: str | None) -> str:
    """'123.456.789-09' -> '12345678909'."""
    return re.sub(r"\D", "", texto or "")


def _digito_verificador(digitos: str) -> int:
    """Dígito que vem depois de `digitos` (9 ou 10 dígitos), pelo módulo 11 da Receita."""
    pesos = range(len(digitos) + 1, 1, -1)
    soma = sum(int(digito) * peso for digito, peso in zip(digitos, pesos))
    return (soma * 10) % 11 % 10


def _cpf_valido(digitos: str) -> bool:
    if digitos == digitos[0] * TAMANHO_CPF:  # 000.000.000-00, 111.111.111-11...
        return False
    return all(
        _digito_verificador(digitos[:posicao]) == int(digitos[posicao])
        for posicao in (9, 10)
    )


def normalizar_cpf(texto: str) -> str:
    """'123.456.789-09' -> '12345678909'. Levanta IdentificacaoInvalida se o CPF for inválido."""
    digitos = apenas_digitos(texto)
    if len(digitos) != TAMANHO_CPF:
        raise IdentificacaoInvalida("CPF deve ter 11 dígitos")
    if not _cpf_valido(digitos):
        raise IdentificacaoInvalida("CPF inválido")
    return digitos


def formatar_cpf(cpf: str) -> str:
    """'12345678909' -> '123.456.789-09'."""
    return f"{cpf[:3]}.{cpf[3:6]}.{cpf[6:9]}-{cpf[9:]}"


# --- Nome ---------------------------------------------------------------------


def normalizar_nome(texto: str) -> str:
    """Tira espaços extras. Levanta IdentificacaoInvalida se não parecer um nome."""
    nome = " ".join((texto or "").split())
    tamanho_ok = TAMANHO_MINIMO_NOME <= len(nome) <= TAMANHO_MAXIMO_NOME
    tem_letra = any(caractere.isalpha() for caractere in nome)
    if not (tamanho_ok and tem_letra):
        raise IdentificacaoInvalida("Informe o nome completo")
    return nome
