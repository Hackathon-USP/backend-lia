"""Perguntas complementares e relatório da triagem feitos pela LIA (IA).

A API real da OpenAI nunca é chamada: os testes usam um assistente falso.
"""

from types import SimpleNamespace

import httpx2
import openai
import pytest

from app.domain.assistente import AssistenteIndisponivel
from app.domain.enums import ModoAcessibilidade
from app.domain.perguntas_da_lia import (
    OpcaoSugerida,
    PerguntaSugerida,
    SugestaoInvalida,
    criar_pergunta,
    pode_perguntar_mais,
)
from app.domain.relatorio import ConteudoRelatorio, juntar_alertas, montar_contexto, relatorio_por_regras
from app.domain.triagem import OrigemPergunta
from app.ia.gpt import AssistenteGPT, _Decisao, _Opcao, _Pergunta
from app.ia.prompts import descrever_contexto
from tests.test_atendimentos import CPF_VALIDO, finalizar, iniciar, responder, responder_tudo

DOR_NO_PEITO = {
    "motivo": "sintoma", "sintoma": "dor", "local_dor": "peito",
    "intensidade": 9, "desde_quando": "hoje",
}

SUOR_FRIO = PerguntaSugerida(
    texto="Você está suando frio?",
    titulo="Suor frio",
    opcoes=(OpcaoSugerida("Sim", "Dor no peito com suor frio"), OpcaoSugerida("Não")),
)


class AssistenteFalso:
    """Devolve as perguntas da lista, uma por chamada; depois, None (não precisa mais)."""

    modelo = "modelo-falso"

    def __init__(self, perguntas=(), relatorio=None, falhar_pergunta=False, falhar_relatorio=False):
        self.perguntas = list(perguntas)
        self.relatorio = relatorio
        self.falhar_pergunta = falhar_pergunta
        self.falhar_relatorio = falhar_relatorio
        self.contextos = []

    def sugerir_pergunta(self, contexto):
        self.contextos.append(contexto)
        if self.falhar_pergunta:
            raise AssistenteIndisponivel("fora do ar")
        return self.perguntas.pop(0) if self.perguntas else None

    def escrever_relatorio(self, contexto):
        self.contextos.append(contexto)
        if self.falhar_relatorio:
            raise AssistenteIndisponivel("fora do ar")
        return self.relatorio or ConteudoRelatorio(
            queixa_principal="Dor no peito desde hoje, 9 de 10",
            resumo="Paciente relata dor no peito desde hoje, com suor frio.",
            sinais_de_alerta=("Suor frio",),
            pontos_a_confirmar=("Confirmar se a dor vai para o braço.",),
            orientacao_recepcao="Providenciar intérprete de Libras e avisar a enfermagem.",
        )


class SemprePergunta(AssistenteFalso):
    def sugerir_pergunta(self, contexto):
        self.contextos.append(contexto)
        n = contexto.perguntas_da_lia + 1
        return PerguntaSugerida(f"Pergunta {n}?", f"Item {n}", (OpcaoSugerida("Sim"), OpcaoSugerida("Não")))


# --- Domínio ------------------------------------------------------------------


def test_sugestao_vira_pergunta_de_opcoes_com_nao_sei():
    p = criar_pergunta(SUOR_FRIO, ordem=1)
    assert p.id == "lia_1" and p.origem == OrigemPergunta.lia
    assert [(o.id, o.rotulo) for o in p.opcoes] == [("sim", "Sim"), ("nao", "Não"), ("nao_sei", "Não sei")]
    # Palavra única vira o nome do sinal que a câmera reconhece.
    assert p.opcoes[0].sinais == ("SIM",) and p.opcoes[1].sinais == ("NAO",)
    assert p.alertas == {"sim": "Dor no peito com suor frio"}


