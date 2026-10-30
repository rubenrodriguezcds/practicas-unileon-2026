from fastapi import FastAPI
from starlette.middleware.sessions import SessionMiddleware

from app.config import Settings, get_settings
from app.routers import auth
from app.spa import mount_spa


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    app = FastAPI(docs_url="/api/docs", openapi_url="/api/openapi.json")

    # https_only=False: en HTTP plano una cookie Secure no se guardaría
    app.add_middleware(SessionMiddleware, secret_key=settings.app_secret, https_only=False, same_site="lax")
    app.include_router(auth.router)

    @app.get("/api/health")
    def health():
        return {"status": "ok"}

    # después de los routers: el catch-all no debe taparlos
    if settings.static_dir:
        mount_spa(app, settings.static_dir)

    return app


# Con settings=None lee el entorno al importar; en tests se usa create_app(Settings(...)).
app = create_app()
