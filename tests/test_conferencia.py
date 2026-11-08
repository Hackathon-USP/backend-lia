from datetime import datetime

import pytest

from app.domain.conferencia import gerar_conferencia
from app.domain.entidades import Atendimento
from app.domain.enums import ModoAcessibilidade
from app.domain.erros import RespostaInvalida
from tests.test_atendimentos import finalizar, identificar, iniciar, responder_tudo

DOR_NO_PEITO = {
    "motivo": "sintoma", "sintoma": "dor", "local_dor": "peito",
    "intensidade": 9, "desde_quando": "hoje", "prioridade": "nao",
}


# --- Domínio (sem banco) ------------------------------------------------------


def test_texto_da_conferencia_repete_as_respostas_na_ordem():
    conferencia = gerar_conferencia({"prioridade": "sim", "motivo": "exame"})
    assert [i.pergunta_id for i in conferencia.itens] == ["motivo", "prioridade"]
    assert conferencia.texto == (
        "Vamos conferir suas respostas. Motivo da vinda: Exame. Atendimento prioritário: Sim. "
        "Está tudo certo? Se algo estiver errado, escolha a resposta que quer corrigir."
    )


def test_escala_aparece_como_x_de_maximo():
    itens = gerar_conferencia({"motivo": "sintoma", "intensidade": 9}).itens
    assert itens[-1].titulo == "Intensidade" and itens[-1].resposta == "9 de 10"


def test_voltar_para_apaga_a_resposta_e_as_seguintes():
    atendimento = Atendimento.iniciar(ModoAcessibilidade.toque, datetime(2026, 1, 1))
    atendimento.respostas = dict(DOR_NO_PEITO)
    atendimento.canais = {pid: "toque" for pid in DOR_NO_PEITO}

    atendimento.voltar_para("local_dor")

    assert atendimento.respostas == {"motivo": "sintoma", "sintoma": "dor"}
    assert set(atendimento.canais) == {"motivo", "sintoma"}
    assert atendimento.proxima_pergunta().id == "local_dor"


def test_voltar_para_pergunta_nao_respondida_e_erro():
    atendimento = Atendimento.iniciar(ModoAcessibilidade.toque, datetime(2026, 1, 1))
    with pytest.raises(RespostaInvalida):
        atendimento.voltar_para("motivo")


# --- API ----------------------------------------------------------------------


def test_conferencia_antes_de_finalizar(client):
    a = iniciar(client)
    responder_tudo(client, a["id"], DOR_NO_PEITO)
    identificar(client, a["id"])

    corpo = client.get(f"/atendimentos/{a['id']}/conferencia").json()

    assert corpo["pode_finalizar"] is True
    assert [i["resposta"] for i in corpo["itens"]] == [
        "Estou sentindo algo", "Dor", "Peito", "9 de 10", "Desde hoje", "Não",
    ]
    assert "Onde dói: Peito." in corpo["texto"]
    assert "Maria" not in corpo["texto"]  # nome e CPF não aparecem na tela pública


def test_conferencia_avisa_quando_ainda_nao_pode_finalizar(client):
    a = iniciar(client)
    responder_tudo(client, a["id"], DOR_NO_PEITO)  # falta nome e CPF
    assert client.get(f"/atendimentos/{a['id']}/conferencia").json()["pode_finalizar"] is False


def test_conferencia_de_atendimento_inexistente_retorna_404(client):
    assert client.get("/atendimentos/999/conferencia").status_code == 404


def test_corrigir_volta_para_a_pergunta_e_refaz_o_caminho(client):
    a = iniciar(client)
    responder_tudo(client, a["id"], DOR_NO_PEITO)

    corpo = client.delete(f"/atendimentos/{a['id']}/respostas/sintoma").json()
    assert corpo["proxima_pergunta"]["id"] == "sintoma"
    assert corpo["respostas"] == {"motivo": "sintoma"}

    # Febre não pergunta "onde dói": o caminho muda conforme a nova resposta.
    perguntadas = responder_tudo(client, a["id"], {**DOR_NO_PEITO, "sintoma": "febre"})
    assert perguntadas == ["sintoma", "intensidade", "desde_quando", "prioridade"]
    assert finalizar(client, a["id"]).status_code == 200


def test_corrigir_pergunta_nao_respondida_retorna_422(client):
    a = iniciar(client)
    assert client.delete(f"/atendimentos/{a['id']}/respostas/sintoma").status_code == 422


def test_corrigir_depois_de_finalizar_retorna_409(client):
    a = iniciar(client)
    responder_tudo(client, a["id"], {"motivo": "exame", "prioridade": "nao"})
    finalizar(client, a["id"])
    assert client.delete(f"/atendimentos/{a['id']}/respostas/motivo").status_code == 409


def test_perguntas_expoem_titulo(client):
    titulos = {p["id"]: p["titulo"] for p in client.get("/conteudo/perguntas").json()}
    assert titulos["local_dor"] == "Onde dói"
