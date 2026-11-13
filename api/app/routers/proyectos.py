"""Endpoints de gestión de proyectos y sus documentos adjuntos: /api/proyectos y /api/documentos (issue #7).

Para qué: es lo que llaman las pantallas de proyectos del frontend para crear, listar, editar y
borrar proyectos, y para subir, ver, descargar y borrar sus documentos.

Por qué existe: la issue #7 pide un menú de gestión de proyectos. De momento solo lo usa el
administrador (como roles): los dos routers dependen de `require_admin` (app/deps.py; el de
documentos a través de `admin_o_login`, que solo cambia la respuesta sin sesión), así que no hay
forma de añadir un endpoint aquí y olvidarse de protegerlo. Abrirlo a más usuarios es cambiar esa
dependencia.

Contrato (el frontend depende de él):
  GET    /api/proyectos            → 200 [{"id","nombre","tipo","descripcion","num_documentos"}] por nombre
  POST   /api/proyectos            {"nombre","tipo","descripcion"} → 201 proyecto · 409 nombre repetido
  GET    /api/proyectos/{id}       → 200 proyecto + "documentos": [{"id","nombre","tamano","visible"}] · 404
  PUT    /api/proyectos/{id}       {"nombre","tipo","descripcion"} → 200 proyecto · 404 · 409 nombre repetido
  DELETE /api/proyectos/{id}       → 204 (borra también sus documentos) · 404
  POST   /api/proyectos/{id}/documentos  multipart, campo "archivo" → 201 {"id","nombre","tamano"}
                                   · 404 · 409 nombre repetido · 411/413 tamaño · 415 tipo · 422 vacío
  GET    /api/documentos/{id}      → 200 el archivo (descarga; con ?ver=1 se abre en el navegador si es
                                     de un tipo que se puede ver) · 404 · 303 al login si es un enlace
                                     del navegador sin sesión
  DELETE /api/documentos/{id}      → 204 · 404
  En todos: 401 sin sesión · 403 si no es administrador · 422 datos no válidos · 503 bbdd caída.

Decisiones:
  - Nombre de proyecto único sin distinguir mayúsculas («Web» = «web»), aunque la issue no lo pide:
    dos proyectos que se llaman igual confunden.
  - Editar un proyecto es cambiar su nombre, tipo o descripción, y añadir o borrar documentos. Un
    documento no se edita: se borra y se sube otro.
  - `visible` (si el navegador puede mostrar el documento) lo decide la API con app/documentos.py,
    para no repetir la lista de tipos en el frontend.

Quién lo usa: main.py lo registra; usa db.py (consultas), deps.py (permisos) y documentos.py (tipos).
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, StringConstraints, field_validator
from starlette.concurrency import run_in_threadpool
from starlette.datastructures import UploadFile

from app import db
from app.db import get_conn
from app.deps import require_admin
from app.documentos import charset_texto, content_disposition, limpiar_nombre, tipo_de


def admin_o_login(request: Request, conn=Depends(get_conn)) -> dict:
    """`require_admin`, pero un enlace del navegador sin sesión va al login en vez de a un JSON de error.

    «Ver» y «Descargar» son enlaces normales: con la sesión caducada, el navegador enseñaría (o
    bajaría como si fuera el documento) el JSON del 401. Solo en GET y solo si el navegador pide
    HTML (es una navegación): un DELETE o una llamada desde código siguen recibiendo el 401.
    """
    try:
        return require_admin(request, conn)
    except HTTPException as e:
        if e.status_code == 401 and request.method == "GET" and "text/html" in request.headers.get("accept", ""):
            raise HTTPException(303, headers={"Location": "/login"}) from None
        raise


router = APIRouter(prefix="/api/proyectos", dependencies=[Depends(require_admin)])
documentos_router = APIRouter(prefix="/api/documentos", dependencies=[Depends(admin_o_login)])

DUPLICADO_MSG = "Ya existe un proyecto con ese nombre"
NO_EXISTE_MSG = "El proyecto no existe"
DOC_DUPLICADO_MSG = "Ya existe un documento con ese nombre en el proyecto"
DOC_NO_EXISTE_MSG = "El documento no existe"
TIPO_MSG = "Tipo de archivo no permitido"
VACIO_MSG = "El archivo está vacío"

# Cabeceras de toda descarga: el navegador no adivina el tipo (nosniff) ni la guarda en caché.
SEGURIDAD = {"X-Content-Type-Options": "nosniff", "Cache-Control": "private, no-store"}
# Además, todo lo que no es PDF se abre como página aislada sin scripts (sandbox), para que un
# documento nunca ejecute código con la sesión del administrador. El PDF va sin sandbox porque el
# visor de Chrome se queda en blanco con ella, y un PDF no ejecuta JavaScript de página.
SIN_SANDBOX = {"application/pdf"}


def tamano_msg(max_mb: int) -> str:
    """Mensaje del 413; lo usa también el límite previo de main.py."""
    return f"El archivo pasa de {max_mb} MB"


class ProyectoIn(BaseModel):
    """Cuerpo de POST. 422 si el nombre está vacío o algún campo es demasiado largo."""

    nombre: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
    tipo: Annotated[str | None, StringConstraints(strip_whitespace=True, max_length=100)] = None
    descripcion: Annotated[str | None, StringConstraints(strip_whitespace=True, max_length=1000)] = None

    @field_validator("tipo", "descripcion")
    @classmethod
    def vacio_es_none(cls, v):
        return v or None


@router.get("")
def listar(conn=Depends(get_conn)):
    """Todos los proyectos, con cuántos documentos tiene cada uno."""
    return db.list_projects(conn)


@router.post("", status_code=201)
def crear(body: ProyectoIn, conn=Depends(get_conn)):
    """Crea un proyecto.

    Raises:
        HTTPException: 409 si el nombre ya existe (sin distinguir mayúsculas).
    """
    try:
        return db.create_project(conn, body.nombre, body.tipo, body.descripcion)
    except db.NombreDuplicado:
        raise HTTPException(409, DUPLICADO_MSG) from None


@router.get("/{proyecto_id}")
def detalle(proyecto_id: int, conn=Depends(get_conn)):
    """Proyecto con sus documentos; cada documento dice si se puede ver en el navegador.

    Raises:
        HTTPException: 404 si no existe.
    """
    proyecto = db.get_project(conn, proyecto_id)
    if proyecto is None:
        raise HTTPException(404, NO_EXISTE_MSG)
    for doc in proyecto["documentos"]:
        tipo = tipo_de(doc["nombre"])
        doc["visible"] = bool(tipo and tipo.visible)
    return proyecto


@router.put("/{proyecto_id}")
def editar(proyecto_id: int, body: ProyectoIn, conn=Depends(get_conn)):
    """Cambia el nombre, el tipo y la descripción de un proyecto (sus documentos no se tocan).

    Raises:
        HTTPException: 404 si no existe; 409 si el nombre nuevo ya lo tiene otro proyecto.
    """
    try:
        proyecto = db.update_project(conn, proyecto_id, body.nombre, body.tipo, body.descripcion)
    except db.NombreDuplicado:
        raise HTTPException(409, DUPLICADO_MSG) from None
    if proyecto is None:
        raise HTTPException(404, NO_EXISTE_MSG)
    return proyecto


@router.delete("/{proyecto_id}", status_code=204)
def borrar(proyecto_id: int, conn=Depends(get_conn)):
    """Borra un proyecto y todos sus documentos (la bbdd los borra en cascada).

    Raises:
        HTTPException: 404 si no existe.
    """
    if not db.delete_project(conn, proyecto_id):
        raise HTTPException(404, NO_EXISTE_MSG)
    return Response(status_code=204)


@router.post("/{proyecto_id}/documentos", status_code=201)
async def subir(proyecto_id: int, request: Request, conn=Depends(get_conn)):
    """Añade un documento a un proyecto (multipart, campo «archivo»).

    El multipart se lee aquí dentro y no como parámetro `UploadFile`: FastAPI lee los parámetros
    del cuerpo ANTES de las dependencias, así que un anónimo haría procesar el archivo antes de
    recibir el 401. Dentro de la función, `require_admin` ya ha pasado.

    Orden de las comprobaciones: nombre → tipo → tamaño → bbdd, de lo más barato a lo más caro.
    main.py ya ha cortado antes las peticiones que anuncian más tamaño del permitido; aquí se mira
    el tamaño real.

    Raises:
        HTTPException: 422 sin archivo, nombre o archivo vacío; 415 tipo no permitido; 413
            demasiado grande; 404 el proyecto no existe; 409 ya hay un documento con ese nombre.
    """
    async with request.form(max_files=1, max_fields=1) as form:
        archivo = form.get("archivo")
        if not isinstance(archivo, UploadFile):
            raise HTTPException(422, "Falta el archivo")
        return await _guardar(proyecto_id, archivo, request, conn)


async def _guardar(proyecto_id: int, archivo: UploadFile, request: Request, conn) -> dict:
    """Comprueba y guarda el archivo recibido (ver `subir`)."""
    try:
        nombre = limpiar_nombre(archivo.filename or "")
    except ValueError:
        raise HTTPException(422, "El nombre del archivo no es válido") from None
    if tipo_de(nombre) is None:
        raise HTTPException(415, TIPO_MSG)
    max_mb = request.app.state.settings.documento_max_mb
    contenido = await archivo.read(max_mb * 1024 * 1024 + 1)  # un byte de más basta para saber si se pasa
    if len(contenido) > max_mb * 1024 * 1024:
        raise HTTPException(413, tamano_msg(max_mb))
    if not contenido:
        raise HTTPException(422, VACIO_MSG)
    try:
        # psycopg es síncrono y `subir` es async: en un hilo aparte, para que guardar 50 MB no deje
        # al resto de peticiones esperando.
        doc = await run_in_threadpool(db.add_document, conn, proyecto_id, nombre, contenido)
    except db.NombreDuplicado:
        raise HTTPException(409, DOC_DUPLICADO_MSG) from None
    if doc is None:
        raise HTTPException(404, NO_EXISTE_MSG)
    return doc


@documentos_router.get("/{documento_id}")
def descargar(documento_id: int, ver: bool = False, conn=Depends(get_conn)):
    """Devuelve el documento: como descarga, o abierto en el navegador si `ver` y su tipo se puede ver.

    Raises:
        HTTPException: 404 si no existe.
    """
    # shortcut: carga el documento entero en memoria (≤ DOCUMENTO_MAX_MB); pasar a streaming si sube el límite
    doc = db.get_document(conn, documento_id)
    if doc is None:
        raise HTTPException(404, DOC_NO_EXISTE_MSG)
    tipo = tipo_de(doc["nombre"])
    # Un documento guardado antes de cambiar la lista de tipos se sirve como binario genérico.
    content_type = tipo.content_type if tipo else "application/octet-stream"
    if content_type.startswith("text/plain"):
        content_type = f"text/plain; charset={charset_texto(doc['contenido'])}"
    inline = ver and bool(tipo and tipo.visible)
    headers = {**SEGURIDAD, "Content-Disposition": content_disposition(doc["nombre"], inline)}
    if content_type not in SIN_SANDBOX:
        headers["Content-Security-Policy"] = "sandbox"
    return Response(doc["contenido"], media_type=content_type, headers=headers)


@documentos_router.delete("/{documento_id}", status_code=204)
def borrar_documento(documento_id: int, conn=Depends(get_conn)):
    """Borra un documento.

    Raises:
        HTTPException: 404 si no existe.
    """
    if not db.delete_document(conn, documento_id):
        raise HTTPException(404, DOC_NO_EXISTE_MSG)
    return Response(status_code=204)
