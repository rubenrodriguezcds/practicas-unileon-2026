"""Endpoint GET /api/captcha: entrega un reto ALTCHA nuevo al widget del navegador.

Para qué: el componente Captcha del frontend (frontend/src/components/Captcha.tsx) lo pide al
montarse y cada vez que se reinicia tras un fallo.

Quién lo usa: main.py lo registra; la lógica está en app/captcha.py.
"""

from fastapi import APIRouter, Request, Response

from app.captcha import new_challenge

router = APIRouter(prefix="/api")


@router.get("/captcha")
def captcha(request: Request, response: Response) -> dict:
    """Devuelve un reto firmado que caduca en 5 minutos."""
    response.headers["Cache-Control"] = "no-store"  # cada petición, un reto distinto
    return new_challenge(request.app.state.settings)
