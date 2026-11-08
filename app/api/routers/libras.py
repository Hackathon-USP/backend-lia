"""Amostras para treinar o reconhecimento de Libras dos totens.

TODO: proteger o envio e a remoção antes de uso real (hoje qualquer um pode mandar ou apagar).
"""

from fastapi import APIRouter, Depends, Query

from app.api.dependencias import servico_amostras_libras
from app.api.schemas import (
    AmostraLia,
    AmostraRecusada,
    DatasetLia,
    EnvioAmostras,
    EnvioAmostrasResultado,
    RemocaoAmostras,
    ResumoAmostrasLeitura,
)
from app.application.amostras_libras import MAX_POR_PAGINA, ServicoAmostrasLibras
from app.application.relogio import agora_local
from app.domain.amostras_libras import AmostraLibras

router = APIRouter(prefix="/libras", tags=["libras"])


def _amostra_lia(amostra: AmostraLibras) -> AmostraLia:
    return AmostraLia(
        id=amostra.id,
        gloss=amostra.glosa,
        source=amostra.fonte,
        signer=amostra.sinalizante,
        createdAt=amostra.gravada_em,
        origin=amostra.origem,
        width=amostra.largura,
        height=amostra.altura,
        frames=amostra.quadros,
        quality=amostra.qualidade,
    )


@router.post("/amostras", response_model=EnvioAmostrasResultado)
def enviar_amostras(dados: EnvioAmostras, servico: ServicoAmostrasLibras = Depends(servico_amostras_libras)):
    """Guarda amostras novas. As repetidas (mesmo id) são ignoradas e as inválidas voltam com o
    motivo, sem impedir as outras. Por padrão só a fonte `vlibras` é aceita."""
    relatorio = servico.enviar(dados.amostras)
    return EnvioAmostrasResultado(
        adicionadas=relatorio.adicionadas,
        ignoradas=relatorio.ignoradas,
        invalidas=[AmostraRecusada(indice=i, motivo=m) for i, m in relatorio.invalidas],
    )


@router.get("/amostras", response_model=DatasetLia)
def listar_amostras(
    fonte: str | None = Query(None, description="Ex.: 'vlibras'."),
    glosa: str | None = None,
    depois_de: int = Query(0, ge=0, description="Cursor da página anterior (0 = desde o começo)."),
    limite: int = Query(100, ge=1, le=MAX_POR_PAGINA),
    servico: ServicoAmostrasLibras = Depends(servico_amostras_libras),
):
    """Amostras em ordem de chegada, no formato de dataset do front. Para baixar tudo, repita
    com `depois_de=cursor` enquanto `tem_mais` for true; guarde o cursor para a próxima vez."""
    pagina = servico.listar(fonte, glosa, depois_de, limite)
    return DatasetLia(
        exportedAt=agora_local(),
        cursor=pagina.cursor,
        tem_mais=pagina.tem_mais,
        samples=[_amostra_lia(a) for a in pagina.amostras],
    )


@router.get("/amostras/resumo", response_model=ResumoAmostrasLeitura)
def resumir_amostras(
    fonte: str | None = None,
    servico: ServicoAmostrasLibras = Depends(servico_amostras_libras),
):
    """Quantas amostras há por glosa, por fonte e por sinalizante (sem os quadros)."""
    resumo = servico.resumir(fonte)
    return ResumoAmostrasLeitura(
        total=resumo.total,
        por_glosa=resumo.por_glosa,
        por_fonte=resumo.por_fonte,
        por_sinalizante=resumo.por_sinalizante,
    )


@router.delete("/amostras", response_model=RemocaoAmostras)
def remover_amostras(
    fonte: str | None = None,
    glosa: str | None = None,
    servico: ServicoAmostrasLibras = Depends(servico_amostras_libras),
):
    """Apaga as amostras da fonte e/ou glosa (pelo menos um filtro). Os totens que já baixaram
    continuam com as suas cópias."""
    return RemocaoAmostras(removidas=servico.remover(fonte, glosa))
