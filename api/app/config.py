from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
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
    return Settings()
