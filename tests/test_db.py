import pytest

from app.persistence.db import normalizar_url


@pytest.mark.parametrize(
    ("entrada", "esperado"),
    [
        ("postgres://u:s@host:5432/lia", "postgresql+psycopg://u:s@host:5432/lia"),
        ("postgresql://u:s@host/lia", "postgresql+psycopg://u:s@host/lia"),
        ("  postgresql://u:s@host/lia\n", "postgresql+psycopg://u:s@host/lia"),
        ("postgresql+psycopg://u:s@host/lia", "postgresql+psycopg://u:s@host/lia"),
        ("sqlite:///./totem.db", "sqlite:///./totem.db"),
    ],
)
def test_normalizar_url_usa_psycopg_no_postgres(entrada, esperado):
    assert normalizar_url(entrada) == esperado
