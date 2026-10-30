"""Endpoints de autenticación: /api/auth/login, /logout y /me.

Para qué: es lo que llama el frontend (frontend/src/api/client.ts) para iniciar sesión,
cerrarla y saber al cargar la página si ya hay una sesión abierta.

Por qué existe: concentra el flujo de login en un solo sitio. Comprueba la contraseña contra
la tabla `usuarios` de Postgres y guarda el nombre de usuario en la cookie de sesión.

Contrato (el frontend depende de él):
  POST /api/auth/login   {"username","password"} → 200 {"username"} + cookie
                         401 «Usuario o contraseña incorrectos» (mismo mensaje si el usuario
                         no existe, para no revelar qué usuarios hay) · 422 campos vacíos
  POST /api/auth/logout  → 204, borra la sesión
  GET  /api/auth/me      → 200 {"username"} · 401 si no hay sesión

Quién lo usa: main.py lo registra; usa db.py (consultas) y security.py (bcrypt).
"""

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field

from app.db import find_password_hash, get_conn
from app.security import verify_password

router = APIRouter(prefix="/api/auth")


class LoginIn(BaseModel):
    """Cuerpo de POST /login; rechaza (422) usuario o contraseña vacíos."""

    username: str = Field(min_length=1)
    password: str = Field(min_length=1)


@router.post("/login")
def login(body: LoginIn, request: Request, conn=Depends(get_conn)):
    """Valida credenciales y guarda el usuario en la sesión (cookie firmada).

    Returns:
        {"username": ...} del usuario autenticado.

    Raises:
        HTTPException: 401 si el usuario no existe o la contraseña no coincide
            (mismo mensaje en ambos casos); 503 si la bbdd no está disponible.
    """
    hashed = find_password_hash(conn, body.username)
    # mismo mensaje para usuario inexistente y contraseña mala
    if hashed is None or not verify_password(body.password, hashed):
        raise HTTPException(401, "Usuario o contraseña incorrectos")
    request.session["username"] = body.username
    return {"username": body.username}


@router.post("/logout", status_code=204)
def logout(request: Request):
    """Cierra la sesión borrando su contenido; es idempotente (siempre 204)."""
    request.session.clear()
    return Response(status_code=204)


@router.get("/me")
def me(request: Request):
    """Devuelve el usuario de la sesión actual.

    Raises:
        HTTPException: 401 si no hay sesión iniciada.
    """
    username = request.session.get("username")
    if not username:
        raise HTTPException(401, "No autenticado")
    return {"username": username}
