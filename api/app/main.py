"""Punto de entrada de la API: construye la aplicación FastAPI.

Para qué: junta las piezas en una app lista para servir: configuración, sesión por cookie,
endpoints (/api/health, /api/auth/*, /api/captcha, /api/roles, /api/usuarios) y, si procede, el frontend compilado.
Al arrancar aplica las migraciones de la bbdd pendientes (app/migrations.py).

Por qué existe: es el único sitio donde se conectan los módulos entre sí. Cada módulo nuevo
del gestor documental (p. ej. routers/documentos.py) se registra aquí con una línea.

Quién lo usa: uvicorn en el contenedor (`uvicorn app.main:app`, ver docker/web.Dockerfile) y
los tests, que llaman a `create_app(Settings(...))` con una configuración de prueba.

Notas:
  - La sesión es una cookie firmada con APP_SECRET, HttpOnly (el JavaScript no puede leerla)
    y sin `Secure` porque de momento se sirve por HTTP en el puerto 80.
  - El frontend se monta el ÚLTIMO, para que su ruta comodín no tape las de /api.
  - La documentación interactiva de la API queda en /api/docs.
  - La configuración queda en `app.state.settings` para que los endpoints usen la misma que
    recibió create_app (en tests, una de prueba).
  - El lifespan (migraciones) solo corre al arrancar el servidor; el TestClient de los tests
    no lo ejecuta salvo que se use con `with`, así que los tests no tocan una bbdd real.
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from starlette.middleware.sessions import SessionMiddleware

from app.config import Settings, get_settings
from app.migrations import migrate
from app.routers import auth, captcha, roles, usuarios
from app.spa import mount_spa

logger = logging.getLogger(__name__)


def create_app(settings: Settings | None = None) -> FastAPI:
    """Construye la aplicación FastAPI.

    Args:
        settings: configuración a usar; si es None se lee del entorno.
            Los tests pasan una explícita para no depender del entorno.

    Returns:
        La app con sesión por cookie, router de auth, /api/health y, si hay
        static_dir, la SPA servida como último recurso.
    """
    settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        """Al arrancar: migraciones pendientes y aviso si el captcha está desactivado."""
        migrate(settings)
        if not settings.altcha_enabled:
            logger.warning("Captcha DESACTIVADO (ALTCHA_ENABLED=false): solo para tests o desarrollo")
        yield

    app = FastAPI(docs_url="/api/docs", openapi_url="/api/openapi.json", lifespan=lifespan)
    app.state.settings = settings

    # https_only=False: en HTTP plano una cookie Secure no se guardaría
    app.add_middleware(SessionMiddleware, secret_key=settings.app_secret, https_only=False, same_site="lax")
    app.include_router(auth.router)
    app.include_router(captcha.router)
    app.include_router(roles.router)
    app.include_router(usuarios.router)

    @app.get("/api/health")
    def health():
        """Comprobación de vida: no toca la base de datos."""
        return {"status": "ok"}

    # después de los routers: el catch-all no debe taparlos
    if settings.static_dir:
        mount_spa(app, settings.static_dir)

    return app


# Con settings=None lee el entorno al importar; en tests se usa create_app(Settings(...)).
app = create_app()
