"""Tests de la configuración (Settings).

Para qué: garantizar que la API se niega a arrancar con un APP_SECRET o un ALTCHA_HMAC_KEY
cortos, o un SMTP_TLS desconocido. Es una barrera
de seguridad: con un secreto conocido o débil cualquiera podría falsificar una sesión.
"""

import pytest
from pydantic import ValidationError

from app.config import Settings
from tests.factories import make_settings


def test_app_secret_corto_se_rechaza():
    """APP_SECRET de menos de 32 caracteres impide arrancar (firma de cookie débil)."""
    with pytest.raises(ValidationError):
        Settings(postgres_db="t", postgres_user="t", postgres_password="t", app_secret="corto")


def test_altcha_hmac_key_obligatoria_con_captcha_activo():
    """Con el captcha activo, una clave corta o vacía impide arrancar (retos falsificables)."""
    for key in ("", "corta"):
        with pytest.raises(ValidationError):
            make_settings(altcha_hmac_key=key)


def test_captcha_desactivado_no_exige_clave():
    assert make_settings(altcha_enabled=False, altcha_hmac_key="").altcha_enabled is False


def test_smtp_tls_solo_valores_conocidos():
    with pytest.raises(ValidationError):
        make_settings(smtp_tls="tls")
