"""Rotas da tela do paciente."""

import logging

from fastapi import APIRouter, BackgroundTasks, Depends, status

from app.api.dependencias import AbrirUnidade, assistente_triagem, fabrica_de_unidades, servico_atendimento
from app.api.schemas import (
    AtendimentoCriar,
    AtendimentoLeitura,
    ConferenciaLeitura,
    FinalizacaoLeitura,
    IdentificacaoCriar,
    ItemConferenciaLeitura,
    PerguntaLeitura,
    RespostaCriar,
    SenhaLeitura,
)
from app.application.atendimentos import EstadoAtendimento, ServicoAtendimento
from app.application.relatorios import ServicoRelatorio
from app.domain.assistente import AssistenteTriagem
from app.domain.textos import TEXTOS

router = APIRouter(prefix="/atendimentos", tags=["atendimentos"])
logger = logging.getLogger(__name__)


def gerar_relatorio_depois(abrir: AbrirUnidade, assistente: AssistenteTriagem | None, atendimento_id: int) -> None:
    """Escreve o relatório da triagem depois que a senha já foi entregue ao paciente."""
    try:
        with abrir() as uow:
            ServicoRelatorio(uow, assistente).gerar(atendimento_id)
    except Exception:  # roda fora da requisição: registra e segue (a recepção pode pedir de novo)
        logger.exception("Atendimento %s: não foi possível gerar o relatório", atendimento_id)


def _para_leitura(estado: EstadoAtendimento) -> AtendimentoLeitura:
    atendimento = estado.atendimento
    return AtendimentoLeitura(
        id=atendimento.id,
        modo=atendimento.modo,
        status=atendimento.status,
        respostas=atendimento.respostas,
        canais=atendimento.canais,
        proxima_pergunta=PerguntaLeitura.de(estado.proxima_pergunta),
        identificado=estado.identificado,
        repetir=estado.repetir,
        mensagem=TEXTOS["repetir"] if estado.repetir else None,
        criado_em=atendimento.criado_em,
    )


@router.post("", response_model=AtendimentoLeitura, status_code=status.HTTP_201_CREATED)
def iniciar(dados: AtendimentoCriar, servico: ServicoAtendimento = Depends(servico_atendimento)):
    """Inicia a triagem após o consentimento. Devolve a primeira pergunta."""
    return _para_leitura(servico.iniciar(dados.modo))


@router.get("/{atendimento_id}", response_model=AtendimentoLeitura)
def consultar(atendimento_id: int, servico: ServicoAtendimento = Depends(servico_atendimento)):
    """Estado atual (útil para retomar se a tela do totem recarregar)."""
    return _para_leitura(servico.consultar(atendimento_id))


@router.post("/{atendimento_id}/respostas", response_model=AtendimentoLeitura)
def responder(
    atendimento_id: int,
    dados: RespostaCriar,
    servico: ServicoAtendimento = Depends(servico_atendimento),
):
    """Grava a resposta da pergunta atual e devolve a próxima (`null` = pode finalizar).

    Aceita o nome do sinal reconhecido em Libras (ex.: `"DOR"`) ou a palavra falada.
    Se vier por Libras/voz com `confianca` abaixo do limiar, ou com um sinal que não
    corresponde a nenhuma opção, nada é gravado e a resposta vem com `repetir: true`.

    Depois das perguntas fixas, a LIA (IA) pode mandar até 3 perguntas complementares
    para o caso do paciente (`origem: "lia"`); elas são respondidas do mesmo jeito.
    Esta chamada demora alguns segundos a mais quando a LIA está criando a pergunta.
    """
    estado = servico.responder(atendimento_id, dados.pergunta_id, dados.valor, dados.canal, dados.confianca)
    return _para_leitura(estado)


@router.get("/{atendimento_id}/conferencia", response_model=ConferenciaLeitura)
def conferir(atendimento_id: int, servico: ServicoAtendimento = Depends(servico_atendimento)):
    """Resumo das respostas para o paciente conferir antes de receber a senha.

    `texto` vai para o VLibras/voz; `itens` para a tela, cada um com o `pergunta_id` que
    o front manda em `DELETE .../respostas/{pergunta_id}` se o paciente quiser corrigir.
    Nome e CPF não aparecem (a tela do totem é pública).
    """
    resultado = servico.conferir(atendimento_id)
    return ConferenciaLeitura(
        atendimento_id=resultado.atendimento.id,
        itens=[ItemConferenciaLeitura.model_validate(i, from_attributes=True) for i in resultado.conferencia.itens],
        texto=resultado.conferencia.texto,
        pode_finalizar=resultado.pode_finalizar,
    )


@router.delete("/{atendimento_id}/respostas/{pergunta_id}", response_model=AtendimentoLeitura)
def corrigir(
    atendimento_id: int,
    pergunta_id: str,
    servico: ServicoAtendimento = Depends(servico_atendimento),
):
    """Volta a triagem para `pergunta_id`: apaga essa resposta e as de todas as perguntas
    seguintes (que dependem dela). A resposta traz `proxima_pergunta` = a pergunta corrigida.

    Use quando o paciente apontar um erro no resumo de conferência.
    """
    return _para_leitura(servico.corrigir(atendimento_id, pergunta_id))


@router.put("/{atendimento_id}/identificacao", response_model=AtendimentoLeitura)
def identificar(
    atendimento_id: int,
    dados: IdentificacaoCriar,
    servico: ServicoAtendimento = Depends(servico_atendimento),
):
    """Grava o CPF do paciente (obrigatório para finalizar). Pode ser chamado de
    novo para corrigir, enquanto o atendimento não foi finalizado. Não devolve os dados
    de volta: o totem é público."""
    return _para_leitura(servico.identificar(atendimento_id, dados.nome, dados.cpf))


@router.post("/{atendimento_id}/finalizar", response_model=FinalizacaoLeitura)
def finalizar(
    atendimento_id: int,
    tarefas: BackgroundTasks,
    servico: ServicoAtendimento = Depends(servico_atendimento),
    abrir: AbrirUnidade = Depends(fabrica_de_unidades),
    assistente: AssistenteTriagem | None = Depends(assistente_triagem),
):
    """Emite a senha, gera o resumo para a recepção e devolve a mensagem final do totem.

    O relatório da triagem é escrito logo depois (sem atrasar a senha) e aparece em
    `GET /recepcao/atendimentos/{id}`.
    """
    finalizacao = servico.finalizar(atendimento_id)
    tarefas.add_task(gerar_relatorio_depois, abrir, assistente, atendimento_id)
    return FinalizacaoLeitura(
        atendimento_id=finalizacao.atendimento.id,
        senha=SenhaLeitura.model_validate(finalizacao.senha, from_attributes=True),
        mensagem_final=finalizacao.mensagem_final,
    )
