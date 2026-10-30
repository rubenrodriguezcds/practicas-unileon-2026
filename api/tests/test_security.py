from app.security import hash_password, verify_password


def test_hash_y_verifica():
    h = hash_password("secreto")
    assert h.startswith("$2b$") and verify_password("secreto", h)


def test_contrasena_mala():
    assert not verify_password("otra", hash_password("secreto"))


def test_hash_corrupto_no_explota():  # Review Focus 3
    assert verify_password("x", "no-es-bcrypt") is False


def test_contrasena_larga_no_explota():  # Review Focus 2
    assert verify_password("a" * 100, hash_password("secreto")) is False

