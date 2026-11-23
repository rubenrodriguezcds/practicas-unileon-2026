"""Tests de config.py: la lectura y validación del entorno del indexador."""

import pytest
from config import ConfigError, leer_config

BASE = {"POSTGRES_DB": "gestor", "POSTGRES_USER": "app", "POSTGRES_PASSWORD": "p@ss/1"}


def test_valores_por_defecto():
    cfg = leer_config(BASE)
    assert cfg.docling_url == "http://docling:5001"
    assert (cfg.max_intentos, cfg.colgado_min, cfg.espera_s) == (3, 30, 5)
    # La contraseña va escapada en la URL de conexión.
    assert cfg.db_dsn == "postgresql://app:p%40ss%2F1@localhost:5432/gestor"


def test_lee_host_docling_y_ajustes():
    cfg = leer_config({**BASE, "DB_HOST": "db", "DOCLING_URL": "http://otro:5001/",
                       "INDEXADOR_MAX_INTENTOS": "5", "OPENAI_API_KEY": "sk-x"})
    assert "@db:5432/" in cfg.db_dsn
    assert cfg.docling_url == "http://otro:5001"
    assert cfg.max_intentos == 5 and cfg.openai_api_key == "sk-x"


def test_sin_password_de_la_bbdd_es_error_claro():
    with pytest.raises(ConfigError, match="POSTGRES_PASSWORD"):
        leer_config({k: v for k, v in BASE.items() if k != "POSTGRES_PASSWORD"})


def test_sin_api_key_arranca_con_none():
    assert leer_config({**BASE, "OPENAI_API_KEY": ""}).openai_api_key is None


def test_ajuste_no_numerico_es_error_claro():
    with pytest.raises(ConfigError, match="INDEXADOR_"):
        leer_config({**BASE, "INDEXADOR_ESPERA_S": "cinco"})
