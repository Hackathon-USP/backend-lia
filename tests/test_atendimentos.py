from sqlmodel import select

from app.models import Atendimento, Queixa


def iniciar(client, modo="toque"):
    resp = client.post("/atendimentos", json={"modo": modo, "consentimento": True})
    assert resp.status_code == 201
    return resp.json()


def responder(client, atendimento_id, pergunta_id, valor):
    return client.post(
        f"/atendimentos/{atendimento_id}/respostas",
        json={"pergunta_id": pergunta_id, "valor": valor},
    )


def responder_tudo(client, atendimento_id, respostas):
    """Responde na ordem que o back end pedir; falha se pedir algo não previsto."""
    proxima = client.get(f"/atendimentos/{atendimento_id}").json()["proxima_pergunta"]
    perguntadas = []
    while proxima is not None:
        pid = proxima["id"]
        perguntadas.append(pid)
        resp = responder(client, atendimento_id, pid, respostas[pid])
        assert resp.status_code == 200, resp.text
        proxima = resp.json()["proxima_pergunta"]
    return perguntadas


def test_sem_consentimento_retorna_422(client):
    resp = client.post("/atendimentos", json={"modo": "libras", "consentimento": False})
    assert resp.status_code == 422


def test_primeira_pergunta_e_motivo(client):
    assert iniciar(client)["proxima_pergunta"]["id"] == "motivo"


def test_motivo_exame_termina_rapido(client):
    a = iniciar(client)
    perguntadas = responder_tudo(client, a["id"], {"motivo": "exame", "prioridade": "nao"})
    assert perguntadas == ["motivo", "prioridade"]


def test_sintoma_dor_pede_local(client):
    a = iniciar(client, "libras")
    perguntadas = responder_tudo(client, a["id"], {
        "motivo": "sintoma", "sintoma": "dor", "local_dor": "cabeca",
        "intensidade": 5, "desde_quando": "hoje",
    })
    assert perguntadas == ["motivo", "sintoma", "local_dor", "intensidade", "desde_quando"]


def test_febre_nao_pede_local(client):
    a = iniciar(client, "voz")
    perguntadas = responder_tudo(client, a["id"], {
        "motivo": "sintoma", "sintoma": "febre", "intensidade": "6", "desde_quando": "1_3_dias",
    })
    assert "local_dor" not in perguntadas


def test_opcao_invalida_retorna_422(client):
    a = iniciar(client)
    assert responder(client, a["id"], "motivo", "passear").status_code == 422


def test_escala_fora_da_faixa_retorna_422(client):
    a = iniciar(client)
    responder(client, a["id"], "motivo", "sintoma")
    responder(client, a["id"], "sintoma", "tosse")
    assert responder(client, a["id"], "intensidade", 11).status_code == 422
    assert responder(client, a["id"], "intensidade", "muito").status_code == 422


def test_pergunta_fora_da_vez_retorna_422(client):
    a = iniciar(client)
    assert responder(client, a["id"], "intensidade", 3).status_code == 422


def test_finalizar_antes_da_hora_retorna_409(client):
    a = iniciar(client)
    assert client.post(f"/atendimentos/{a['id']}/finalizar").status_code == 409


def test_libras_pula_prioridade_e_recebe_preferencial(client):
    a = iniciar(client, "libras")
    perguntadas = responder_tudo(client, a["id"], {"motivo": "consulta"})
    assert "prioridade" not in perguntadas
    final = client.post(f"/atendimentos/{a['id']}/finalizar").json()
    assert final["senha"]["codigo"] == "P001"
    assert "P 0 0 1" in final["mensagem_final"]


def test_toque_sem_prioridade_recebe_normal(client):
    a = iniciar(client, "toque")
    responder_tudo(client, a["id"], {"motivo": "retorno", "prioridade": "nao"})
    final = client.post(f"/atendimentos/{a['id']}/finalizar").json()
    assert final["senha"]["codigo"] == "N001"


def test_toque_com_prioridade_recebe_preferencial(client):
    a = iniciar(client, "toque")
    responder_tudo(client, a["id"], {"motivo": "retorno", "prioridade": "sim"})
    final = client.post(f"/atendimentos/{a['id']}/finalizar").json()
    assert final["senha"]["tipo"] == "preferencial"


