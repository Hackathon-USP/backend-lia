from datetime import datetime

from sqlmodel import Session

from app.config import settings
from app.conteudo import fluxo
from app.conteudo.textos import TEXTOS
from app.models import (
    Atendimento,
    Identificacao,
    ModoAcessibilidade,
    Queixa,
    Senha,
    StatusAtendimento,
    TipoSenha,
)
from app.services import fila, resumo


class AtendimentoNaoEncontrado(Exception):
    pass


class AtendimentoJaFinalizado(Exception):
    pass


class RespostaInvalida(Exception):
    pass


class TriagemIncompleta(Exception):
    pass


class IdentificacaoPendente(Exception):
    pass


def obter(session: Session, atendimento_id: int) -> Atendimento:
    atendimento = session.get(Atendimento, atendimento_id)
    if atendimento is None:
        raise AtendimentoNaoEncontrado
    return atendimento


def iniciar(session: Session, modo: ModoAcessibilidade, agora: datetime | None = None) -> Atendimento:
    agora = agora or fila.agora_local()
    atendimento = Atendimento(modo=modo, consentimento_em=agora, criado_em=agora)
    session.add(atendimento)
    session.commit()
    session.refresh(atendimento)
    return atendimento


def proxima_pergunta(atendimento: Atendimento) -> fluxo.Pergunta | None:
    if atendimento.status == StatusAtendimento.finalizado:
        return None
    return fluxo.proxima_pergunta(atendimento.respostas, atendimento.modo)


def registrar_resposta(
    session: Session,
    atendimento_id: int,
    pergunta_id: str,
    valor,
    canal: ModoAcessibilidade | None = None,
    confianca: float | None = None,
) -> tuple[Atendimento, bool]:
    """Grava a resposta. Devolve (atendimento, repetir).

    `repetir=True` quer dizer que nada foi gravado e o totem deve pedir a resposta
    de novo: acontece quando o reconhecimento de Libras/voz vem com confiança baixa
    ou com um sinal que não corresponde a nenhuma opção. Pelo toque, um valor
    inválido é erro do front e vira RespostaInvalida (422).
    """
    atendimento = obter(session, atendimento_id)
    if atendimento.status == StatusAtendimento.finalizado:
        raise AtendimentoJaFinalizado
    esperada = proxima_pergunta(atendimento)
    if esperada is None:
        raise RespostaInvalida("A triagem já terminou; finalize o atendimento")
    if pergunta_id != esperada.id:
        raise RespostaInvalida(f"Pergunta esperada agora: {esperada.id}")

    canal = canal or atendimento.modo
    reconhecimento = canal in (ModoAcessibilidade.libras, ModoAcessibilidade.voz)
    if reconhecimento and confianca is not None and confianca < settings.limiar_confianca:
        return atendimento, True
    try:
        normalizado = fluxo.validar_valor(esperada, valor)
    except ValueError as erro:
        if reconhecimento:
            return atendimento, True
        raise RespostaInvalida(str(erro)) from None

    # Dicts novos: o SQLAlchemy não detecta mutação in-place em colunas JSON.
    atendimento.respostas = {**atendimento.respostas, pergunta_id: normalizado}
    atendimento.canais = {**atendimento.canais, pergunta_id: canal.value}
    session.add(atendimento)
    session.commit()
    session.refresh(atendimento)
    return atendimento, False


def tipo_da_senha(atendimento: Atendimento) -> TipoSenha:
    if atendimento.modo != ModoAcessibilidade.toque or atendimento.respostas.get("prioridade") == "sim":
        return TipoSenha.preferencial
    return TipoSenha.normal


def finalizar(session: Session, atendimento_id: int, agora: datetime | None = None) -> tuple[Atendimento, Senha, str]:
    """Emite a senha, registra a queixa e gera o resumo. Devolve (atendimento, senha, mensagem_final)."""
    agora = agora or fila.agora_local()
    atendimento = obter(session, atendimento_id)
    if atendimento.status == StatusAtendimento.finalizado:
        raise AtendimentoJaFinalizado
    if proxima_pergunta(atendimento) is not None:
        raise TriagemIncompleta
    identificacao = session.get(Identificacao, atendimento.id)
    if identificacao is None:
        raise IdentificacaoPendente

    tipo = tipo_da_senha(atendimento)
    senha = fila.emitir_senha(session, tipo, agora)  # faz commit da senha

    respostas = atendimento.respostas
    if "sintoma" in respostas:
        session.add(
            Queixa(
                atendimento_id=atendimento.id,
                sintoma=respostas["sintoma"],
                local=respostas.get("local_dor"),
                intensidade=respostas.get("intensidade"),
                desde_quando=respostas.get("desde_quando"),
                criada_em=agora,
            )
        )

    alertas = resumo.gerar_alertas(respostas)
    atendimento.alertas = alertas
    atendimento.resumo = resumo.gerar_resumo(
        senha.codigo, atendimento.modo, respostas, alertas, nome=identificacao.nome
    )
    atendimento.senha_id = senha.id
    atendimento.status = StatusAtendimento.finalizado
    atendimento.finalizado_em = agora
    session.add(atendimento)
    session.commit()
    session.refresh(atendimento)

    chave = "finalizado_preferencial" if tipo == TipoSenha.preferencial else "finalizado"
    mensagem = TEXTOS[chave].format(senha=_soletrar_senha(senha.codigo))
    return atendimento, senha, mensagem


def _soletrar_senha(codigo: str) -> str:
    """'P012' -> 'P 0 1 2': fica mais claro no TTS e no VLibras (datilologia)."""
    return " ".join(codigo)
