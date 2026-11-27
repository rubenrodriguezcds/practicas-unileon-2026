"""Configuración del indexador leída de las variables de entorno.

Para qué: convierte las variables del `.env` (que docker compose inyecta) en un objeto `Config`.

Por qué existe: es el ÚNICO sitio que lee el entorno (validar en la frontera). Si falta la
conexión a la bbdd el indexador no arranca, con un error claro. Ollama (embeddings) tiene valores
por defecto: si no responde, el indexador arranca igual y cada documento queda reintentable y luego
en «error» con el motivo, visible en la ficha del proyecto (avisar, no bloquear).

Quién lo usa: main.py al arrancar.
"""

from dataclasses import dataclass
from urllib.parse import quote


@dataclass(frozen=True)
class Config:
    db_dsn: str
    docling_url: str
    ollama_url: str = "http://localhost:11434"   # en Docker con el túnel: http://host.docker.internal:11435
    embeddings_modelo: str = "bge-m3"
    max_intentos: int = 3   # fallos seguidos antes de dejar el documento en «error»
    colgado_min: int = 30   # un «procesando» más antiguo se da por colgado y se reintenta
    espera_s: int = 5       # pausa cuando no hay nada que indexar


class ConfigError(Exception):
    """Falta una variable obligatoria o tiene un valor no válido."""


def leer_config(env: dict[str, str]) -> Config:
    """Config a partir del entorno (os.environ en main.py; un dict en los tests)."""
    faltan = [v for v in ("POSTGRES_DB", "POSTGRES_USER", "POSTGRES_PASSWORD") if not env.get(v)]
    if faltan:
        raise ConfigError(f"Faltan variables en el .env: {', '.join(faltan)}")
    try:
        enteros = {k: int(env[v]) for k, v in (("max_intentos", "INDEXADOR_MAX_INTENTOS"),
                                               ("colgado_min", "INDEXADOR_COLGADO_MIN"),
                                               ("espera_s", "INDEXADOR_ESPERA_S")) if env.get(v)}
    except ValueError as e:
        raise ConfigError(f"Valor no numérico en una variable INDEXADOR_*: {e}") from None
    # quote: una contraseña con @, / o espacios rompería la URL de conexión.
    dsn = (f"postgresql://{quote(env['POSTGRES_USER'], safe='')}:{quote(env['POSTGRES_PASSWORD'], safe='')}"
           f"@{env.get('DB_HOST', 'localhost')}:{env.get('DB_PORT', '5432')}/{quote(env['POSTGRES_DB'], safe='')}")
    return Config(
        db_dsn=dsn,
        docling_url=env.get("DOCLING_URL", "http://docling:5001").rstrip("/"),
        ollama_url=(env.get("OLLAMA_URL") or Config.ollama_url).rstrip("/"),
        embeddings_modelo=env.get("EMBEDDINGS_MODELO") or Config.embeddings_modelo,
        **enteros,
    )
