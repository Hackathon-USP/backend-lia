"""Casos de uso de senhas avulsas: emitir e consultar. A numeração reinicia a cada dia, por tipo."""

from datetime import datetime

from app.application.relogio import agora_local
from app.domain.entidades import Senha
from app.domain.enums import TipoSenha
from app.domain.erros import SenhaNaoEncontrada
from app.domain.repositorios import UnidadeDeTrabalho


def emitir_sem_commit(uow: UnidadeDeTrabalho, tipo: TipoSenha, agora: datetime) -> Senha:
    """Emite dentro da transação de quem chamou (usado também ao finalizar a triagem)."""
    numero = uow.senhas.proximo_numero(agora.date(), tipo)
    return uow.senhas.adicionar(Senha.emitir(tipo, numero, agora))


class ServicoSenhas:
    def __init__(self, uow: UnidadeDeTrabalho):
        self.uow = uow

    def emitir(self, tipo: TipoSenha, agora: datetime | None = None) -> Senha:
        senha = emitir_sem_commit(self.uow, tipo, agora or agora_local())
        self.uow.commit()
        return senha

    def obter_do_dia(self, codigo: str, agora: datetime | None = None) -> Senha:
        """Senha emitida hoje com esse código (maiúsculas ou minúsculas). Levanta SenhaNaoEncontrada."""
        data_ref = (agora or agora_local()).date()
        senha = self.uow.senhas.buscar_do_dia(codigo.upper(), data_ref)
        if senha is None:
            raise SenhaNaoEncontrada
        return senha
