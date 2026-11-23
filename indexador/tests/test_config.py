"""Tests de config.py: la lectura y validación del entorno del indexador."""

import pytest
from config import ConfigError, leer_config

BASE = {"POSTGRES_DB": "gestor", "POSTGRES_USER": "app", "POSTGRES_PASSWORD": "p@ss/1"}


def test_valores_por_defecto():
    cfg = leer_config(BASE)
    assert cfg.docling_url == "http://docling:5001"
    assert (cfg.ollama_url, cfg.embeddings_modelo) == ("http://localhost:11434", "bge-m3")
    assert (cfg.max_intentos, cfg.colgado_min, cfg.espera_s) == (3, 30, 5)
    # La contraseña va escapada en la URL de conexión.
    assert cfg.db_dsn == "postgresql://app:p%40ss%2F1@localhost:5432/gestor"


def test_lee_host_docling_ollama_y_ajustes():
    cfg = leer_config({**BASE, "DB_HOST": "db", "DOCLING_URL": "http://otro:5001/",
                       "OLLAMA_URL": "http://host.docker.internal:11435/", "EMBEDDINGS_MODELO": "otro",
                       "INDEXADOR_MAX_INTENTOS": "5"})
    assert "@db:5432/" in cfg.db_dsn
    assert cfg.docling_url == "http://otro:5001"
    assert cfg.ollama_url == "http://host.docker.internal:11435"
    assert cfg.embeddings_modelo == "otro" and cfg.max_intentos == 5


def test_sin_password_de_la_bbdd_es_error_claro():
    with pytest.raises(ConfigError, match="POSTGRES_PASSWORD"):
        leer_config({k: v for k, v in BASE.items() if k != "POSTGRES_PASSWORD"})


def test_variables_de_ollama_vacias_usan_los_valores_por_defecto():
    cfg = leer_config({**BASE, "OLLAMA_URL": "", "EMBEDDINGS_MODELO": ""})
    assert (cfg.ollama_url, cfg.embeddings_modelo) == ("http://localhost:11434", "bge-m3")


def test_ajuste_no_numerico_es_error_claro():
    with pytest.raises(ConfigError, match="INDEXADOR_"):
        leer_config({**BASE, "INDEXADOR_ESPERA_S": "cinco"})
