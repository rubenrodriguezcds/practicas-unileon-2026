"""Endpoints de gestión de usuarios: /api/usuarios (issue #6).

Para qué: es lo que llama la pantalla de usuarios del frontend para listar, crear, editar o
renombrar y borrar usuarios (de uno en uno o en lote), ver el detalle de cada uno con sus roles,
asociarle o quitarle roles y marcarlo como administrador.

Por qué existe: la issue #6 pide un menú de gestión de usuarios SOLO para el administrador. Todo el
router depende de `require_admin` (app/deps.py): 401 sin sesión, 403 si no es admin.

Contrato (el frontend depende de él):
  GET    /api/usuarios                      → 200 [{"id","username","email","es_admin","num_roles"}] por nombre
  GET    /api/usuarios/{id}                 → 200 {"id","username","email","es_admin","roles":[…]} · 404
  POST   /api/usuarios {"username","email","es_admin"} → 201 usuario · 409 nombre repetido
                                              · 502 no se pudo enviar el correo (el usuario NO se crea)
  PUT    /api/usuarios/{id} {"username","email","es_admin"} → 200 usuario · 404 · 409 nombre repetido
                                              · 409 quitarse a sí mismo el permiso de administrador
  DELETE /api/usuarios/{id}                 → 204 · 404 · 409 si es uno mismo
  POST   /api/usuarios/borrar {"ids":[…]}   → 200 {"borrados": n} · 409 si incluye a uno mismo (no borra nada)
  PUT    /api/usuarios/{id}/roles/{rol_id}  → 204 (si ya lo tenía, igual) · 404 usuario o rol inexistente
  DELETE /api/usuarios/{id}/roles/{rol_id}  → 204 (si no lo tenía, igual)
  En todos: 401 sin sesión · 403 si no es administrador · 422 datos no válidos · 503 bbdd caída.

Decisiones:
  - La contraseña del usuario nuevo la genera la API (`secrets`) y la envía por correo al usuario:
    el administrador nunca la conoce. Por eso el email es obligatorio al crear. El alta solo se
    confirma si el correo sale; si falla, rollback y 502, y el administrador lo sabe al momento
    (a diferencia del reseteo, aquí no hay nada que ocultar: quien pregunta ya es administrador).
  - El administrador no puede borrarse a sí mismo ni quitarse su propio permiso. Como quien hace
    la petición siempre es administrador, eso basta para que siempre quede al menos uno.
  - El borrado en lote es todo o nada respecto a uno mismo: si la lista te incluye, no se borra
    ninguno, para que no parezca que se ha hecho a medias.
  - Nombre de usuario: 1–50 caracteres (la columna es VARCHAR(50)), solo letras, números y . _ -
    (se escribe al iniciar sesión, mejor sin espacios ni acentos).

Quién lo usa: main.py lo registra; usa db.py (consultas), deps.py (permisos), security.py (bcrypt)
y mailer.py (correo).
"""

import logging
import secrets
import smtplib
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field, StringConstraints, field_validator

from app import db, mailer
from app.db import get_conn
from app.deps import require_admin
from app.security import hash_password

logger = logging.getLogger(__name__)

# Todo el router exige administrador: no hay forma de añadir un endpoint aquí y olvidarse.
router = APIRouter(prefix="/api/usuarios", dependencies=[Depends(require_admin)])

DUPLICADO_MSG = "Ya existe un usuario con ese nombre"
NO_EXISTE_MSG = "El usuario no existe"
AUTOBORRADO_MSG = "No puedes borrar tu propio usuario"
CORREO_MSG = ("No se ha podido enviar el correo con la contraseña, así que el usuario no se ha creado. "
              "Revisa el email o inténtalo más tarde.")

ALTA_SUBJECT = "Tu cuenta en el gestor documental"
ALTA_BODY = """Hola, {username}:

Se ha creado una cuenta para ti en el gestor documental.

    Usuario: {username}
    Contraseña: {password}

Guárdala en un sitio seguro. Si la pierdes, puedes pedir una nueva desde «¿Olvidaste tu
contraseña?» en la pantalla de inicio de sesión.
"""

