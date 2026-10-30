"""Configuración de la API leída de las variables de entorno.

Para qué: convierte las variables del `.env` (que docker compose inyecta en el contenedor)
en un objeto `Settings` tipado y validado.

Por qué existe: es el ÚNICO sitio que lee el entorno. Así, si falta una variable o tiene un
valor peligroso, la API se niega a arrancar con un error claro en vez de fallar más tarde a
mitad de una petición. Ejemplo: `APP_SECRET` exige ≥ 32 caracteres, porque quien conozca
el secreto podría fabricar cookies de sesión de cualquier usuario.

Quién lo usa: main.py (al crear la app) y db.py (datos de conexión).

Notas: los nombres de los campos coinciden con las variables sin distinguir mayúsculas
(`postgres_db` ← `POSTGRES_DB`). Las variables que no aparecen aquí (SSH_*, etc.) se ignoran.
"""

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configuración de la app leída del entorno (o del constructor en tests).

    Falla al arrancar si falta alguna variable obligatoria o si APP_SECRET
    tiene menos de 32 caracteres.
    """

    model_config = SettingsConfigDict(hide_input_in_errors=True)  # no volcar APP_SECRET en el traceback

    # pydantic-settings ignora mayúsculas: POSTGRES_DB -> postgres_db
    postgres_db: str
    postgres_user: str
    postgres_password: str
    db_host: str = "localhost"
    db_port: int = 5432
    app_secret: str = Field(min_length=32)
    static_dir: str | None = None


@lru_cache
def get_settings() -> Settings:
    """Devuelve la configuración, cacheada para leer el entorno una sola vez."""
    return Settings()