def test_sugestao_limpa_repeticoes_e_corta_excesso_de_opcoes():
    sugestao = PerguntaSugerida(
        "  Onde   está a dor?  ", "",
        tuple(OpcaoSugerida(r) for r in ("Braço", "braço", "Queixo", "Costas", "Barriga", "Pescoço", "Não sei")),
    )
    p = criar_pergunta(sugestao, ordem=2)
    assert p.texto == "Onde está a dor?"
    assert p.titulo == "Pergunta da LIA 2"
    assert [o.rotulo for o in p.opcoes] == ["Braço", "Queixo", "Costas", "Barriga", "Não sei"]


@pytest.mark.parametrize("sugestao", [
    PerguntaSugerida("", "x", (OpcaoSugerida("Sim"), OpcaoSugerida("Não"))),
    PerguntaSugerida("Tudo bem?", "x", (OpcaoSugerida("Sim"),)),
    PerguntaSugerida("Tudo bem?", "x", (OpcaoSugerida("Sim"), OpcaoSugerida("Não sei"))),
])
def test_sugestao_inutilizavel_e_recusada(sugestao):
    with pytest.raises(SugestaoInvalida):
        criar_pergunta(sugestao, ordem=1)


def test_lia_so_pergunta_quando_ha_sintoma_ou_outro_motivo():
    modo = ModoAcessibilidade.libras
    assert pode_perguntar_mais(DOR_NO_PEITO, modo, ())
    assert not pode_perguntar_mais({"motivo": "exame"}, modo, ())
    assert not pode_perguntar_mais({"motivo": "sintoma"}, modo, ())  # perguntas fixas ainda faltando


def test_relatorio_por_regras_resume_as_respostas():
    contexto = montar_contexto(ModoAcessibilidade.libras, DOR_NO_PEITO, {"sintoma": "libras"}, ())
    r = relatorio_por_regras(contexto)
    assert r.queixa_principal == "Dor (peito), desde hoje, intensidade 9 de 10"
    assert r.sinais_de_alerta == ("Dor no peito", "Intensidade alta (9/10)")
    assert "Libras" in r.orientacao_recepcao and "enfermagem" in r.orientacao_recepcao
    assert any("reconhecimento automático" in p for p in r.pontos_a_confirmar)


def test_juntar_alertas_sem_repetir():
    assert juntar_alertas(["Dor no peito"], ["dor no peito ", "Suor frio", ""]) == ["Dor no peito", "Suor frio"]


# --- Fluxo pela API -----------------------------------------------------------


def test_sem_ia_a_triagem_fica_igual_e_o_relatorio_sai_por_regras(client):
    a = iniciar(client, "libras")
    assert responder_tudo(client, a["id"], DOR_NO_PEITO) == list(DOR_NO_PEITO)
    assert finalizar(client, a["id"]).status_code == 200

    relatorio = client.get(f"/recepcao/atendimentos/{a['id']}").json()["relatorio"]
    assert relatorio["gerado_por"] == "regras" and relatorio["modelo"] is None
    assert relatorio["sinais_de_alerta"] == ["Dor no peito", "Intensidade alta (9/10)"]


