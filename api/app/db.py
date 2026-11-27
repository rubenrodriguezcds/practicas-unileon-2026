"""Acceso a la base de datos PostgreSQL.

Para qué: abre una conexión por petición HTTP y contiene las consultas SQL de la app.

Por qué existe: es el ÚNICO sitio que habla SQL. Los endpoints no saben nada de psycopg ni de
tablas; solo piden datos con funciones como `find_user`. Si mañana se cambia a un ORM
(SQLAlchemy) o se añaden tablas, el cambio queda aquí.

Quién lo usa: routers/auth.py (a través de la dependencia de FastAPI `Depends(get_conn)`),
deps.py (permisos), captcha.py y migrations.py (que usa `connect` al arrancar).

Notas:
  - Si Postgres no responde, se devuelve 503 «Base de datos no disponible» (y se deja en el log)
    en vez de un 500 genérico, para que el usuario sepa que el problema no es su contraseña.
  - La conexión se cierra siempre al acabar la petición, también si hay errores.
  - Dentro de Docker se conecta a `db:5432` (red interna), no al 1521 publicado al host.
"""

import logging

import psycopg
from fastapi import HTTPException

from app.config import Settings, get_settings

logger = logging.getLogger(__name__)


def connect(s: Settings, **kwargs):
    """Abre una conexión con los datos de `s` (kwargs extra, p. ej. autocommit, van a psycopg)."""
    return psycopg.connect(
        host=s.db_host, port=s.db_port, dbname=s.postgres_db,
        user=s.postgres_user, password=s.postgres_password, connect_timeout=3, **kwargs,
    )


def get_conn():
    """Dependencia FastAPI: abre una conexión por petición y la cierra al terminar.

    Yields:
        La conexión psycopg abierta.

    Raises:
        HTTPException: 503 si no se puede conectar o si la bbdd cae durante
            la petición (sin filtrar detalles internos al cliente).
    """
    try:
        conn = connect(get_settings())
    except psycopg.OperationalError:
        logger.exception("No se pudo conectar a la base de datos")
        raise HTTPException(503, "Base de datos no disponible") from None
    try:
        yield conn
    except psycopg.OperationalError:  # la bbdd cae a mitad de petición
        logger.exception("Base de datos caída durante la petición")
        raise HTTPException(503, "Base de datos no disponible") from None
    finally:
        conn.close()


def find_user(conn, username: str) -> dict | None:
    """Datos del usuario para login y reseteo, o None si no existe.

    `reset_hash` solo se devuelve si la contraseña pendiente no ha caducado: así el login no
    tiene que comprobar fechas.
    """
    row = conn.execute(
        "SELECT password_hash, email, CASE WHEN reset_expira > now() THEN reset_hash END, es_admin, id"
        " FROM usuarios WHERE username = %s",
        (username,),
    ).fetchone()
    if row is None:
        return None
    return {"password_hash": row[0], "email": row[1], "reset_hash": row[2], "es_admin": row[3], "id": row[4]}


def get_session_user(conn, user_id: int) -> dict | None:
    """Nombre y permiso de administrador del usuario de la sesión; None si ya no existe.

    La sesión guarda el id (no cambia aunque se renombre al usuario). Se consulta en cada
    petición protegida, en vez de guardar es_admin en la cookie, para que quitar el permiso en la
    bbdd surta efecto al momento.
    """
    row = conn.execute("SELECT username, es_admin FROM usuarios WHERE id = %s", (user_id,)).fetchone()
    return {"id": user_id, "username": row[0], "es_admin": row[1]} if row else None


def save_pending_password(conn, username: str, hashed: str) -> None:
    """Guarda la contraseña del reseteo como pendiente durante 1 hora. NO hace commit.

    Sin commit a propósito: el reseteo solo confirma si el correo se ha enviado (si no, rollback).
    """
    conn.execute(
        "UPDATE usuarios SET reset_hash = %s, reset_expira = now() + interval '1 hour' WHERE username = %s",
        (hashed, username),
    )


