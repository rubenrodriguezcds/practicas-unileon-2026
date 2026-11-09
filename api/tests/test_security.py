"""Tests del hash y la verificación de contraseñas (security.py).

Para qué: asegurar que el hash es bcrypt y que la verificación nunca rompe la app: un hash
corrupto en la bbdd o una contraseña de más de 72 bytes deben dar «no coincide», no un error 500.
"""

from app.security import hash_password, verify_password


def test_hash_y_verifica():
    """El hash es bcrypt ($2b$) y la contraseña correcta lo verifica."""
    h = hash_password("secreto")
    assert h.startswith("$2b$") and verify_password("secreto", h)


def test_contrasena_mala():
    """Una contraseña distinta no verifica."""
    assert not verify_password("otra", hash_password("secreto"))


def test_hash_corrupto_no_explota():  # Review Focus 3
    """Un hash que no es bcrypt devuelve False en vez de lanzar."""
    assert verify_password("x", "no-es-bcrypt") is False


def test_contrasena_larga_no_explota():  # Review Focus 2
    """Contraseña > 72 bytes no debe dar 500: devuelve False."""
    assert verify_password("a" * 100, hash_password("secreto")) is False