def test_lia_faz_pergunta_complementar_e_escreve_o_relatorio(client, usar_assistente):
    lia = usar_assistente(AssistenteFalso([SUOR_FRIO]))
    a = iniciar(client, "libras")
    for pergunta_id, valor in DOR_NO_PEITO.items():
        resp = responder(client, a["id"], pergunta_id, valor).json()
    pergunta = resp["proxima_pergunta"]
    assert pergunta["id"] == "lia_1" and pergunta["origem"] == "lia"
    assert pergunta["texto"] == "Você está suando frio?"
    assert [o["id"] for o in pergunta["opcoes"]] == ["sim", "nao", "nao_sei"]

    # O sinal SIM reconhecido pela câmera responde a pergunta da LIA.
    resp = client.post(
        f"/atendimentos/{a['id']}/respostas", json={"pergunta_id": "lia_1", "valor": "SIM", "canal": "libras"}
    ).json()
    assert resp["proxima_pergunta"] is None and resp["repetir"] is False

    conferencia = client.get(f"/atendimentos/{a['id']}/conferencia").json()
    assert conferencia["itens"][-1] == {
        "pergunta_id": "lia_1", "titulo": "Suor frio", "pergunta": "Você está suando frio?", "resposta": "Sim",
    }

    assert finalizar(client, a["id"]).status_code == 200
    detalhe = client.get(f"/recepcao/atendimentos/{a['id']}").json()
    assert "Dor no peito com suor frio" in detalhe["alertas"]
    assert detalhe["respostas"][-1]["da_lia"] is True
    assert "Suor frio: Sim" in detalhe["resumo"]

    relatorio = detalhe["relatorio"]
    assert relatorio["gerado_por"] == "ia" and relatorio["modelo"] == "modelo-falso"
    # Os alertas das regras e da pergunta da LIA ficam, mesmo que a IA não os repita.
    assert relatorio["sinais_de_alerta"] == [
        "Dor no peito", "Intensidade alta (9/10)", "Dor no peito com suor frio", "Suor frio",
    ]

    # Nome e CPF nunca chegam à IA.
    for contexto in lia.contextos:
        texto = descrever_contexto(contexto)
        assert "Maria" not in texto and "529" not in texto and CPF_VALIDO not in texto

    chamada = client.post("/recepcao/chamar").json()
    assert chamada["relatorio"]["queixa_principal"] == "Dor no peito desde hoje, 9 de 10"


def test_lia_para_no_limite_de_perguntas(client, usar_assistente):
    usar_assistente(SemprePergunta())
    a = iniciar(client, "toque")
    perguntadas = responder_tudo(client, a["id"], {
        **DOR_NO_PEITO, "prioridade": "nao", "lia_1": "sim", "lia_2": "nao", "lia_3": "nao_sei",
    })
    assert perguntadas[-4:] == ["prioridade", "lia_1", "lia_2", "lia_3"]


def test_lia_nao_pergunta_quando_o_motivo_e_exame(client, usar_assistente):
    lia = usar_assistente(SemprePergunta())
    a = iniciar(client, "toque")
    assert responder_tudo(client, a["id"], {"motivo": "exame", "prioridade": "nao"}) == ["motivo", "prioridade"]
    assert lia.contextos == []


def test_ia_fora_do_ar_nao_trava_o_paciente(client, usar_assistente):
    usar_assistente(AssistenteFalso(falhar_pergunta=True, falhar_relatorio=True))
    a = iniciar(client, "voz")
    assert responder_tudo(client, a["id"], DOR_NO_PEITO) == list(DOR_NO_PEITO)
    assert finalizar(client, a["id"]).status_code == 200
    assert client.get(f"/recepcao/atendimentos/{a['id']}").json()["relatorio"]["gerado_por"] == "regras"


def test_sugestao_ruim_encerra_as_perguntas_da_lia(client, usar_assistente):
    usar_assistente(AssistenteFalso([PerguntaSugerida("Tudo bem?", "x", (OpcaoSugerida("Sim"),)), SUOR_FRIO]))
    a = iniciar(client, "libras")
    assert responder_tudo(client, a["id"], DOR_NO_PEITO) == list(DOR_NO_PEITO)


def test_corrigir_pergunta_fixa_refaz_as_perguntas_da_lia(client, usar_assistente):
    # Primeira passada: uma pergunta e pronto. Depois da correção: a pergunta de novo.
    lia = usar_assistente(AssistenteFalso([SUOR_FRIO, None, SUOR_FRIO]))
    a = iniciar(client, "libras")
    responder_tudo(client, a["id"], {**DOR_NO_PEITO, "lia_1": "sim"})

    resp = client.delete(f"/atendimentos/{a['id']}/respostas/intensidade").json()
    assert resp["proxima_pergunta"]["id"] == "intensidade"
    assert "lia_1" not in resp["respostas"]

    resp = responder(client, a["id"], "intensidade", 3).json()
    resp = responder(client, a["id"], "desde_quando", "hoje").json()
    assert resp["proxima_pergunta"]["id"] == "lia_1"
    # A nova pergunta foi pedida com a resposta corrigida.
    assert any(r.resposta == "3 de 10" for r in lia.contextos[-1].respostas)


