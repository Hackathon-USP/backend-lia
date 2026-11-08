import uuid

import pytest

from app.application.amostras_libras import ServicoAmostrasLibras
from app.application.relogio import agora_local
from app.domain.amostras_libras import AmostraInvalida, calcular_qualidade, validar_amostra

VLIBRAS = frozenset({"vlibras"})


def _quadro(t_ms: float, maos: bool = True) -> list[float]:
    quadro = [0.0] * 152
    quadro[0] = t_ms
    quadro[1] = 1 | (2 if maos else 0)  # corpo + mão direita
    quadro[2:26] = [0.5] * 24
    return quadro


def _amostra(gloss="DOR", source="vlibras", signer="vlibras-hosana", n=30, **extra):
    return {
        "id": extra.pop("id", str(uuid.uuid4())),
        "gloss": gloss,
        "source": source,
        "signer": signer,
        "createdAt": "2026-11-08T10:00:00.000Z",
        "origin": "vlibras:hosana:1:DOR",
        "format": "lia-raw-1",
        "width": 960,
        "height": 720,
        "frames": [_quadro(i * 33.3, maos=i % 3 != 0) for i in range(n)],
        # O back recalcula: este valor errado não pode passar.
        "quality": {"handsRatio": 1, "bodyRatio": 1, "durationMs": 1, "fps": 999},
        **extra,
    }


# --- Domínio ------------------------------------------------------------------


def test_valida_e_recalcula_a_qualidade():
    amostra = validar_amostra(_amostra(gloss="  cabeça "), VLIBRAS, agora_local())
    assert amostra.glosa == "CABEÇA"
    assert amostra.fonte == "vlibras"
    assert amostra.qualidade == calcular_qualidade(amostra.quadros)
    assert amostra.qualidade["handsRatio"] == pytest.approx(20 / 30, abs=1e-3)
    assert amostra.qualidade["bodyRatio"] == 1


@pytest.mark.parametrize(
    "alteracao, motivo",
    [
        ({"source": "proprio"}, "fonte não aceita"),
        ({"format": "outro"}, "formato"),
        ({"gloss": "  "}, "gloss ausente"),
        ({"frames": []}, "sem quadros"),
        ({"frames": [[0.0] * 10]}, "tamanho errado"),
        ({"frames": [[float("nan")] * 152]}, "valor inválido"),
        ({"width": 0}, "width/height"),
        ({"signer": ""}, "signer ausente"),
    ],
)
def test_recusa_amostras_invalidas(alteracao, motivo):
    with pytest.raises(AmostraInvalida, match=motivo):
        validar_amostra({**_amostra(), **alteracao}, VLIBRAS, agora_local())


def test_gravacoes_de_pessoas_so_entram_se_liberadas(uow):
    servico = ServicoAmostrasLibras(uow, fontes_aceitas=frozenset({"vlibras", "proprio"}))
    assert servico.enviar([_amostra(source="proprio")]).adicionadas == 1


# --- API ------------------------------------------------------------------------


def test_envia_ignora_repetidas_e_explica_as_invalidas(client):
    a, b = _amostra(), _amostra(gloss="FEBRE")
    resp = client.post("/libras/amostras", json={"amostras": [a, b, _amostra(source="v-librasil"), a]})
    assert resp.status_code == 200
    corpo = resp.json()
    assert corpo["adicionadas"] == 2
    assert corpo["ignoradas"] == 1  # `a` repetida no mesmo envio
    assert [i["indice"] for i in corpo["invalidas"]] == [2]
    assert "fonte não aceita" in corpo["invalidas"][0]["motivo"]

    # Reenviar não duplica.
    assert client.post("/libras/amostras", json={"amostras": [a]}).json() == {
        "adicionadas": 0,
        "ignoradas": 1,
        "invalidas": [],
    }