def promote_pending_password(conn, username: str) -> None:
    """La contraseña pendiente pasa a ser la del usuario (se ha entrado con ella)."""
    conn.execute(
        "UPDATE usuarios SET password_hash = reset_hash, reset_hash = NULL, reset_expira = NULL"
        " WHERE username = %s AND reset_hash IS NOT NULL",
        (username,),
    )
    conn.commit()


def discard_pending_password(conn, username: str) -> None:
    """Descarta la contraseña pendiente (se ha entrado con la de siempre)."""
    conn.execute("UPDATE usuarios SET reset_hash = NULL, reset_expira = NULL WHERE username = %s", (username,))
    conn.commit()


def mark_captcha_used(conn, signature: str, expires_at: int) -> bool:
    """Apunta un reto de captcha como usado. Devuelve False si ya lo estaba (reenvío).

    De paso borra los retos caducados: ya no se pueden reutilizar porque la firma caduca sola.
    """
    conn.execute("DELETE FROM captchas_usados WHERE expira < now()")
    inserted = conn.execute(
        "INSERT INTO captchas_usados (firma, expira) VALUES (%s, to_timestamp(%s))"
        " ON CONFLICT (firma) DO NOTHING RETURNING firma",
        (signature, expires_at),
    ).fetchone()
    conn.commit()
    return inserted is not None


def count_reset_attempts(conn, keys: list[str]) -> int:
    """Máximo de intentos de reseteo en la última hora entre las claves dadas (usuario, IP)."""
    row = conn.execute(
        "SELECT coalesce(max(n), 0) FROM (SELECT count(*) AS n FROM intentos_reset"
        " WHERE clave = ANY(%s) AND creado_en > now() - interval '1 hour' GROUP BY clave) t",
        (keys,),
    ).fetchone()
    return row[0]


def add_reset_attempt(conn, keys: list[str]) -> None:
    """Apunta un intento de reseteo para cada clave y borra los de hace más de un día."""
    conn.execute("DELETE FROM intentos_reset WHERE creado_en < now() - interval '1 day'")
    for key in keys:
        conn.execute("INSERT INTO intentos_reset (clave) VALUES (%s)", (key,))
    conn.commit()


# --- Roles (issue #5) ---

class NombreDuplicado(Exception):
    """El nombre ya existe: roles.nombre y usuarios.username son únicos."""


def _rol(row) -> dict:
    return {"id": row[0], "nombre": row[1], "descripcion": row[2], "num_usuarios": row[3]}


def list_roles(conn) -> list[dict]:
    """Todos los roles por nombre, con cuántos usuarios tiene cada uno."""
    rows = conn.execute(
        "SELECT r.id, r.nombre, r.descripcion, count(ur.usuario_id) FROM roles r"
        " LEFT JOIN usuario_roles ur ON ur.rol_id = r.id GROUP BY r.id ORDER BY r.nombre"
    ).fetchall()
    return [_rol(r) for r in rows]


def create_role(conn, nombre: str, descripcion: str | None) -> dict:
    """Crea un rol y lo devuelve.

    Raises:
        NombreDuplicado: si ya existe uno con ese nombre.
    """
    try:
        row = conn.execute(
            "INSERT INTO roles (nombre, descripcion) VALUES (%s, %s) RETURNING id, nombre, descripcion, 0",
            (nombre, descripcion),
        ).fetchone()
    except psycopg.errors.UniqueViolation:
        conn.rollback()
        raise NombreDuplicado from None
    conn.commit()
    return _rol(row)


def update_role(conn, rol_id: int, nombre: str, descripcion: str | None) -> dict | None:
    """Renombra o edita un rol y lo devuelve; None si no existe.

    Raises:
        NombreDuplicado: si el nombre nuevo ya lo tiene otro rol.
    """
    try:
        row = conn.execute(
            "UPDATE roles SET nombre = %s, descripcion = %s WHERE id = %s RETURNING id, nombre, descripcion,"
            " (SELECT count(*) FROM usuario_roles WHERE rol_id = roles.id)",
            (nombre, descripcion, rol_id),
        ).fetchone()
    except psycopg.errors.UniqueViolation:
        conn.rollback()
        raise NombreDuplicado from None
    conn.commit()
    return _rol(row) if row else None


