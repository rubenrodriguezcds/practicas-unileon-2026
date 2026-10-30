"""Tests del servido del frontend compilado (spa.py).

Para qué: comprobar lo que haría fallar la web en el contenedor aunque la API funcione:
recargar en /login debe devolver index.html, los ficheros de assets se sirven tal cual, las
rutas /api inexistentes dan 404 en JSON y ninguna ruta puede salirse de la carpeta de estáticos.

Cómo: crea una carpeta temporal que imita el `dist/` de Vite; no hace falta compilar React.
"""

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


def make(static_dir):
    """Crea un cliente con la app configurada con ese static_dir (o None)."""
    return TestClient(create_app(Settings(
        postgres_db="t", postgres_user="t", postgres_password="t", app_secret="0123456789abcdef0123456789abcdef0123456789abcdef", static_dir=static_dir)))


@pytest.fixture
def spa(tmp_path):
    """Cliente sobre un static_dir temporal con index.html y assets/app.js."""
    (tmp_path / "index.html").write_text('<div id="root"></div>')
    (tmp_path / "assets").mkdir()
    (tmp_path / "assets" / "app.js").write_text("console.log(1)")
    return make(str(tmp_path))


def test_raiz_sirve_index(spa):
    """/ sirve index.html."""
    r = spa.get("/")
    assert r.status_code == 200 and 'id="root"' in r.text


def test_recarga_en_login_sirve_index(spa):  # Review Focus 1
    """Recargar en una ruta del cliente (/login) sirve index.html, no 404."""
    r = spa.get("/login")
    assert r.status_code == 200 and 'id="root"' in r.text


def test_asset_existente(spa):
    """Los ficheros de /assets se sirven tal cual."""
    assert spa.get("/assets/app.js").status_code == 200


def test_api_inexistente_es_404_json(spa):
    """Una ruta /api desconocida da 404 JSON, no el HTML de la SPA."""
    r = spa.get("/api/nada")
    assert r.status_code == 404 and r.json()


def test_api_health_sigue_funcionando(spa):
    """El catch-all de la SPA no tapa los endpoints de /api."""
    assert spa.get("/api/health").json() == {"status": "ok"}


def test_no_sale_de_static_dir(tmp_path):
    """Path traversal (../) no puede leer ficheros fuera de static_dir."""
    (tmp_path / "dist" / "assets").mkdir(parents=True)
    (tmp_path / "dist" / "index.html").write_text('<div id="root"></div>')
    (tmp_path / "secreto.txt").write_text("fuera")
    c = make(str(tmp_path / "dist"))
    r = c.get("/%2e%2e/secreto.txt")
    assert "fuera" not in r.text


def test_sin_static_dir_no_monta():
    """Sin static_dir (modo desarrollo) no se monta la SPA y / da 404."""
    assert make(None).get("/").status_code == 404
