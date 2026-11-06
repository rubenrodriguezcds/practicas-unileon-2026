"""Dependencias de permisos: quién puede llamar a cada endpoint.

Para qué: `current_user` lee el usuario de la sesión y si es administrador (columna
usuarios.es_admin); `require_admin` exige además que lo sea. Un endpoint se protege con un
parámetro, p. ej. `username: str = Depends(require_admin)`.

Por qué existe: la issue #5 pide que SOLO el administrador gestione roles. Esconder el menú en
el frontend no basta: cualquiera puede llamar a la API a mano. La comprobación tiene que estar en
el servidor, en cada petición.

Por qué se consulta la bbdd cada vez y no se guarda es_admin en la cookie: si se le quita el
permiso a alguien, deja de tenerlo en su siguiente petición, sin esperar a que cierre sesión.
Si el usuario de la sesión ya no existe, la sesión se borra y se responde 401.

Quién lo usa: routers/auth.py (/me) y routers/roles.py.
"""

from fastapi import Depends, HTTPException, Request

from app import db
from app.db import get_conn


def current_user(request: Request, conn) -> tuple[str, bool]:
    """Usuario de la sesión y si es admin.

    Raises:
        HTTPException: 401 si no hay sesión o si su usuario ya no existe (la sesión se borra).
    """
    username = request.session.get("username")
    if not username:
        raise HTTPException(401, "No autenticado")
    es_admin = db.get_es_admin(conn, username)
    if es_admin is None:
        request.session.clear()
        raise HTTPException(401, "No autenticado")
    return username, es_admin


def require_admin(request: Request, conn=Depends(get_conn)) -> str:
    """Dependencia: exige sesión de administrador. Devuelve el nombre de usuario.

    Raises:
        HTTPException: 401 sin sesión; 403 si el usuario no es administrador.
    """
    username, es_admin = current_user(request, conn)
    if not es_admin:
        raise HTTPException(403, "Solo el administrador puede hacer esto")
    return username
