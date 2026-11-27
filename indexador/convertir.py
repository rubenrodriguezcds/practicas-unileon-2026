"""Qué camino sigue cada tipo de documento y conversión previa con LibreOffice.

Para qué: Docling no abre los formatos antiguos (.doc, .ppt: «An unexpected error occurred while
opening the document») ni los de OpenDocument o Visio. LibreOffice sin interfaz los pasa antes a
un formato que Docling sí lee (comprobado en prueba_docling/INFORME.md).

Destino de cada uno:
  - texto (.doc, .odt), presentaciones (.ppt, .odp) y Visio antiguo (.vsd) → PDF: se cita por página.
  - hojas antiguas (.xls, .ods) → .xlsx: en PDF una hoja se rompe en páginas y pierde la tabla.
  - Visio .vsdx → PDF para Docling, y además visio.py saca las conexiones «A → B», que en PDF se pierden.

Quién lo usa: procesar.py.
"""

import subprocess
import tempfile
from pathlib import Path

_DOCLING = {"pdf", "docx", "pptx", "xlsx", "png", "jpg", "jpeg", "gif", "webp", "txt", "md", "csv"}
_A_PDF = {"doc", "odt", "ppt", "odp", "vsd"}
_A_XLSX = {"xls", "ods"}
TIEMPO_MAX_S = 120


class ConversionError(Exception):
    """LibreOffice no pudo convertir el documento."""


def extension(nombre: str) -> str:
    return nombre.rpartition(".")[2].lower() if "." in nombre else ""


def camino(nombre: str) -> str | None:
    """"docling" (directo), "pdf" o "xlsx" (convertir antes), "visio" (.vsdx) o None (no soportado)."""
    ext = extension(nombre)
    if ext in _DOCLING:
        return "docling"
    if ext in _A_PDF:
        return "pdf"
    if ext in _A_XLSX:
        return "xlsx"
    if ext == "vsdx":
        return "visio"
    return None


def convertir(nombre: str, contenido: bytes, destino: str) -> tuple[str, bytes]:
    """Convierte con LibreOffice a `destino` ("pdf" o "xlsx"); devuelve (nombre nuevo, bytes).

    Raises:
        ConversionError: con el motivo, si LibreOffice falla, tarda más de TIEMPO_MAX_S o no deja salida.
    """
    with tempfile.TemporaryDirectory() as tmp:
        # Nombre fijo: el original puede traer caracteres que la línea de órdenes interprete.
        entrada = Path(tmp) / f"entrada.{extension(nombre)}"
        entrada.write_bytes(contenido)
        # Perfil propio en cada llamada: dos conversiones a la vez no se pisan el perfil de LibreOffice.
        perfil = (Path(tmp) / "perfil").as_uri()
        orden = ["soffice", f"-env:UserInstallation={perfil}", "--headless", "--norestore",
                 "--convert-to", destino, "--outdir", tmp, str(entrada)]
        try:
            r = subprocess.run(orden, capture_output=True, text=True, timeout=TIEMPO_MAX_S, check=False)
        except subprocess.TimeoutExpired:
            raise ConversionError(f"LibreOffice tardó más de {TIEMPO_MAX_S} s en convertir {nombre}") from None
        salida = Path(tmp) / f"entrada.{destino}"
        if r.returncode != 0 or not salida.exists():
            detalle = (r.stderr or r.stdout or "sin mensaje").strip()[:300]
            raise ConversionError(f"LibreOffice no pudo convertir {nombre}: {detalle}")
        return f"{nombre.rpartition('.')[0]}.{destino}", salida.read_bytes()
