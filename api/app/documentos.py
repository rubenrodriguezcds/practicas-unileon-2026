"""Reglas de los documentos adjuntos: tipos admitidos, nombre de archivo y cabecera de descarga.

Para qué: decide qué archivos se pueden subir (por extensión), con qué `Content-Type` se
sirven y si el navegador puede mostrarlos en la propia página; limpia el nombre que envía el
cliente y construye la cabecera `Content-Disposition` de la descarga.

Por qué existe: es el ÚNICO sitio con esas reglas, para que subida y descarga no discrepen.
La lista es cerrada a propósito: `.html` y `.svg` quedan fuera porque servidos desde nuestro
dominio podrían ejecutar scripts (XSS), y el `Content-Type` lo fijamos nosotros por extensión
en vez de fiarnos del que declara el cliente.

Quién lo usa: routers/proyectos.py (endpoints de subida y descarga de documentos).
"""

import unicodedata
from dataclasses import dataclass
from urllib.parse import quote

NOMBRE_MAX = 255  # longitud máxima del nombre del documento (columna de la bbdd)


@dataclass(frozen=True)
class TipoArchivo:
    content_type: str
    visible: bool  # True: el navegador puede mostrarlo inline (pdf, imágenes, texto)


_OFFICE = "application/vnd.openxmlformats-officedocument"
_ODF = "application/vnd.oasis.opendocument"
_TEXTO = "text/plain; charset=utf-8"

_TIPOS: dict[str, TipoArchivo] = {
    "pdf": TipoArchivo("application/pdf", True),
    "png": TipoArchivo("image/png", True),
    "jpg": TipoArchivo("image/jpeg", True),
    "jpeg": TipoArchivo("image/jpeg", True),
    "gif": TipoArchivo("image/gif", True),
    "webp": TipoArchivo("image/webp", True),
    "txt": TipoArchivo(_TEXTO, True),
    "md": TipoArchivo(_TEXTO, True),
    "csv": TipoArchivo(_TEXTO, True),
    "doc": TipoArchivo("application/msword", False),
    "docx": TipoArchivo(f"{_OFFICE}.wordprocessingml.document", False),
    "xls": TipoArchivo("application/vnd.ms-excel", False),
    "xlsx": TipoArchivo(f"{_OFFICE}.spreadsheetml.sheet", False),
    "ppt": TipoArchivo("application/vnd.ms-powerpoint", False),
    "pptx": TipoArchivo(f"{_OFFICE}.presentationml.presentation", False),
    "odt": TipoArchivo(f"{_ODF}.text", False),
    "ods": TipoArchivo(f"{_ODF}.spreadsheet", False),
    "odp": TipoArchivo(f"{_ODF}.presentation", False),
}


def tipo_de(nombre: str) -> TipoArchivo | None:
    """Tipo según la extensión (sin distinguir mayúsculas); None si no está permitido."""
    return _TIPOS.get(nombre.rpartition(".")[2].lower()) if "." in nombre else None


def limpiar_nombre(nombre: str) -> str:
    """Deja solo el nombre del archivo: sin ruta, sin caracteres de control y sin espacios a los lados.

    Algunos navegadores envían la ruta completa (`C:\\...`), y un `../` en el nombre sería un
    riesgo si algún día se guardase en disco. Lanza ValueError si queda vacío o pasa de 255.
    """
    nombre = nombre.replace("\\", "/").rpartition("/")[2]
    nombre = "".join(c for c in nombre if ord(c) >= 32 and ord(c) != 127).strip()
    # macOS manda «é» como «e» + tilde suelta (NFD) y Windows como una sola letra (NFC): sin
    # normalizar, el mismo nombre subido desde los dos no chocaría en el índice único.
    nombre = unicodedata.normalize("NFC", nombre)
    if not nombre or len(nombre) > NOMBRE_MAX:
        raise ValueError("Nombre de archivo vacío o de más de 255 caracteres")
    return nombre


def charset_texto(contenido: bytes) -> str:
    """Codificación de un documento de texto: UTF-8 si lo es; si no, Windows-1252.

    El Excel y el Bloc de notas en español guardan muchas veces en Windows-1252: servirlo como
    UTF-8 rompería las tildes al verlo en el navegador. Windows-1252 acepta casi cualquier byte,
    así que es el último recurso.
    """
    try:
        contenido.decode("utf-8")
    except UnicodeDecodeError:
        return "windows-1252"
    return "utf-8"


def content_disposition(nombre: str, inline: bool) -> str:
    """Cabecera de descarga: `filename` en ASCII para clientes viejos y `filename*` con los acentos."""
    ascii_ = unicodedata.normalize("NFKD", nombre).encode("ascii", "ignore").decode()
    ascii_ = ascii_.replace('"', "").replace("\\", "")  # nada que cierre las comillas de la cabecera
    modo = "inline" if inline else "attachment"
    return f"{modo}; filename=\"{ascii_}\"; filename*=UTF-8''{quote(nombre)}"
