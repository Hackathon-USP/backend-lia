"""Casos de uso da tela do paciente: abrir a triagem, responder, identificar e finalizar.

Depois das perguntas fixas, a LIA (IA) pode fazer algumas perguntas complementares
para o caso do paciente (ver `app.domain.perguntas_da_lia`). Sem IA configurada, ou se
ela falhar, a triagem simplesmente segue para a identificação.
"""

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from app.application.relogio import agora_local
from app.application.senhas import emitir_sem_commit
from app.domain.assistente import AssistenteIndisponivel, AssistenteTriagem
from app.domain.conferencia import Conferencia, gerar_conferencia
from app.domain.entidades import Atendimento, Identificacao, PerguntasDaLia, Queixa, Senha
from app.domain.enums import ModoAcessibilidade
from app.domain.erros import AtendimentoNaoEncontrado, IdentificacaoPendente, TriagemIncompleta
from app.domain.perguntas_da_lia import SugestaoInvalida, criar_pergunta, pode_perguntar_mais
from app.domain.relatorio import montar_contexto
from app.domain.repositorios import UnidadeDeTrabalho
from app.domain.textos import TEXTOS
from app.domain.triagem import Pergunta

logger = logging.getLogger(__name__)


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
    def __init__(
        self,
        uow: UnidadeDeTrabalho,
        limiar_confianca: float,
        assistente: AssistenteTriagem | None = None,
    ):
        self.uow = uow
        self.limiar_confianca = limiar_confianca
        self.assistente = assistente  # None = triagem só com as perguntas fixas

    # --- Consultas ------------------------------------------------------------

    def obter(self, atendimento_id: int) -> Atendimento:
        atendimento = self.uow.atendimentos.obter(atendimento_id)
        if atendimento is None:
            raise AtendimentoNaoEncontrado
        return atendimento

    def _perguntas_da_lia(self, atendimento_id: int) -> PerguntasDaLia:
        return self.uow.perguntas_da_lia.obter(atendimento_id) or PerguntasDaLia(atendimento_id)

    def _estado(
        self, atendimento: Atendimento, repetir: bool = False, lia: PerguntasDaLia | None = None
    ) -> EstadoAtendimento:
        lia = lia or self._perguntas_da_lia(atendimento.id)
        return EstadoAtendimento(
            atendimento=atendimento,
            proxima_pergunta=atendimento.proxima_pergunta(lia.lista),
            identificado=self.uow.identificacoes.obter(atendimento.id) is not None,
            repetir=repetir,
        )

    def consultar(self, atendimento_id: int) -> EstadoAtendimento:
        return self._estado(self.obter(atendimento_id))

    def conferir(self, atendimento_id: int) -> ConferenciaAtendimento:
        """Resumo do que o paciente respondeu, para ele confirmar antes da senha."""
        estado = self.consultar(atendimento_id)
        triagem_completa = estado.proxima_pergunta is None
        lia = self._perguntas_da_lia(atendimento_id)
        return ConferenciaAtendimento(
            atendimento=estado.atendimento,
            conferencia=gerar_conferencia(estado.atendimento.respostas, lia.lista),
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
        lia = self._perguntas_da_lia(atendimento_id)
        gravou = atendimento.responder(
            pergunta_id, valor, canal, confianca, self.limiar_confianca, extras=lia.lista
        )
        if gravou:
            atendimento = self.uow.atendimentos.salvar(atendimento)
            self.uow.commit()
            lia = self._pedir_pergunta_da_lia(atendimento, lia)
        return self._estado(atendimento, repetir=not gravou, lia=lia)

    def _pedir_pergunta_da_lia(self, atendimento: Atendimento, lia: PerguntasDaLia) -> PerguntasDaLia:
        """Terminadas as perguntas fixas, pede à LIA a próxima pergunta complementar (se couber).

        Qualquer falha da IA só encerra as perguntas da LIA: o paciente nunca fica preso.
        """
        if self.assistente is None or lia.encerradas:
            return lia
        if not pode_perguntar_mais(atendimento.respostas, atendimento.modo, lia.lista):
            return lia
        contexto = montar_contexto(atendimento.modo, atendimento.respostas, atendimento.canais, lia.lista)
        try:
            sugestao = self.assistente.sugerir_pergunta(contexto)
            pergunta = criar_pergunta(sugestao, ordem=len(lia.lista) + 1) if sugestao else None
        except (AssistenteIndisponivel, SugestaoInvalida) as erro:
            logger.warning("Atendimento %s: sem pergunta da LIA (%s)", atendimento.id, erro)
            pergunta = None
        if pergunta is None:
            lia.encerrar()
        else:
            lia.adicionar(pergunta)
        lia = self.uow.perguntas_da_lia.salvar(lia)
        self.uow.commit()
        return lia

    def corrigir(self, atendimento_id: int, pergunta_id: str) -> EstadoAtendimento:
        """Volta a triagem para `pergunta_id`, apagando essa resposta e as seguintes.

        As perguntas da LIA feitas depois dela também saem: foram criadas a partir da
        resposta antiga e serão refeitas quando o paciente chegar lá de novo.
        """
        atendimento = self.obter(atendimento_id)
        lia = self._perguntas_da_lia(atendimento_id)
        atendimento.voltar_para(pergunta_id, lia.lista)
        lia.recomecar_a_partir_de(pergunta_id)
        atendimento = self.uow.atendimentos.salvar(atendimento)
        lia = self.uow.perguntas_da_lia.salvar(lia)
        self.uow.commit()
        return self._estado(atendimento, lia=lia)

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
        lia = self._perguntas_da_lia(atendimento_id)
        if atendimento.proxima_pergunta(lia.lista) is not None:
            raise TriagemIncompleta
        identificacao = self.uow.identificacoes.obter(atendimento_id)
        if identificacao is None:
            raise IdentificacaoPendente

        senha = emitir_sem_commit(self.uow, atendimento.tipo_de_senha(), agora)
        queixa = Queixa.das_respostas(atendimento, agora)
        if queixa is not None:
            self.uow.queixas.adicionar(queixa)
        atendimento.concluir(senha, identificacao.nome, agora, extras=lia.lista)
        atendimento = self.uow.atendimentos.salvar(atendimento)
        self.uow.commit()

        return Finalizacao(atendimento, senha, _mensagem_final(senha))