def delete_role(conn, rol_id: int) -> int | None:
    """Borra un rol si nadie lo tiene.

    Returns:
        None si el rol no existe; 0 si se ha borrado; N > 0 si lo tienen N usuarios y NO se borra
        (la bbdd también lo impediría: ON DELETE RESTRICT).
    """
    row = conn.execute(
        "SELECT (SELECT count(*) FROM usuario_roles WHERE rol_id = %s) FROM roles WHERE id = %s",
        (rol_id, rol_id),
    ).fetchone()
    if row is None:
        return None
    if row[0] == 0:
        conn.execute("DELETE FROM roles WHERE id = %s", (rol_id,))
        conn.commit()
    return row[0]


def role_users(conn, rol_id: int) -> list[dict] | None:
    """Usuarios que tienen el rol, por nombre; None si el rol no existe."""
    if conn.execute("SELECT 1 FROM roles WHERE id = %s", (rol_id,)).fetchone() is None:
        return None
    rows = conn.execute(
        "SELECT u.id, u.username, u.email FROM usuarios u JOIN usuario_roles ur ON ur.usuario_id = u.id"
        " WHERE ur.rol_id = %s ORDER BY u.username",
        (rol_id,),
    ).fetchall()
    return [{"id": r[0], "username": r[1], "email": r[2]} for r in rows]


# --- Usuarios (issue #6) ---

def _usuario(row) -> dict:
    return {"id": row[0], "username": row[1], "email": row[2], "es_admin": row[3]}


def list_users(conn) -> list[dict]:
    """Todos los usuarios por nombre, con cuántos roles tiene cada uno."""
    rows = conn.execute(
        "SELECT u.id, u.username, u.email, u.es_admin, count(ur.rol_id) FROM usuarios u"
        " LEFT JOIN usuario_roles ur ON ur.usuario_id = u.id GROUP BY u.id ORDER BY u.username"
    ).fetchall()
    return [{**_usuario(r), "num_roles": r[4]} for r in rows]


def get_user(conn, user_id: int) -> dict | None:
    """Detalle de un usuario con sus roles (por nombre); None si no existe."""
    row = conn.execute("SELECT id, username, email, es_admin FROM usuarios WHERE id = %s", (user_id,)).fetchone()
    if row is None:
        return None
    roles = conn.execute(
        "SELECT r.id, r.nombre, r.descripcion FROM roles r JOIN usuario_roles ur ON ur.rol_id = r.id"
        " WHERE ur.usuario_id = %s ORDER BY r.nombre",
        (user_id,),
    ).fetchall()
    return {**_usuario(row), "roles": [{"id": r[0], "nombre": r[1], "descripcion": r[2]} for r in roles]}


def create_user(conn, username: str, email: str, es_admin: bool, password_hash: str) -> dict:
    """Crea un usuario y lo devuelve. NO hace commit.

    Sin commit a propósito: el alta solo se confirma si sale el correo con la contraseña (si no,
    rollback y el usuario no queda creado sin que nadie conozca su contraseña).

    Raises:
        NombreDuplicado: si ya existe un usuario con ese nombre.
    """
    try:
        row = conn.execute(
            "INSERT INTO usuarios (username, email, es_admin, password_hash) VALUES (%s, %s, %s, %s)"
            " RETURNING id, username, email, es_admin",
            (username, email, es_admin, password_hash),
        ).fetchone()
    except psycopg.errors.UniqueViolation:
        conn.rollback()
        raise NombreDuplicado from None
    return {**_usuario(row), "num_roles": 0}


def update_user(conn, user_id: int, username: str, email: str | None, es_admin: bool) -> dict | None:
    """Renombra o edita un usuario y lo devuelve; None si no existe.

    Raises:
        NombreDuplicado: si el nombre nuevo ya lo tiene otro usuario.
    """
    try:
        row = conn.execute(
            "UPDATE usuarios SET username = %s, email = %s, es_admin = %s WHERE id = %s"
            " RETURNING id, username, email, es_admin",
            (username, email, es_admin, user_id),
        ).fetchone()
    except psycopg.errors.UniqueViolation:
        conn.rollback()
        raise NombreDuplicado from None
    conn.commit()
    return _usuario(row) if row else None


