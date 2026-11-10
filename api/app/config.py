"""Configuración de la API leída de las variables de entorno.

Para qué: convierte las variables del `.env` (que docker compose inyecta en el contenedor)
en un objeto `Settings` tipado y validado.

Por qué existe: es el ÚNICO sitio que lee el entorno. Así, si falta una variable o tiene un
valor peligroso, la API se niega a arrancar con un error claro en vez de fallar más tarde a
mitad de una petición. Ejemplo: `APP_SECRET` exige ≥ 32 caracteres, porque quien conozca
el secreto podría fabricar cookies de sesión de cualquier usuario.

Quién lo usa: main.py (al crear la app), db.py (datos de conexión), captcha.py, mailer.py,
migrations.py y routers/auth.py.

Notas: los nombres de los campos coinciden con las variables sin distinguir mayúsculas
(`postgres_db` ← `POSTGRES_DB`). Las variables que no aparecen aquí (SSH_*, etc.) se ignoran.
"""

from functools import lru_cache
from typing import Literal

from pydantic import Field, model_validator
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

    # Email del admin: las migraciones se lo ponen al arrancar si aún no tiene (reseteo de contraseña).
    app_admin_email: str | None = None

    # Correo (app/mailer.py). Sin SMTP_HOST, el correo se escribe en el log: solo para desarrollo.
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = "no-reply@localhost"
    smtp_tls: Literal["starttls", "ssl", "none"] = "starttls"
    smtp_timeout: float = 10

    # Captcha ALTCHA (app/captcha.py). La clave firma los retos: quien la conozca podría fabricarlos.
    altcha_enabled: bool = True
    altcha_hmac_key: str = ""
    altcha_cost: int = 5000  # iteraciones PBKDF2 por intento: ~1 s en el navegador

    # Reseteos permitidos por hora, por usuario y por IP (más → 429).
    reset_max_por_hora: int = Field(default=5, ge=1)

    # Tamaño máximo de un documento adjunto (routers/proyectos.py). Los documentos se guardan en
    # Postgres y se cargan enteros en memoria al subir y descargar, así que el límite es bajo.
    documento_max_mb: int = Field(default=50, ge=1)

    @model_validator(mode="after")
    def _clave_altcha(self):
        """Con el captcha activo, exige ALTCHA_HMAC_KEY de ≥ 32 caracteres (como APP_SECRET)."""
        if self.altcha_enabled and len(self.altcha_hmac_key) < 32:
            raise ValueError("ALTCHA_HMAC_KEY debe tener al menos 32 caracteres (o ALTCHA_ENABLED=false)")
        return self


@lru_cache
def get_settings() -> Settings:
    """Devuelve la configuración, cacheada para leer el entorno una sola vez."""
    return Settings()
