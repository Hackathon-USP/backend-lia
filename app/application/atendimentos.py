"""Casos de uso da tela do paciente: abrir a triagem, responder, identificar e finalizar."""

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from app.application.relogio import agora_local
from app.application.senhas import emitir_sem_commit
from app.domain.conferencia import Conferencia, gerar_conferencia
from app.domain.entidades import Atendimento, Identificacao, Queixa, Senha
from app.domain.enums import ModoAcessibilidade
from app.domain.erros import AtendimentoNaoEncontrado, IdentificacaoPendente, TriagemIncompleta
from app.domain.repositorios import UnidadeDeTrabalho
from app.domain.textos import TEXTOS
from app.domain.triagem import Pergunta


@dataclass
class EstadoAtendimento:
    """O que a tela do paciente precisa para desenhar o próximo passo."""

    atendimento: Atendimento
    proxima_pergunta: Pergunta | None
    identificado: bool
    repetir: bool = False  # a última resposta não foi entendida; pedir de novo


@dataclass
class ConferenciaAtendimento:
    """Resumo das respostas para o paciente conferir antes de finalizar."""

    atendimento: Atendimento
    conferencia: Conferencia
    pode_finalizar: bool  # triagem completa e nome/CPF informados


@dataclass
class Finalizacao:
    atendimento: Atendimento
    senha: Senha
    mensagem_final: str


def _soletrar_senha(codigo: str) -> str:
    """'P012' -> 'P 0 1 2': fica mais claro no TTS e no VLibras (datilologia)."""
    return " ".join(codigo)


def _mensagem_final(senha: Senha) -> str:
    chave = "finalizado_preferencial" if senha.preferencial else "finalizado"
    return TEXTOS[chave].format(senha=_soletrar_senha(senha.codigo))


class ServicoAtendimento:
    def __init__(self, uow: UnidadeDeTrabalho, limiar_confianca: float):
        self.uow = uow
        self.limiar_confianca = limiar_confianca

    # --- Consultas ------------------------------------------------------------

    def obter(self, atendimento_id: int) -> Atendimento:
        atendimento = self.uow.atendimentos.obter(atendimento_id)
        if atendimento is None:
            raise AtendimentoNaoEncontrado
        return atendimento

    def _estado(self, atendimento: Atendimento, repetir: bool = False) -> EstadoAtendimento:
        return EstadoAtendimento(
            atendimento=atendimento,
            proxima_pergunta=atendimento.proxima_pergunta(),
            identificado=self.uow.identificacoes.obter(atendimento.id) is not None,
            repetir=repetir,
        )

    def consultar(self, atendimento_id: int) -> EstadoAtendimento:
        return self._estado(self.obter(atendimento_id))

    def conferir(self, atendimento_id: int) -> ConferenciaAtendimento:
        """Resumo do que o paciente respondeu, para ele confirmar antes da senha."""
        estado = self.consultar(atendimento_id)
        triagem_completa = estado.proxima_pergunta is None
        return ConferenciaAtendimento(
            atendimento=estado.atendimento,
            conferencia=gerar_conferencia(estado.atendimento.respostas),
            pode_finalizar=triagem_completa and estado.identificado and not estado.atendimento.finalizado,
        )

    # --- Comandos -------------------------------------------------------------

    def iniciar(self, modo: ModoAcessibilidade, agora: datetime | None = None) -> EstadoAtendimento:
        atendimento = self.uow.atendimentos.adicionar(Atendimento.iniciar(modo, agora or agora_local()))
        self.uow.commit()
        return self._estado(atendimento)

    def responder(
        self,
        atendimento_id: int,
        pergunta_id: str,
        valor: Any,
        canal: ModoAcessibilidade | None = None,
        confianca: float | None = None,
    ) -> EstadoAtendimento:
        atendimento = self.obter(atendimento_id)
        gravou = atendimento.responder(pergunta_id, valor, canal, confianca, self.limiar_confianca)
        if gravou:
            atendimento = self.uow.atendimentos.salvar(atendimento)
            self.uow.commit()
        return self._estado(atendimento, repetir=not gravou)

    def corrigir(self, atendimento_id: int, pergunta_id: str) -> EstadoAtendimento:
        """Volta a triagem para `pergunta_id`, apagando essa resposta e as seguintes."""
        atendimento = self.obter(atendimento_id)
        atendimento.voltar_para(pergunta_id)
        atendimento = self.uow.atendimentos.salvar(atendimento)
        self.uow.commit()
        return self._estado(atendimento)

    def identificar(
        self, atendimento_id: int, nome: str, cpf: str, agora: datetime | None = None
    ) -> EstadoAtendimento:
        """Grava (ou corrige, antes de finalizar) nome e CPF."""
        atendimento = self.obter(atendimento_id)
        atendimento.garantir_em_andamento()

        identificacao = self.uow.identificacoes.obter(atendimento_id)
        if identificacao is None:
            identificacao = Identificacao.criar(atendimento_id, nome, cpf, agora or agora_local())
        else:
            identificacao.corrigir(nome, cpf)
        self.uow.identificacoes.salvar(identificacao)
        self.uow.commit()
        return self._estado(atendimento)

    def finalizar(self, atendimento_id: int, agora: datetime | None = None) -> Finalizacao:
        """Emite a senha, registra a queixa e gera o resumo para a recepção, tudo numa transação."""
        agora = agora or agora_local()
        atendimento = self.obter(atendimento_id)
        atendimento.garantir_em_andamento()
        if atendimento.proxima_pergunta() is not None:
            raise TriagemIncompleta
        identificacao = self.uow.identificacoes.obter(atendimento_id)
        if identificacao is None:
            raise IdentificacaoPendente

        senha = emitir_sem_commit(self.uow, atendimento.tipo_de_senha(), agora)
        queixa = Queixa.das_respostas(atendimento, agora)
        if queixa is not None:
            self.uow.queixas.adicionar(queixa)
        atendimento.concluir(senha, identificacao.nome, agora)
        atendimento = self.uow.atendimentos.salvar(atendimento)
        self.uow.commit()

        return Finalizacao(atendimento, senha, _mensagem_final(senha))
