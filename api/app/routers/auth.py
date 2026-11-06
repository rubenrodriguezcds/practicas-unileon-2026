"""Endpoints de autenticación: /api/auth/login, /logout, /me y /reset.

Para qué: es lo que llama el frontend (frontend/src/api/client.ts) para iniciar sesión,
cerrarla, saber al cargar la página si ya hay una sesión abierta y pedir una contraseña nueva.

Por qué existe: concentra el flujo de login en un solo sitio. Comprueba la contraseña contra
la tabla `usuarios` de Postgres y guarda el nombre de usuario en la cookie de sesión.

Contrato (el frontend depende de él):
  POST /api/auth/login   {"username","password","altcha"} → 200 {"username","es_admin"} + cookie
                         400 captcha no válido · 401 «Usuario o contraseña incorrectos» (mismo
                         mensaje si el usuario no existe, para no revelar qué usuarios hay)
                         · 422 campos vacíos · 503 bbdd caída
  POST /api/auth/logout  → 204, borra la sesión
  GET  /api/auth/me      → 200 {"username","es_admin"} · 401 si no hay sesión (o su usuario
                         ya no existe) · 503 bbdd caída
  POST /api/auth/reset   {"username","altcha"} → 202 {"detail": RESET_MSG} siempre (exista o
                         no el usuario, tenga o no email, falle o no el correo) · 400 captcha
                         · 429 demasiados intentos

Reseteo de contraseña (por qué es así):
  - La contraseña nueva se genera con `secrets` y se guarda como PENDIENTE (1 hora). La vieja
    sigue valiendo hasta que se entra con la nueva; si se entra con la vieja, la pendiente se
    descarta. Si cambiara al momento, cualquiera que sepa un nombre de usuario podría dejarlo
    sin acceso.
  - Se guarda la pendiente, se envía el correo y solo entonces commit: si el correo falla,
    rollback y nada cambia. El fallo queda en el log del servidor, pero el cliente recibe la
    misma respuesta que siempre.
  - Límite de RESET_MAX_POR_HORA intentos por usuario y por IP → 429. Afecta igual a usuarios
    que existen y que no, así que no revela nada, y el usuario legítimo sabe que debe esperar.
  - Los endpoints son `def` (no `async`): FastAPI los ejecuta en un threadpool, así que el envío
    SMTP no bloquea al resto de peticiones.

Quién lo usa: main.py lo registra; usa db.py (consultas), security.py (bcrypt), captcha.py y
mailer.py.
"""

import logging
import secrets
import smtplib

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field

from app import captcha, db, mailer
from app.db import get_conn
from app.deps import current_user
from app.security import hash_password, verify_password

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/auth")

RESET_MSG = "Si el usuario existe, recibirá un correo con una contraseña nueva."
RESET_SUBJECT = "Tu contraseña nueva"
RESET_BODY = """Hola, {username}:

Se ha pedido una contraseña nueva para tu cuenta. Es esta:

    {password}

Vale durante 1 hora. Tu contraseña actual sigue funcionando hasta que entres con la nueva.
Si no lo has pedido tú, ignora este correo.
"""


class LoginIn(BaseModel):
    """Cuerpo de POST /login; rechaza (422) usuario o contraseña vacíos."""

    username: str = Field(min_length=1)
    password: str = Field(min_length=1)
    altcha: str | None = None  # payload del captcha; captcha.verify decide si hace falta


class ResetIn(BaseModel):
    """Cuerpo de POST /reset; rechaza (422) usuario vacío."""

    username: str = Field(min_length=1, max_length=50)
    altcha: str | None = None


@router.post("/login")
def login(body: LoginIn, request: Request, conn=Depends(get_conn)):
    """Valida captcha y credenciales y guarda el usuario en la sesión (cookie firmada).

    Acepta la contraseña actual (y descarta una pendiente, si la hay) o la pendiente de un
    reseteo no caducado (que pasa a ser la contraseña del usuario).

    Returns:
        {"username": ...} del usuario autenticado.

    Raises:
        HTTPException: 400 si el captcha no es válido; 401 si el usuario no existe o la
            contraseña no coincide (mismo mensaje en ambos casos); 503 si la bbdd no está
            disponible.
    """
    captcha.verify(request.app.state.settings, conn, body.altcha)
    user = db.find_user(conn, body.username)
    # mismo mensaje para usuario inexistente y contraseña mala
    if user is None:
        raise HTTPException(401, "Usuario o contraseña incorrectos")
    if verify_password(body.password, user["password_hash"]):
        if user["reset_hash"]:
            db.discard_pending_password(conn, body.username)
    elif user["reset_hash"] and verify_password(body.password, user["reset_hash"]):
        db.promote_pending_password(conn, body.username)
    else:
        raise HTTPException(401, "Usuario o contraseña incorrectos")
    request.session["username"] = body.username
    return {"username": body.username, "es_admin": user["es_admin"]}


@router.post("/logout", status_code=204)
def logout(request: Request):
    """Cierra la sesión borrando su contenido; es idempotente (siempre 204)."""
    request.session.clear()
    return Response(status_code=204)


@router.get("/me")
def me(request: Request, conn=Depends(get_conn)):
    """Devuelve el usuario de la sesión actual y si es administrador.

    `es_admin` se lee de la bbdd en cada llamada (ver deps.py): el frontend lo usa para enseñar
    el menú de administración, pero quien protege de verdad es la API.

    Raises:
        HTTPException: 401 si no hay sesión iniciada o su usuario ya no existe.
    """
    username, es_admin = current_user(request, conn)
    return {"username": username, "es_admin": es_admin}


@router.post("/reset", status_code=202)
def reset(body: ResetIn, request: Request, conn=Depends(get_conn)):
    """Envía por correo una contraseña nueva (pendiente 1 hora) si el usuario existe y tiene email.

    Returns:
        202 {"detail": RESET_MSG}, siempre el mismo (ver «Reseteo» en la cabecera del módulo).

    Raises:
        HTTPException: 400 si el captcha no es válido; 429 si se supera el límite por hora;
            503 si la bbdd no está disponible.
    """
    s = request.app.state.settings
    captcha.verify(s, conn, body.altcha)

    ip = request.client.host if request.client else "desconocida"
    keys = [f"usuario:{body.username}", f"ip:{ip}"]
    if db.count_reset_attempts(conn, keys) >= s.reset_max_por_hora:
        raise HTTPException(429, "Demasiados intentos. Prueba más tarde.")
    db.add_reset_attempt(conn, keys)

    user = db.find_user(conn, body.username)
    if user and user["email"]:
        password = secrets.token_urlsafe(12)
        db.save_pending_password(conn, body.username, hash_password(password))
        try:
            mailer.send_mail(s, user["email"], RESET_SUBJECT, RESET_BODY.format(username=body.username, password=password))
        except (smtplib.SMTPException, OSError):
            conn.rollback()
            logger.exception("No se pudo enviar el correo de reseteo a %s; la contraseña no cambia", body.username)
        else:
            conn.commit()
    return {"detail": RESET_MSG}
