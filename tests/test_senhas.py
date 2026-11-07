from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from sqlmodel import Session

from app.db import criar_engine, init_db
from app.models import TipoSenha
from app.services import fila


def test_emite_senhas_sequenciais_por_tipo(client):
    codigos = [client.post("/senhas", json={"tipo": t}).json()["codigo"]
               for t in ["normal", "preferencial", "normal", "preferencial", "normal"]]
    assert codigos == ["N001", "P001", "N002", "P002", "N003"]


def test_resposta_da_emissao(client):
    resp = client.post("/senhas", json={"tipo": "preferencial"})
    assert resp.status_code == 201
    corpo = resp.json()
    assert corpo["codigo"] == "P001"
    assert corpo["tipo"] == "preferencial"
    assert corpo["numero"] == 1
    assert corpo["status"] == "aguardando"
    assert "criada_em" in corpo


def test_tipo_invalido_retorna_422(client):
    assert client.post("/senhas", json={"tipo": "vip"}).status_code == 422


def test_consulta_senha(client):
    client.post("/senhas", json={"tipo": "normal"})
    assert client.get("/senhas/n001").json()["codigo"] == "N001"
    assert client.get("/senhas/N999").status_code == 404


def test_numeracao_reinicia_no_dia_seguinte(session):
    hoje = datetime(2026, 3, 10, 23, 50, tzinfo=ZoneInfo("America/Sao_Paulo"))
    assert fila.emitir_senha(session, TipoSenha.normal, hoje).codigo == "N001"
    assert fila.emitir_senha(session, TipoSenha.normal, hoje).codigo == "N002"
    amanha = hoje + timedelta(minutes=20)
    assert fila.emitir_senha(session, TipoSenha.normal, amanha).codigo == "N001"


def test_emissao_concorrente_sem_duplicidade(tmp_path):
    # Banco em arquivo para que cada thread tenha sua própria conexão de verdade.
    eng = criar_engine(f"sqlite:///{tmp_path / 'concorrente.db'}")
    init_db(eng)

    def emitir(_):
        with Session(eng) as s:
            return fila.emitir_senha(s, TipoSenha.normal).numero

    with ThreadPoolExecutor(max_workers=8) as pool:
        numeros = list(pool.map(emitir, range(40)))
    eng.dispose()

    assert sorted(numeros) == list(range(1, 41))
