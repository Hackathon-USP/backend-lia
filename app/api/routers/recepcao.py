"""Endpoints da tela da recepção.

TODO: proteger antes de uso real — devolvem nome, CPF e dados de saúde dos pacientes (LGPD).
"""

from datetime import date
from typing import Any

from fastapi import APIRouter, Depends, Query

from app.api.dependencias import servico_recepcao, servico_relatorio
from app.api.schemas import (
    AtendimentoDetalhe,
    AtendimentoResumo,
    Chamada,
    ItemFila,
    QueixaLeitura,
    RelatorioLeitura,
    RespostaRotulada,
    SenhaLeitura,
    SenhaStatusAtualizar,
)
from app.application.recepcao import AtendimentoListado, SenhaNaFila, ServicoRecepcao
from app.application.relatorios import ServicoRelatorio
from app.domain.entidades import Atendimento, Identificacao, Senha
from app.domain.enums import ModoAcessibilidade, StatusAtendimento, StatusSenha
from app.domain.identificacao import formatar_cpf

router = APIRouter(prefix="/recepcao", tags=["recepcao"])


# --- Conversões para os schemas ----------------------------------------------


def _senha_leitura(senha: Senha | None) -> SenhaLeitura | None:
    return SenhaLeitura.model_validate(senha, from_attributes=True) if senha else None


def _nome_e_cpf(ident: Identificacao | None) -> dict[str, str | None]:
    """Campos `nome` e `cpf` (formatado); vazios para atendimentos sem identificação."""
    if ident is None:
        return {"nome": None, "cpf": None}
    return {"nome": ident.nome or None, "cpf": formatar_cpf(ident.cpf)}


def _dados_do_paciente(atendimento: Atendimento | None, ident: Identificacao | None) -> dict[str, Any]:
    """Campos comuns à fila e à chamada; vazios para senhas emitidas sem triagem."""
    if atendimento is None:
        return {"atendimento_id": None, "modo": None, "nome": None, "cpf": None, "alertas": []}
    return {
        "atendimento_id": atendimento.id,
        "modo": atendimento.modo,
        **_nome_e_cpf(ident),
        "alertas": atendimento.alertas,
    }


def _resumo(item: AtendimentoListado) -> AtendimentoResumo:
    atendimento = item.atendimento
    return AtendimentoResumo(
        id=atendimento.id,
        modo=atendimento.modo,
        status=atendimento.status,
        senha=item.senha.codigo if item.senha else None,
        **_nome_e_cpf(item.identificacao),
        alertas=atendimento.alertas,
        criado_em=atendimento.criado_em,
        finalizado_em=atendimento.finalizado_em,
    )


def _item_fila(item: SenhaNaFila) -> ItemFila:
    return ItemFila(
        codigo=item.senha.codigo,
        tipo=item.senha.tipo,
        status=item.senha.status,
        criada_em=item.senha.criada_em,
        **_dados_do_paciente(item.atendimento, item.identificacao),
    )


# --- Rotas --------------------------------------------------------------------


@router.get("/fila", response_model=list[ItemFila])
def fila(
    data: date | None = None,
    status_senha: StatusSenha | None = Query(None, alias="status"),
    servico: ServicoRecepcao = Depends(servico_recepcao),
):
    """Senhas do dia (padrão: hoje). Ordem: aguardando primeiro, preferenciais antes,
    depois por horário de emissão. Inclui os alertas da triagem de cada paciente."""
    return [_item_fila(item) for item in servico.listar_fila(data, status_senha)]


@router.get("/atendimentos", response_model=list[AtendimentoResumo])
def listar_atendimentos(
    data: date | None = None,
    status_atendimento: StatusAtendimento | None = Query(None, alias="status"),
    modo: ModoAcessibilidade | None = None,
    cpf: str | None = Query(None, description="Com ou sem máscara. Traz o histórico do paciente."),
    servico: ServicoRecepcao = Depends(servico_recepcao),
):
    """Atendimentos cadastrados, mais recentes primeiro. Todos os filtros são opcionais."""
    return [_resumo(item) for item in servico.listar_atendimentos(data, status_atendimento, modo, cpf)]


@router.get("/atendimentos/{atendimento_id}", response_model=AtendimentoDetalhe)
def detalhar_atendimento(atendimento_id: int, servico: ServicoRecepcao = Depends(servico_recepcao)):
    """Tudo que o paciente informou, com textos legíveis, resumo, alertas e o relatório da triagem."""
    detalhe = servico.detalhar_atendimento(atendimento_id)
    return AtendimentoDetalhe(
        **_resumo(detalhe).model_dump(),
        senha_detalhe=_senha_leitura(detalhe.senha),
        resumo=detalhe.atendimento.resumo,
        respostas=[RespostaRotulada.model_validate(r, from_attributes=True) for r in detalhe.respostas],
        queixa=QueixaLeitura.model_validate(detalhe.queixa, from_attributes=True) if detalhe.queixa else None,
        relatorio=RelatorioLeitura.de(detalhe.relatorio),
    )


@router.post("/atendimentos/{atendimento_id}/relatorio", response_model=RelatorioLeitura)
def gerar_relatorio(atendimento_id: int, servico: ServicoRelatorio = Depends(servico_relatorio)):
    """Gera de novo o relatório da triagem (com IA, se configurada; senão, por regras).

    O relatório já sai sozinho logo depois da senha; use esta rota se ele não apareceu
    ou para refazê-lo. 409 se o atendimento ainda não foi finalizado.
    """
    return RelatorioLeitura.de(servico.gerar(atendimento_id))


@router.post("/chamar", response_model=Chamada)
def chamar(servico: ServicoRecepcao = Depends(servico_recepcao)):
    """Chama a próxima senha aguardando (preferenciais primeiro) e a marca como
    `em_atendimento`. Dois guichês chamando juntos nunca recebem a mesma senha."""
    item = servico.chamar_proxima()
    return Chamada(
        senha=_senha_leitura(item.senha),
        **_dados_do_paciente(item.atendimento, item.identificacao),
        resumo=item.atendimento.resumo if item.atendimento else None,
        relatorio=RelatorioLeitura.de(item.relatorio),
    )


@router.patch("/senhas/{codigo}", response_model=SenhaLeitura)
def atualizar_senha(
    codigo: str,
    dados: SenhaStatusAtualizar,
    servico: ServicoRecepcao = Depends(servico_recepcao),
):
    """Muda o status de uma senha de hoje (ex.: chamar uma específica, ou `finalizada`)."""
    return _senha_leitura(servico.atualizar_status_senha(codigo, dados.status))
