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
    s = Settings(postgres_db="t", postgres_user="t", postgres_password="t", app_secret="0123456789abcdef0123456789abcdef0123456789abcdef")
    return TestClient(create_app(s))
