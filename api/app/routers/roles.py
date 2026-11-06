"""Endpoints de gestión de roles: /api/roles (issue #5).

Para qué: es lo que llama la pantalla de roles del frontend para listar, crear, editar o
renombrar y borrar roles, y para ver qué usuarios tienen cada uno.

Por qué existe: la issue #5 pide un menú de gestión de roles SOLO para el administrador. Todos
los endpoints dependen de `require_admin` (app/deps.py): 401 sin sesión, 403 si no es admin.

Contrato (el frontend depende de él):
  GET    /api/roles                 → 200 [{"id","nombre","descripcion","num_usuarios"}] por nombre
  POST   /api/roles                 {"nombre","descripcion"} → 201 rol · 409 nombre repetido
  PUT    /api/roles/{id}            {"nombre","descripcion"} → 200 rol · 404 · 409 nombre repetido
  DELETE /api/roles/{id}            → 204 · 404 · 409 si algún usuario tiene el rol
  GET    /api/roles/{id}/usuarios   → 200 [{"id","username","email"}] por nombre · 404
  En todos: 401 sin sesión · 403 si no es administrador · 422 datos no válidos · 503 bbdd caída.

Decisiones:
  - El nombre se guarda sin espacios al principio ni al final y no puede quedar vacío; la
    descripción vacía se guarda como NULL (sin descripción).
  - Un rol que tienen usuarios no se borra (409, diciendo cuántos): borrarlo les quitaría el rol
    sin avisar. Primero hay que quitárselo a esos usuarios.

Quién lo usa: main.py lo registra; usa db.py (consultas) y deps.py (permisos).
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, StringConstraints, field_validator

from app import db
from app.db import get_conn
from app.deps import require_admin

# Todo el router exige administrador: no hay forma de añadir un endpoint aquí y olvidarse.
router = APIRouter(prefix="/api/roles", dependencies=[Depends(require_admin)])

DUPLICADO_MSG = "Ya existe un rol con ese nombre"
NO_EXISTE_MSG = "El rol no existe"


class RolIn(BaseModel):
    """Cuerpo de POST y PUT. 422 si el nombre está vacío o es demasiado largo."""

    nombre: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
    descripcion: Annotated[str | None, StringConstraints(strip_whitespace=True, max_length=500)] = None

    @field_validator("descripcion")
    @classmethod
    def vacia_es_none(cls, v):
        return v or None


@router.get("")
def listar(conn=Depends(get_conn)):
    """Todos los roles, con cuántos usuarios tiene cada uno."""
    return db.list_roles(conn)


@router.post("", status_code=201)
def crear(body: RolIn, conn=Depends(get_conn)):
    """Crea un rol.

    Raises:
        HTTPException: 409 si el nombre ya existe.
    """
    try:
        return db.create_role(conn, body.nombre, body.descripcion)
    except db.NombreDuplicado:
        raise HTTPException(409, DUPLICADO_MSG) from None


@router.put("/{rol_id}")
def editar(rol_id: int, body: RolIn, conn=Depends(get_conn)):
    """Cambia el nombre y la descripción de un rol.

    Raises:
        HTTPException: 404 si no existe; 409 si el nombre nuevo ya lo tiene otro rol.
    """
    try:
        rol = db.update_role(conn, rol_id, body.nombre, body.descripcion)
    except db.NombreDuplicado:
        raise HTTPException(409, DUPLICADO_MSG) from None
    if rol is None:
        raise HTTPException(404, NO_EXISTE_MSG)
    return rol


@router.delete("/{rol_id}", status_code=204)
def borrar(rol_id: int, conn=Depends(get_conn)):
    """Borra un rol que no tiene ningún usuario.

    Raises:
        HTTPException: 404 si no existe; 409 si algún usuario lo tiene.
    """
    n = db.delete_role(conn, rol_id)
    if n is None:
        raise HTTPException(404, NO_EXISTE_MSG)
    if n > 0:
        usuarios = "1 usuario" if n == 1 else f"{n} usuarios"
        raise HTTPException(409, f"No se puede borrar: el rol está asignado a {usuarios}")
    return Response(status_code=204)


@router.get("/{rol_id}/usuarios")
def usuarios(rol_id: int, conn=Depends(get_conn)):
    """Usuarios que tienen el rol.

    Raises:
        HTTPException: 404 si el rol no existe.
    """
    lista = db.role_users(conn, rol_id)
    if lista is None:
        raise HTTPException(404, NO_EXISTE_MSG)
    return lista