def test_corrigir_pergunta_da_lia_pergunta_de_novo(client, usar_assistente):
    usar_assistente(AssistenteFalso([SUOR_FRIO]))
    a = iniciar(client, "libras")
    responder_tudo(client, a["id"], {**DOR_NO_PEITO, "lia_1": "sim"})
    resp = client.delete(f"/atendimentos/{a['id']}/respostas/lia_1").json()
    assert resp["proxima_pergunta"]["id"] == "lia_1"
    assert responder(client, a["id"], "lia_1", "nao").json()["proxima_pergunta"] is None


def test_recepcao_pode_gerar_o_relatorio_de_novo(client, usar_assistente):
    a = iniciar(client, "toque")
    responder_tudo(client, a["id"], {"motivo": "exame", "prioridade": "nao"})
    assert client.post(f"/recepcao/atendimentos/{a['id']}/relatorio").status_code == 409

    finalizar(client, a["id"])
    assert client.get(f"/recepcao/atendimentos/{a['id']}").json()["relatorio"]["gerado_por"] == "regras"

    usar_assistente(AssistenteFalso())
    resp = client.post(f"/recepcao/atendimentos/{a['id']}/relatorio")
    assert resp.status_code == 200 and resp.json()["gerado_por"] == "ia"
    assert client.post("/recepcao/atendimentos/999/relatorio").status_code == 404


# --- Adaptador do GPT (sem rede) ---------------------------------------------


def _gpt_com_resposta(resposta=None, erro=None):
    chamadas = []

    def parse(**kwargs):
        chamadas.append(kwargs)
        if erro:
            raise erro
        return resposta

    assistente = AssistenteGPT(api_key="teste")
    falso = SimpleNamespace(responses=SimpleNamespace(parse=parse))
    assistente._cliente_pergunta = assistente._cliente_relatorio = falso
    return assistente, chamadas


def _contexto():
    return montar_contexto(ModoAcessibilidade.libras, DOR_NO_PEITO, {}, ())


def _resposta(parsed, status="completed", motivo=None):
    detalhes = SimpleNamespace(reason=motivo) if motivo else None
    return SimpleNamespace(status=status, output_parsed=parsed, incomplete_details=detalhes)


def test_gpt_devolve_a_pergunta_sugerida():
    decisao = _Decisao(perguntar=True, pergunta=_Pergunta(
        texto="Você está suando frio?", titulo="Suor frio",
        opcoes=[_Opcao(rotulo="Sim", alerta="Suor frio"), _Opcao(rotulo="Não", alerta=None)],
    ))
    assistente, chamadas = _gpt_com_resposta(_resposta(decisao))
    assert assistente.sugerir_pergunta(_contexto()) == PerguntaSugerida(
        "Você está suando frio?", "Suor frio", (OpcaoSugerida("Sim", "Suor frio"), OpcaoSugerida("Não", None))
    )
    [pedido] = chamadas
    assert pedido["model"] == "gpt-6-luna" and pedido["store"] is False
    assert pedido["reasoning"] == {"effort": "none"} and pedido["text_format"] is _Decisao


def test_gpt_sem_mais_perguntas():
    assistente, _ = _gpt_com_resposta(_resposta(_Decisao(perguntar=False, pergunta=None)))
    assert assistente.sugerir_pergunta(_contexto()) is None


@pytest.mark.parametrize("resposta, erro", [
    (_resposta(None), None),  # recusa: sem JSON
    (_resposta(None, status="incomplete", motivo="max_output_tokens"), None),
    (None, openai.APIConnectionError(request=httpx2.Request("POST", "https://api.openai.com"))),
    (None, openai.APITimeoutError(request=httpx2.Request("POST", "https://api.openai.com"))),
])
def test_gpt_falha_vira_assistente_indisponivel(resposta, erro):
    assistente, _ = _gpt_com_resposta(resposta, erro)
    with pytest.raises(AssistenteIndisponivel):
        assistente.escrever_relatorio(_contexto())