def delete_users(conn, user_ids: list[int]) -> int:
    """Borra los usuarios dados (sus roles se van con ellos: ON DELETE CASCADE). Devuelve cuántos."""
    n = conn.execute("DELETE FROM usuarios WHERE id = ANY(%s)", (user_ids,)).rowcount
    conn.commit()
    return n


def add_user_role(conn, user_id: int, rol_id: int) -> bool:
    """Asocia un rol a un usuario (si ya lo tenía, no cambia nada). False si el usuario o el rol no existen."""
    try:
        conn.execute(
            "INSERT INTO usuario_roles (usuario_id, rol_id) VALUES (%s, %s) ON CONFLICT DO NOTHING",
            (user_id, rol_id),
        )
    except psycopg.errors.ForeignKeyViolation:
        conn.rollback()
        return False
    conn.commit()
    return True


def remove_user_role(conn, user_id: int, rol_id: int) -> None:
    """Quita un rol a un usuario (si no lo tenía, no cambia nada)."""
    conn.execute("DELETE FROM usuario_roles WHERE usuario_id = %s AND rol_id = %s", (user_id, rol_id))
    conn.commit()


# --- Proyectos (issue #7) ---
# NombreDuplicado (arriba) sirve también aquí: proyectos y documentos tienen índices únicos sobre
# lower(nombre), así que «Web» y «web» chocan y la bbdd lo garantiza sin carreras.

def _proyecto(row) -> dict:
    return {"id": row[0], "nombre": row[1], "tipo": row[2], "descripcion": row[3], "num_documentos": row[4]}


def list_projects(conn) -> list[dict]:
    """Todos los proyectos por nombre (sin distinguir mayúsculas), con cuántos documentos tiene cada uno."""
    rows = conn.execute(
        "SELECT p.id, p.nombre, p.tipo, p.descripcion, count(d.id) FROM proyectos p"
        " LEFT JOIN documentos d ON d.proyecto_id = p.id GROUP BY p.id ORDER BY lower(p.nombre)"
    ).fetchall()
    return [_proyecto(r) for r in rows]


def create_project(conn, nombre: str, tipo: str | None, descripcion: str | None) -> dict:
    """Crea un proyecto y lo devuelve.

    Raises:
        NombreDuplicado: si ya existe uno con ese nombre (sin distinguir mayúsculas).
    """
    try:
        row = conn.execute(
            "INSERT INTO proyectos (nombre, tipo, descripcion) VALUES (%s, %s, %s)"
            " RETURNING id, nombre, tipo, descripcion, 0",
            (nombre, tipo, descripcion),
        ).fetchone()
    except psycopg.errors.UniqueViolation:
        conn.rollback()
        raise NombreDuplicado from None
    conn.commit()
    return _proyecto(row)


def get_project(conn, proyecto_id: int) -> dict | None:
    """Proyecto con la lista de sus documentos (id, nombre, tamaño, estado de indexado); None si no existe.

    No carga el contenido de los documentos: el tamaño sale de octet_length en la propia bbdd.
    Un documento sin fila en `indexado` está pendiente (el indexador aún no lo ha cogido).
    """
    row = conn.execute(
        "SELECT id, nombre, tipo, descripcion FROM proyectos WHERE id = %s", (proyecto_id,)
    ).fetchone()
    if row is None:
        return None
    docs = conn.execute(
        "SELECT d.id, d.nombre, octet_length(d.contenido), coalesce(i.estado, 'pendiente'), i.error,"
        " (SELECT count(*) FROM fragmentos f WHERE f.documento_id = d.id)"
        " FROM documentos d LEFT JOIN indexado i ON i.documento_id = d.id"
        " WHERE d.proyecto_id = %s ORDER BY lower(d.nombre)",
        (proyecto_id,),
    ).fetchall()
    return {"id": row[0], "nombre": row[1], "tipo": row[2], "descripcion": row[3],
            "documentos": [{"id": d[0], "nombre": d[1], "tamano": d[2],
                            "indexado": {"estado": d[3], "error": d[4], "fragmentos": d[5]}} for d in docs]}


