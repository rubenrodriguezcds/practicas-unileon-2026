"""Tests de la configuración (Settings).

Para qué: garantizar que la API se niega a arrancar con un APP_SECRET corto. Es una barrera
de seguridad: con un secreto conocido o débil cualquiera podría falsificar una sesión.
"""

import pytest
from pydantic import ValidationError

from app.config import Settings


def test_app_secret_corto_se_rechaza():
    """APP_SECRET de menos de 32 caracteres impide arrancar (firma de cookie débil)."""
    with pytest.raises(ValidationError):
        Settings(postgres_db="t", postgres_user="t", postgres_password="t", app_secret="corto")