def test_finalizar_duas_vezes_retorna_409(client):
    a = iniciar(client, "libras")
    responder_tudo(client, a["id"], {"motivo": "exame"})
    assert client.post(f"/atendimentos/{a['id']}/finalizar").status_code == 200
    assert client.post(f"/atendimentos/{a['id']}/finalizar").status_code == 409
    assert responder(client, a["id"], "motivo", "exame").status_code == 409


def test_atendimento_inexistente_retorna_404(client):
    assert client.get("/atendimentos/999").status_code == 404


def test_finalizar_grava_queixa_e_resumo(client, session):
    a = iniciar(client, "libras")
    responder_tudo(client, a["id"], {
        "motivo": "sintoma", "sintoma": "dor", "local_dor": "peito",
        "intensidade": 9, "desde_quando": "hoje",
    })
    client.post(f"/atendimentos/{a['id']}/finalizar")

    atendimento = session.get(Atendimento, a["id"])
    assert atendimento.status == "finalizado"
    assert "Dor no peito" in atendimento.alertas
    assert "Libras" in atendimento.resumo
    queixa = session.exec(select(Queixa).where(Queixa.atendimento_id == a["id"])).one()
    assert (queixa.sintoma, queixa.local, queixa.intensidade) == ("dor", "peito", 9)


def test_aceita_nome_do_sinal_de_libras(client):
    a = iniciar(client, "libras")
    responder(client, a["id"], "motivo", "DOENTE")
    responder(client, a["id"], "sintoma", "DOR")
    resp = responder(client, a["id"], "local_dor", "CABEÇA").json()
    assert resp["respostas"] == {"motivo": "sintoma", "sintoma": "dor", "local_dor": "cabeca"}
    assert resp["canais"]["local_dor"] == "libras"
    resp = responder(client, a["id"], "intensidade", "SETE").json()
    assert resp["respostas"]["intensidade"] == 7


def test_aceita_rotulo_sem_acento_e_minusculo(client):
    a = iniciar(client, "voz")
    responder(client, a["id"], "motivo", "estou sentindo algo")
    resp = responder(client, a["id"], "sintoma", "falta de ar").json()
    assert resp["respostas"]["sintoma"] == "falta_de_ar"


def test_confianca_baixa_pede_para_repetir(client):
    a = iniciar(client, "libras")
    resp = client.post(
        f"/atendimentos/{a['id']}/respostas",
        json={"pergunta_id": "motivo", "valor": "EXAME", "canal": "libras", "confianca": 0.4},
    )
    corpo = resp.json()
    assert resp.status_code == 200
    assert corpo["repetir"] is True
    assert corpo["mensagem"]
    assert corpo["respostas"] == {}
    assert corpo["proxima_pergunta"]["id"] == "motivo"


def test_confianca_alta_grava(client):
    a = iniciar(client, "libras")
    corpo = client.post(
        f"/atendimentos/{a['id']}/respostas",
        json={"pergunta_id": "motivo", "valor": "EXAME", "canal": "libras", "confianca": 0.95},
    ).json()
    assert corpo["repetir"] is False
    assert corpo["respostas"] == {"motivo": "exame"}


def test_sinal_desconhecido_em_libras_pede_para_repetir(client):
    a = iniciar(client, "libras")
    corpo = responder(client, a["id"], "motivo", "CACHORRO").json()
    assert corpo["repetir"] is True
    assert corpo["respostas"] == {}


def test_canal_toque_em_atendimento_libras_grava_canal_toque(client):
    a = iniciar(client, "libras")
    corpo = client.post(
        f"/atendimentos/{a['id']}/respostas",
        json={"pergunta_id": "motivo", "valor": "exame", "canal": "toque"},
    ).json()
    assert corpo["canais"] == {"motivo": "toque"}


def test_perguntas_expoem_sinais(client):
    motivo = client.get("/conteudo/perguntas").json()[0]
    exame = next(o for o in motivo["opcoes"] if o["id"] == "exame")
    assert "EXAME" in exame["sinais"]


def test_conteudo(client):
    assert "consentimento" in client.get("/conteudo/textos").json()
    ids = [p["id"] for p in client.get("/conteudo/perguntas").json()]
    assert ids[0] == "motivo"
