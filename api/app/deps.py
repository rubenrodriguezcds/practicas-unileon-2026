"""Dependencias de permisos: quién puede llamar a cada endpoint.

Para qué: `current_user` lee el usuario de la sesión y si es administrador (columna
usuarios.es_admin); `require_admin` exige además que lo sea. Un endpoint se protege con un
parámetro, p. ej. `me: dict = Depends(require_admin)`, o todo un router con
`dependencies=[Depends(require_admin)]`.

Por qué existe: las issues #5 y #6 piden que SOLO el administrador gestione roles y usuarios.
Esconder el menú en el frontend no basta: cualquiera puede llamar a la API a mano. La
comprobación tiene que estar en el servidor, en cada petición.

Por qué la sesión guarda el id y no el nombre: el administrador puede renombrar usuarios (#6), y
el id no cambia. Por qué se consulta la bbdd cada vez y no se guarda es_admin en la cookie: si se
le quita el permiso a alguien, deja de tenerlo en su siguiente petición, sin esperar a que cierre
sesión. Si el usuario de la sesión ya no existe, la sesión se borra y se responde 401.

Quién lo usa: routers/auth.py (/me), routers/roles.py y routers/usuarios.py.
"""

from fastapi import Depends, HTTPException, Request

from app import db
from app.db import get_conn


def current_user(request: Request, conn) -> dict:
    """Usuario de la sesión: {"id", "username", "es_admin"}.

    Raises:
        HTTPException: 401 si no hay sesión o si su usuario ya no existe (la sesión se borra).
    """
    user_id = request.session.get("user_id")
    if not isinstance(user_id, int):
        raise HTTPException(401, "No autenticado")
    user = db.get_session_user(conn, user_id)
    if user is None:
        request.session.clear()
        raise HTTPException(401, "No autenticado")
    return user


def require_admin(request: Request, conn=Depends(get_conn)) -> dict:
    """Dependencia: exige sesión de administrador. Devuelve el usuario de la sesión.

    Raises:
        HTTPException: 401 sin sesión; 403 si el usuario no es administrador.
    """
    user = current_user(request, conn)
    if not user["es_admin"]:
        raise HTTPException(403, "Solo el administrador puede hacer esto")
    return user