def update_project(conn, proyecto_id: int, nombre: str, tipo: str | None, descripcion: str | None) -> dict | None:
    """Cambia nombre, tipo y descripción de un proyecto y lo devuelve; None si no existe.

    Raises:
        NombreDuplicado: si el nombre nuevo ya lo tiene otro proyecto (sin distinguir mayúsculas).
    """
    try:
        row = conn.execute(
            "UPDATE proyectos SET nombre = %s, tipo = %s, descripcion = %s WHERE id = %s"
            " RETURNING id, nombre, tipo, descripcion,"
            " (SELECT count(*) FROM documentos WHERE proyecto_id = proyectos.id)",
            (nombre, tipo, descripcion, proyecto_id),
        ).fetchone()
    except psycopg.errors.UniqueViolation:
        conn.rollback()
        raise NombreDuplicado from None
    conn.commit()
    return _proyecto(row) if row else None


def delete_project(conn, proyecto_id: int) -> bool:
    """Borra un proyecto y, por ON DELETE CASCADE, todos sus documentos. False si no existía."""
    borrado = conn.execute("DELETE FROM proyectos WHERE id = %s RETURNING id", (proyecto_id,)).fetchone()
    conn.commit()
    return borrado is not None


def add_document(conn, proyecto_id: int, nombre: str, contenido: bytes) -> dict | None:
    """Guarda un documento en un proyecto y lo devuelve (sin el contenido); None si el proyecto no existe.

    Raises:
        NombreDuplicado: si el proyecto ya tiene un documento con ese nombre (sin distinguir
            mayúsculas; la extensión forma parte del nombre).
    """
    try:
        # %b: el contenido viaja en binario; en texto psycopg lo pasaría a hexadecimal (el doble de bytes).
        row = conn.execute(
            "INSERT INTO documentos (proyecto_id, nombre, contenido)"
            " SELECT id, %s, %b FROM proyectos WHERE id = %s RETURNING id, nombre, octet_length(contenido)",
            (nombre, contenido, proyecto_id),
        ).fetchone()
    except psycopg.errors.UniqueViolation:
        conn.rollback()
        raise NombreDuplicado from None
    conn.commit()
    return {"id": row[0], "nombre": row[1], "tamano": row[2]} if row else None


def get_document(conn, documento_id: int) -> dict | None:
    """Nombre y contenido de un documento; None si no existe."""
    # binary=True: sin él, Postgres manda el contenido en hexadecimal (el doble de bytes que decodificar).
    row = conn.execute("SELECT nombre, contenido FROM documentos WHERE id = %s", (documento_id,), binary=True).fetchone()
    return {"nombre": row[0], "contenido": bytes(row[1])} if row else None


def delete_document(conn, documento_id: int) -> bool:
    """Borra un documento. False si no existía."""
    borrado = conn.execute("DELETE FROM documentos WHERE id = %s RETURNING id", (documento_id,)).fetchone()
    conn.commit()
    return borrado is not None


# --- Búsqueda del asistente (fase 1: buscador de prueba) ---

