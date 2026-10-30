import pytest
from pydantic import ValidationError

from app.config import Settings


def test_app_secret_corto_se_rechaza():
    with pytest.raises(ValidationError):
        Settings(postgres_db="t", postgres_user="t", postgres_password="t", app_secret="corto")
