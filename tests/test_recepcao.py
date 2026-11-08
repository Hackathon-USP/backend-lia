from tests.test_atendimentos import iniciar, responder_tudo

DOR_NO_PEITO = {
    "motivo": "sintoma", "sintoma": "dor", "local_dor": "peito",
    "intensidade": 9, "desde_quando": "hoje",
}


def atender(client, modo, respostas):
    """Faz a triagem completa e finaliza. Devolve (atendimento_id, codigo_senha)."""
    a = iniciar(client, modo)
    responder_tudo(client, a["id"], respostas)
    resp = client.post(f"/atendimentos/{a['id']}/finalizar")
    assert resp.status_code == 200, resp.text
    return a["id"], resp.json()["senha"]["codigo"]


def test_fila_vazia(client):
    assert client.get("/recepcao/fila").json() == []
    assert client.post("/recepcao/chamar").status_code == 404


def test_fila_poe_preferencial_antes_da_normal(client):
    id_normal, normal = atender(client, "toque", {"motivo": "exame", "prioridade": "nao"})
    id_pref, pref = atender(client, "libras", DOR_NO_PEITO)

    fila = client.get("/recepcao/fila").json()
    assert [i["codigo"] for i in fila] == [pref, normal]
    assert fila[0]["atendimento_id"] == id_pref
    assert fila[0]["modo"] == "libras"
    assert "Dor no peito" in fila[0]["alertas"]
    assert fila[1]["alertas"] == []


def test_fila_inclui_senha_avulsa_sem_atendimento(client):
    client.post("/senhas", json={"tipo": "normal"})
    [item] = client.get("/recepcao/fila").json()
    assert item["atendimento_id"] is None and item["modo"] is None


def test_detalhe_traz_resumo_alertas_e_rotulos(client):
    id_, codigo = atender(client, "voz", DOR_NO_PEITO)
    d = client.get(f"/recepcao/atendimentos/{id_}").json()

    assert d["senha"] == codigo
    assert d["senha_detalhe"]["status"] == "aguardando"
    assert d["status"] == "finalizado"
    assert "Dor no peito" in d["alertas"] and "Intensidade alta (9/10)" in d["alertas"]
    assert "ATENÇÃO" in d["resumo"]
    assert d["queixa"] == {"sintoma": "dor", "local": "peito", "intensidade": 9, "desde_quando": "hoje"}
    respostas = {r["pergunta_id"]: r for r in d["respostas"]}
    assert [r["pergunta_id"] for r in d["respostas"]] == list(DOR_NO_PEITO)
    assert respostas["local_dor"]["resposta"] == "Peito"
    assert respostas["local_dor"]["canal"] == "voz"


def test_detalhe_de_atendimento_em_andamento(client):
    a = iniciar(client, "toque")
    d = client.get(f"/recepcao/atendimentos/{a['id']}").json()
    assert d["status"] == "em_andamento" and d["senha"] is None and d["respostas"] == []


def test_detalhe_inexistente_retorna_404(client):
    assert client.get("/recepcao/atendimentos/999").status_code == 404


def test_chamar_segue_a_ordem_e_marca_em_atendimento(client):
    _, normal = atender(client, "toque", {"motivo": "exame", "prioridade": "nao"})
    id_pref, pref = atender(client, "libras", DOR_NO_PEITO)

    primeira = client.post("/recepcao/chamar").json()
    assert primeira["senha"]["codigo"] == pref
    assert primeira["senha"]["status"] == "em_atendimento"
    assert primeira["atendimento_id"] == id_pref
    assert "Dor no peito" in primeira["alertas"] and primeira["resumo"]

    assert client.post("/recepcao/chamar").json()["senha"]["codigo"] == normal
    assert client.post("/recepcao/chamar").status_code == 404

    aguardando = client.get("/recepcao/fila", params={"status": "aguardando"}).json()
    assert aguardando == []


def test_patch_finaliza_senha(client):
    _, codigo = atender(client, "toque", {"motivo": "exame", "prioridade": "nao"})
    resp = client.patch(f"/recepcao/senhas/{codigo.lower()}", json={"status": "finalizada"})
    assert resp.status_code == 200
    assert resp.json()["status"] == "finalizada"
    # Senha finalizada não volta a ser chamada.
    assert client.post("/recepcao/chamar").status_code == 404


def test_patch_senha_inexistente_retorna_404(client):
    resp = client.patch("/recepcao/senhas/N999", json={"status": "finalizada"})
    assert resp.status_code == 404


def test_listar_atendimentos_com_filtros(client):
    id_toque, _ = atender(client, "toque", {"motivo": "exame", "prioridade": "nao"})
    id_libras, _ = atender(client, "libras", DOR_NO_PEITO)
    id_aberto = iniciar(client, "voz")["id"]

    todos = client.get("/recepcao/atendimentos").json()
    assert [a["id"] for a in todos] == [id_aberto, id_libras, id_toque]

    libras = client.get("/recepcao/atendimentos", params={"modo": "libras"}).json()
    assert [a["id"] for a in libras] == [id_libras]

    abertos = client.get("/recepcao/atendimentos", params={"status": "em_andamento"}).json()
    assert [a["id"] for a in abertos] == [id_aberto]

    outro_dia = client.get("/recepcao/atendimentos", params={"data": "2000-01-01"}).json()
    assert outro_dia == []



def test_filtro_por_data_usa_o_dia_local(session):
    # 22h em São Paulo já é dia seguinte em UTC; deve contar como o dia local.
    from datetime import date, datetime
    from zoneinfo import ZoneInfo

    from app.models import ModoAcessibilidade
    from app.services import atendimento, recepcao

    noite = datetime(2026, 3, 10, 22, 0, tzinfo=ZoneInfo("America/Sao_Paulo"))
    a = atendimento.iniciar(session, ModoAcessibilidade.toque, noite)
    assert [x.id for x, _ in recepcao.listar_atendimentos(session, date(2026, 3, 10))] == [a.id]
    assert recepcao.listar_atendimentos(session, date(2026, 3, 11)) == []