# Búsqueda híbrida: dos rankings de 30 candidatos cada uno, combinados con RRF (Reciprocal Rank
# Fusion): puntuación = 1/(60 + puesto en significado) + 1/(60 + puesto en palabras).
#   - Significado: distancia coseno entre la pregunta y `embedding` (índice HNSW). La subconsulta
#     ordena y corta ANTES de numerar, para que Postgres pueda usar el índice.
#   - Palabras: `busqueda @@ q`, ordenado por ts_rank. Encuentra nombres propios, cifras y códigos
#     que el vector puede no distinguir. `q` es `websearch_to_tsquery('spanish', unaccent(pregunta))`
#     con sus «y» (&) cambiados por «o» (|): websearch exige TODAS las palabras, y en una pregunta
#     («¿cuánto cuesta la migración?») casi nunca están todas en el trozo («cuánto»), así que la
#     parte de palabras no encontraba nada. Con «o» basta una, y ts_rank ya puntúa más a los trozos
#     que tienen más palabras de la pregunta. Las frases entre comillas (<->) se respetan.
# Un trozo que sale en los dos rankings suma las dos partes y sube. RRF solo usa los puestos, así
# que no hace falta poner en la misma escala el coseno y el ts_rank (que no se parecen en nada).
_BUSCAR = """
WITH sig AS (
  SELECT id, 1 - dist AS sim, row_number() OVER (ORDER BY dist) AS puesto
  FROM (SELECT id, embedding <=> %(vec)s::halfvec AS dist FROM fragmentos
        WHERE %(pid)s::int IS NULL OR proyecto_id = %(pid)s
        ORDER BY dist LIMIT 30) s
), pal AS (
  SELECT id, rango, row_number() OVER (ORDER BY rango DESC) AS puesto
  FROM (SELECT f.id, ts_rank(f.busqueda, b.q) AS rango
        FROM fragmentos f,
             (SELECT replace(websearch_to_tsquery('spanish', unaccent(%(texto)s))::text, '&', '|')::tsquery AS q) b
        WHERE f.busqueda @@ b.q AND (%(pid)s::int IS NULL OR f.proyecto_id = %(pid)s)
        ORDER BY rango DESC LIMIT 30) p
)
SELECT f.documento_id, d.nombre, f.proyecto_id, pr.nombre, f.titulos, f.paginas, f.texto, f.id,
       sig.sim, pal.rango,
       coalesce(1.0 / (60 + sig.puesto), 0) + coalesce(1.0 / (60 + pal.puesto), 0) AS puntuacion
FROM (SELECT id FROM sig UNION SELECT id FROM pal) ids
JOIN fragmentos f ON f.id = ids.id
JOIN documentos d ON d.id = f.documento_id
JOIN proyectos pr ON pr.id = f.proyecto_id
LEFT JOIN sig ON sig.id = f.id
LEFT JOIN pal ON pal.id = f.id
ORDER BY puntuacion DESC, sig.sim DESC NULLS LAST
LIMIT %(k)s
"""


def search_fragments(conn, vector: list[float], texto: str, proyecto_id: int | None, k: int = 10) -> list[dict]:
    """Los `k` trozos más parecidos a la pregunta (vector + texto), de todos los proyectos o de uno.

    `fragmento_id` es el id del trozo.
    `puntuacion_vector` es el coseno (1 = idéntico) y `puntuacion_texto` el ts_rank; None si el
    trozo no salió en ese ranking. `puntuacion` es la combinada (RRF), por la que se ordena.
    """
    filas = conn.execute(_BUSCAR, {"vec": "[" + ",".join(str(x) for x in vector) + "]",
                                   "texto": texto, "pid": proyecto_id, "k": k}).fetchall()
    return [{"documento_id": r[0], "documento": r[1], "proyecto_id": r[2], "proyecto": r[3],
             "titulos": r[4], "paginas": r[5], "texto": r[6], "fragmento_id": r[7],
             "puntuacion_vector": _redondear(r[8]), "puntuacion_texto": _redondear(r[9]),
             "puntuacion": _redondear(r[10])} for r in filas]


def _redondear(x) -> float | None:
    return None if x is None else round(float(x), 4)


# --- Validaciones de contenido por proyecto ---

_VALIDACION = "v.id, v.proyecto_id, v.nombre, v.tipo, v.criterio, v.orden"
# Las pruebas van en una lista JSON (en su orden) para traer cada validación en una sola fila.
_RESULTADO = (
    "r.estado, r.explicacion, r.resumen, r.ejecutada, r.validacion_id,"
    " (SELECT coalesce(json_agg(json_build_object('documento_id', f.documento_id, 'documento', d.nombre,"
    "  'paginas', f.paginas, 'texto', f.texto) ORDER BY p.orden), '[]')"
    "  FROM validacion_pruebas p JOIN fragmentos f ON f.id = p.fragmento_id"
    "  JOIN documentos d ON d.id = f.documento_id WHERE p.validacion_id = v.id)"
)