Username = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=50, pattern=r"^[A-Za-z0-9._-]+$")]
Email = Annotated[str, StringConstraints(strip_whitespace=True, max_length=255, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")]


class UsuarioNuevo(BaseModel):
    """Cuerpo de POST. El email es obligatorio: ahí se envía la contraseña."""

    username: Username
    email: Email
    es_admin: bool = False


class UsuarioEditado(BaseModel):
    """Cuerpo de PUT. El email vacío se guarda como NULL (el usuario no podrá resetear su contraseña).

    `es_admin` es obligatorio: si faltara y valiera false por defecto, editar el nombre de otro
    administrador le quitaría el permiso sin querer.
    """

    username: Username
    email: Email | None = None
    es_admin: bool

    @field_validator("email", mode="before")
    @classmethod
    def vacio_es_none(cls, v):
        return None if isinstance(v, str) and not v.strip() else v


class Lote(BaseModel):
    """Cuerpo de POST /borrar."""

    ids: list[int] = Field(min_length=1, max_length=500)


@router.get("")
def listar(conn=Depends(get_conn)):
    """Todos los usuarios, con cuántos roles tiene cada uno."""
    return db.list_users(conn)


@router.get("/{user_id}")
def detalle(user_id: int, conn=Depends(get_conn)):
    """Un usuario con la lista de sus roles.

    Raises:
        HTTPException: 404 si no existe.
    """
    user = db.get_user(conn, user_id)
    if user is None:
        raise HTTPException(404, NO_EXISTE_MSG)
    return user


@router.post("", status_code=201)
def crear(body: UsuarioNuevo, request: Request, conn=Depends(get_conn)):
    """Crea un usuario y le envía por correo una contraseña generada.

    Raises:
        HTTPException: 409 si el nombre ya existe; 502 si el correo no sale (el usuario no se crea).
    """
    password = secrets.token_urlsafe(12)
    try:
        user = db.create_user(conn, body.username, body.email, body.es_admin, hash_password(password))
    except db.NombreDuplicado:
        raise HTTPException(409, DUPLICADO_MSG) from None
    try:
        mailer.send_mail(request.app.state.settings, body.email, ALTA_SUBJECT,
                         ALTA_BODY.format(username=body.username, password=password))
    except (smtplib.SMTPException, OSError):
        conn.rollback()
        logger.exception("No se pudo enviar el correo de alta a %s; el usuario no se crea", body.username)
        raise HTTPException(502, CORREO_MSG) from None
    conn.commit()
    return user


@router.put("/{user_id}")
def editar(user_id: int, body: UsuarioEditado, me: dict = Depends(require_admin), conn=Depends(get_conn)):
    """Cambia el nombre, el email y el permiso de administrador.

    Raises:
        HTTPException: 404 si no existe; 409 si el nombre ya lo tiene otro usuario o si el
            administrador intenta quitarse su propio permiso.
    """
    if user_id == me["id"] and not body.es_admin:
        raise HTTPException(409, "No puedes quitarte a ti mismo el permiso de administrador")
    try:
        user = db.update_user(conn, user_id, body.username, body.email, body.es_admin)
    except db.NombreDuplicado:
        raise HTTPException(409, DUPLICADO_MSG) from None
    if user is None:
        raise HTTPException(404, NO_EXISTE_MSG)
    return user


@router.delete("/{user_id}", status_code=204)
def borrar(user_id: int, me: dict = Depends(require_admin), conn=Depends(get_conn)):
    """Borra un usuario (y sus asignaciones de roles).

    Raises:
        HTTPException: 404 si no existe; 409 si es el propio administrador.
    """
    if user_id == me["id"]:
        raise HTTPException(409, AUTOBORRADO_MSG)
    if db.delete_users(conn, [user_id]) == 0:
        raise HTTPException(404, NO_EXISTE_MSG)
    return Response(status_code=204)


@router.post("/borrar")
def borrar_lote(body: Lote, me: dict = Depends(require_admin), conn=Depends(get_conn)):
    """Borra varios usuarios a la vez. Los ids que ya no existen se ignoran.

    Returns:
        {"borrados": n} con cuántos se han borrado de verdad.

    Raises:
        HTTPException: 409 si la lista incluye al propio administrador (no se borra ninguno).
    """
    if me["id"] in body.ids:
        raise HTTPException(409, AUTOBORRADO_MSG)
    return {"borrados": db.delete_users(conn, sorted(set(body.ids)))}


@router.put("/{user_id}/roles/{rol_id}", status_code=204)
def asociar_rol(user_id: int, rol_id: int, conn=Depends(get_conn)):
    """Da un rol al usuario.

    Raises:
        HTTPException: 404 si el usuario o el rol no existen.
    """
    if not db.add_user_role(conn, user_id, rol_id):
        raise HTTPException(404, "El usuario o el rol no existe")
    return Response(status_code=204)


@router.delete("/{user_id}/roles/{rol_id}", status_code=204)
def quitar_rol(user_id: int, rol_id: int, conn=Depends(get_conn)):
    """Quita un rol al usuario."""
    db.remove_user_role(conn, user_id, rol_id)
    return Response(status_code=204)
