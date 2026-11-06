"""Configuración común de los tests de la API (pytest la carga sola).

Para qué: prepara un entorno mínimo para poder importar la app y ofrece la fixture `client`
(un TestClient de FastAPI) que usan los demás ficheros de tests.

Por qué existe: app/main.py crea la app al importarse y exige las variables de entorno; aquí
se ponen valores falsos para que los tests arranquen sin `.env` y sin Postgres. Ningún test
toca una base de datos real: los que necesitan datos la sustituyen por un doble.

Cómo se ejecuta: `cd api && pytest -q`.
"""

import os

# app.main crea `app` al importar y necesita las variables; los tests nunca usan este valor
for k in ("POSTGRES_DB","POSTGRES_USER","POSTGRES_PASSWORD","APP_SECRET"):
    os.environ.setdefault(k,"test" if k != "APP_SECRET" else "0123456789abcdef0123456789abcdef0123456789abcdef")

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


@pytest.fixture
def client():
    """Cliente de pruebas con la app sin SPA ni base de datos."""
    s = Settings(postgres_db="t", postgres_user="t", postgres_password="t", app_secret="0123456789abcdef0123456789abcdef0123456789abcdef")
    return TestClient(create_app(s))