def _validacion(row) -> dict:
    """Fila de `_VALIDACION` + `_RESULTADO` → validación con su último resultado (o None)."""
    v = {"id": row[0], "proyecto_id": row[1], "nombre": row[2], "tipo": row[3], "criterio": row[4],
         "orden": row[5], "resultado": None}
    if len(row) > 6 and row[10] is not None:  # hay fila en validacion_resultados
        v["resultado"] = {"estado": row[6], "explicacion": row[7], "resumen": row[8],
                          "ejecutada": row[9].isoformat(), "pruebas": row[11]}
    return v


def patron_valido(conn, patron: str) -> str | None:
    """None si Postgres acepta el patrón como expresión regular; si no, su mensaje de error.

    Lo comprueba la propia Postgres porque es quien lo ejecuta y su sintaxis no es la de Python
    (p. ej. `\\m` y `\\M` son inicio y fin de palabra).
    """
    try:
        conn.execute("SELECT '' ~* unaccent(%s)", (patron,))
    except psycopg.errors.InvalidRegularExpression as e:
        conn.rollback()
        return str(e.diag.message_primary or e)
    return None


def list_validations(conn, proyecto_id: int) -> list[dict] | None:
    """Validaciones del proyecto en orden, con su último resultado y su prueba; None si el proyecto no existe."""
    if conn.execute("SELECT 1 FROM proyectos WHERE id = %s", (proyecto_id,)).fetchone() is None:
        return None
    rows = conn.execute(
        f"SELECT {_VALIDACION}, {_RESULTADO} FROM validaciones v"
        " LEFT JOIN validacion_resultados r ON r.validacion_id = v.id"
        " WHERE v.proyecto_id = %s ORDER BY v.orden, v.id",
        (proyecto_id,),
    ).fetchall()
    return [_validacion(r) for r in rows]


def create_validation(conn, proyecto_id: int, nombre: str, tipo: str, criterio: str) -> dict | None:
    """Añade una validación al final del proyecto; None si el proyecto no existe."""
    try:
        row = conn.execute(
            "INSERT INTO validaciones (proyecto_id, nombre, tipo, criterio, orden)"
            " SELECT %s, %s, %s, %s, coalesce(max(orden), 0) + 1 FROM validaciones WHERE proyecto_id = %s"
            f" RETURNING {_VALIDACION.replace('v.', '')}",
            (proyecto_id, nombre, tipo, criterio, proyecto_id),
        ).fetchone()
    except psycopg.errors.ForeignKeyViolation:
        conn.rollback()
        return None
    conn.commit()
    return _validacion(row)


def update_validation(conn, validacion_id: int, nombre: str, tipo: str, criterio: str) -> dict | None:
    """Cambia una validación y borra su resultado (ya no corresponde); None si no existe."""
    row = conn.execute(
        "UPDATE validaciones SET nombre = %s, tipo = %s, criterio = %s WHERE id = %s"
        f" RETURNING {_VALIDACION.replace('v.', '')}",
        (nombre, tipo, criterio, validacion_id),
    ).fetchone()
    if row is not None:
        conn.execute("DELETE FROM validacion_resultados WHERE validacion_id = %s", (validacion_id,))
    conn.commit()
    return _validacion(row) if row else None


def delete_validation(conn, validacion_id: int) -> bool:
    """Borra una validación (y su resultado, en cascada). False si no existía."""
    borrada = conn.execute("DELETE FROM validaciones WHERE id = %s RETURNING id", (validacion_id,)).fetchone()
    conn.commit()
    return borrada is not None


class PatronNoValido(Exception):
    """Postgres no acepta la expresión regular (el mensaje es el suyo)."""