def test_lista_no_formato_de_dataset_do_front(client):
    enviada = _amostra(gloss="cabeça")
    client.post("/libras/amostras", json={"amostras": [enviada]})
    corpo = client.get("/libras/amostras").json()
    assert corpo["kind"] == "lia-dataset"
    assert corpo["version"] == 1
    assert corpo["format"] == "lia-raw-1"
    assert corpo["tem_mais"] is False
    [amostra] = corpo["samples"]
    assert amostra["id"] == enviada["id"]
    assert amostra["gloss"] == "CABEÇA"
    assert amostra["signer"] == "vlibras-hosana"
    assert amostra["frames"] == enviada["frames"]
    assert amostra["quality"]["fps"] != 999


def test_sincroniza_por_cursor_e_pagina(client):
    client.post("/libras/amostras", json={"amostras": [_amostra(gloss=g) for g in ["OI", "SIM", "NÃO"]]})
    p1 = client.get("/libras/amostras", params={"limite": 2}).json()
    assert [s["gloss"] for s in p1["samples"]] == ["OI", "SIM"]
    assert p1["tem_mais"] is True
    p2 = client.get("/libras/amostras", params={"limite": 2, "depois_de": p1["cursor"]}).json()
    assert [s["gloss"] for s in p2["samples"]] == ["NÃO"]
    assert p2["tem_mais"] is False

    # Na próxima sincronização, só vem o que chegou depois do cursor guardado.
    vazio = client.get("/libras/amostras", params={"depois_de": p2["cursor"]}).json()
    assert vazio["samples"] == [] and vazio["cursor"] == p2["cursor"]
    client.post("/libras/amostras", json={"amostras": [_amostra(gloss="AJUDA")]})
    novas = client.get("/libras/amostras", params={"depois_de": p2["cursor"]}).json()
    assert [s["gloss"] for s in novas["samples"]] == ["AJUDA"]


def test_filtra_por_glosa_e_fonte(client):
    client.post("/libras/amostras", json={"amostras": [_amostra(gloss="DOR"), _amostra(gloss="FEBRE")]})
    assert [s["gloss"] for s in client.get("/libras/amostras", params={"glosa": "dor"}).json()["samples"]] == ["DOR"]
    assert client.get("/libras/amostras", params={"fonte": "proprio"}).json()["samples"] == []


def test_resumo(client):
    client.post(
        "/libras/amostras",
        json={
            "amostras": [
                _amostra(gloss="DOR", signer="vlibras-hosana"),
                _amostra(gloss="DOR", signer="vlibras-icaro"),
                _amostra(gloss="FEBRE", signer="vlibras-icaro"),
            ]
        },
    )
    assert client.get("/libras/amostras/resumo").json() == {
        "total": 3,
        "por_glosa": {"DOR": 2, "FEBRE": 1},
        "por_fonte": {"vlibras": 3},
        "por_sinalizante": {"vlibras-hosana": 1, "vlibras-icaro": 2},
    }


def test_remove_com_filtro_obrigatorio(client):
    client.post("/libras/amostras", json={"amostras": [_amostra(gloss="DOR"), _amostra(gloss="FEBRE")]})
    assert client.delete("/libras/amostras").status_code == 422
    assert client.delete("/libras/amostras", params={"glosa": "dor"}).json() == {"removidas": 1}
    assert client.get("/libras/amostras/resumo").json()["por_glosa"] == {"FEBRE": 1}
    assert client.delete("/libras/amostras", params={"fonte": "vlibras"}).json() == {"removidas": 1}


def test_limite_de_amostras_por_envio(client):
    resp = client.post("/libras/amostras", json={"amostras": [{}] * 101})
    assert resp.status_code == 422


def test_resposta_grande_vem_compactada(client):
    client.post("/libras/amostras", json={"amostras": [_amostra(n=90) for _ in range(3)]})
    resp = client.get("/libras/amostras", headers={"Accept-Encoding": "gzip"})
    assert resp.headers.get("content-encoding") == "gzip"
    assert len(resp.json()["samples"]) == 3  # o httpx descompacta sozinho, como o navegador
