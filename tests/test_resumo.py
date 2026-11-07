from app.models import ModoAcessibilidade
from app.services.resumo import gerar_alertas, gerar_resumo


def test_dor_no_peito_gera_alerta():
    assert "Dor no peito" in gerar_alertas({"sintoma": "dor", "local_dor": "peito"})


def test_falta_de_ar_e_intensidade_alta_geram_alerta():
    alertas = gerar_alertas({"sintoma": "falta_de_ar", "intensidade": 8})
    assert "Falta de ar" in alertas
    assert "Intensidade alta (8/10)" in alertas


def test_sem_alerta_para_caso_leve():
    assert gerar_alertas({"sintoma": "tosse", "intensidade": 3}) == []


def test_resumo_cita_modo_e_queixa():
    respostas = {"motivo": "sintoma", "sintoma": "dor", "local_dor": "barriga",
                 "intensidade": 4, "desde_quando": "mais_3_dias"}
    texto = gerar_resumo("P007", ModoAcessibilidade.libras, respostas, [])
    assert "Senha: P007" in texto
    assert "Libras" in texto
    assert "Queixa principal: Dor (barriga)" in texto
    assert "Duração: Mais de 3 dias" in texto
    assert "ATENÇÃO" not in texto


def test_resumo_destaca_alertas():
    texto = gerar_resumo("N001", ModoAcessibilidade.voz, {"motivo": "sintoma"}, ["Falta de ar"])
    assert "ATENÇÃO: Falta de ar" in texto