def get_validation(conn, validacion_id: int) -> dict | None:
    """Una validación con su último resultado y su prueba; None si no existe."""
    row = conn.execute(
        f"SELECT {_VALIDACION}, {_RESULTADO} FROM validaciones v"
        " LEFT JOIN validacion_resultados r ON r.validacion_id = v.id"
        " WHERE v.id = %s",
        (validacion_id,),
    ).fetchone()
    return _validacion(row) if row else None


def run_pattern(conn, proyecto_id: int, patron: str) -> dict:
    """Busca el patrón en los trozos del proyecto, sin distinguir mayúsculas ni acentos.

    `unaccent` en los dos lados: «migracion» encuentra «MIGRACIÓN», como en el buscador. Solo
    quita tildes y diéresis de las letras, así que no cambia el resto de la expresión regular.

    Devuelve {"trozos", "documentos"} que coinciden, "fragmentos": el primer trozo de cada documento
    donde aparece (las pruebas, en orden de documento), y cuántos documentos del proyecto están
    "indexados" y cuántos "pendientes" (aún sin trozos: pendientes, indexándose o con error).

    Raises:
        PatronNoValido: si Postgres no acepta el patrón.
    """
    try:
        filas = conn.execute(
            "SELECT DISTINCT ON (documento_id) id, count(*) OVER (PARTITION BY documento_id)"
            " FROM fragmentos WHERE proyecto_id = %s AND unaccent(texto) ~* unaccent(%s)"
            " ORDER BY documento_id, orden",
            (proyecto_id, patron),
        ).fetchall()
    except psycopg.errors.InvalidRegularExpression as e:
        conn.rollback()
        raise PatronNoValido(str(e.diag.message_primary or e)) from None
    return {"trozos": sum(f[1] for f in filas), "documentos": len(filas), "fragmentos": [f[0] for f in filas],
            **document_counts(conn, proyecto_id)}


def document_counts(conn, proyecto_id: int) -> dict:
    """Documentos del proyecto ya «indexados» y «pendientes» (aún sin trozos: pendientes, indexándose o con error)."""
    indexados, pendientes = conn.execute(
        "SELECT count(*) FILTER (WHERE i.estado = 'hecho'), count(*) FILTER (WHERE i.estado IS DISTINCT FROM 'hecho')"
        " FROM documentos d LEFT JOIN indexado i ON i.documento_id = d.id WHERE d.proyecto_id = %s",
        (proyecto_id,),
    ).fetchone()
    return {"indexados": indexados, "pendientes": pendientes}


def save_result(conn, validacion_id: int, estado: str, explicacion: str, fragmentos: list[int],
                resumen: str | None = None) -> None:
    """Guarda el resultado de una validación con sus pruebas (en orden), sustituyendo al anterior."""
    conn.execute(
        "INSERT INTO validacion_resultados (validacion_id, estado, explicacion, resumen) VALUES (%s, %s, %s, %s)"
        " ON CONFLICT (validacion_id) DO UPDATE SET estado = EXCLUDED.estado, explicacion = EXCLUDED.explicacion,"
        " resumen = EXCLUDED.resumen, ejecutada = now()",
        (validacion_id, estado, explicacion, resumen),
    )
    conn.execute("DELETE FROM validacion_pruebas WHERE validacion_id = %s", (validacion_id,))
    with conn.cursor() as cur:
        cur.executemany("INSERT INTO validacion_pruebas (validacion_id, fragmento_id, orden) VALUES (%s, %s, %s)",
                        [(validacion_id, f, i) for i, f in enumerate(fragmentos)])
    conn.commit()


def get_fragments(conn, ids: list[int]) -> list[dict]:
    """Trozos por id, en el orden pedido: {"documento", "paginas", "texto"} (los que ya no existan se saltan)."""
    if not ids:
        return []
    filas = conn.execute(
        "SELECT f.id, d.nombre, f.paginas, f.texto FROM fragmentos f JOIN documentos d ON d.id = f.documento_id"
        " WHERE f.id = ANY(%s)",
        (ids,),
    ).fetchall()
    por_id = {r[0]: {"documento": r[1], "paginas": r[2], "texto": r[3]} for r in filas}
    return [por_id[i] for i in ids if i in por_id]
