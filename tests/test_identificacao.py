import pytest

from app.services.identificacao import formatar_cpf, normalizar_cpf, normalizar_nome
from tests.test_atendimentos import CPF_VALIDO, finalizar, identificar, iniciar, responder_tudo

EXAME = {"motivo": "exame", "prioridade": "nao"}


@pytest.mark.parametrize("entrada", ["529.982.247-25", "52998224725", " 529 982 247 25 "])
def test_cpf_aceita_com_e_sem_mascara(entrada):
    assert normalizar_cpf(entrada) == "52998224725"


@pytest.mark.parametrize("entrada", ["529.982.247-26", "111.111.111-11", "123", "", "abc"])
def test_cpf_invalido(entrada):
    with pytest.raises(ValueError):
        normalizar_cpf(entrada)


def test_formatar_cpf():
    assert formatar_cpf("52998224725") == "529.982.247-25"


def test_nome_colapsa_espacos_e_rejeita_vazio():
    assert normalizar_nome("  Maria   da  Silva ") == "Maria da Silva"
    for invalido in ["", "   ", "1", "123 456"]:
        with pytest.raises(ValueError):
            normalizar_nome(invalido)


def test_atendimento_comeca_nao_identificado(client):
    assert iniciar(client)["identificado"] is False


def test_identificar_marca_identificado_sem_devolver_os_dados(client):
    a = iniciar(client)
    resp = identificar(client, a["id"])
    assert resp.status_code == 200
    corpo = resp.json()
    assert corpo["identificado"] is True
    assert "cpf" not in corpo and "nome" not in corpo
    assert client.get(f"/atendimentos/{a['id']}").json()["identificado"] is True


@pytest.mark.parametrize("nome,cpf", [("Maria", "529.982.247-26"), ("", CPF_VALIDO), ("Maria", "")])
def test_identificacao_invalida_retorna_422(client, nome, cpf):
    a = iniciar(client)
    assert identificar(client, a["id"], nome, cpf).status_code == 422
    assert client.get(f"/atendimentos/{a['id']}").json()["identificado"] is False


def test_identificar_atendimento_inexistente_retorna_404(client):
    assert identificar(client, 999).status_code == 404


def test_finalizar_sem_identificacao_retorna_409(client):
    a = iniciar(client)
    responder_tudo(client, a["id"], EXAME)
    resp = client.post(f"/atendimentos/{a['id']}/finalizar")
    assert resp.status_code == 409
    assert "CPF" in resp.json()["detail"]


def test_corrigir_antes_de_finalizar_sobrescreve(client):
    a = iniciar(client)
    responder_tudo(client, a["id"], EXAME)
    identificar(client, a["id"], nome="Nome Errado")
    identificar(client, a["id"], nome="Nome Certo", cpf="11144477735")
    client.post(f"/atendimentos/{a['id']}/finalizar")

    d = client.get(f"/recepcao/atendimentos/{a['id']}").json()
    assert d["nome"] == "Nome Certo"
    assert d["cpf"] == "111.444.777-35"
    assert "Paciente: Nome Certo" in d["resumo"]


def test_identificar_depois_de_finalizar_retorna_409(client):
    a = iniciar(client)
    responder_tudo(client, a["id"], EXAME)
    assert finalizar(client, a["id"]).status_code == 200
    assert identificar(client, a["id"], nome="Outro Nome").status_code == 409
