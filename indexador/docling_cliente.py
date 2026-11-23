"""Cliente de Docling: manda un documento y recibe sus trozos y el documento convertido.

Para qué: Docling (contenedor `docling`, imagen oficial docling-serve) lee el documento (texto,
títulos, tablas, OCR si es escaneado) y lo corta en trozos con su sección y sus páginas, que es
lo que se vectoriza y se cita.

Una sola llamada: `POST /v1/chunk/hybrid/file` con `include_converted_doc=true` devuelve los
trozos y, en `documents[0].content.json_content`, el documento entero en JSON (comprobado contra
docling-serve 1.38.2). El JSON se guarda para volver a trocear sin reprocesar el original.

Opciones fijas: OCR en español (solo actúa donde no hay texto digital), tablas en modo
«accurate» (en la prueba «fast» dio lo mismo y tardó igual), imágenes como marcador (no se
guardan) y trozos de hasta 512 tokens (el modelo de embeddings admite muchos más; trozos algo
más largos que los 256 por defecto dan más contexto a cada cita).

Quién lo usa: procesar.py; Trozo también visio.py y guardar.py.
"""

from dataclasses import dataclass, field

import httpx

TIEMPO_MAX_S = 900  # un PDF escaneado largo pasa por OCR página a página


@dataclass(frozen=True)
class Trozo:
    texto: str
    titulos: list[str] = field(default_factory=list)
    paginas: list[int] = field(default_factory=list)  # vacío en Word: no tiene páginas fijas


@dataclass(frozen=True)
class Resultado:
    trozos: list[Trozo]
    docling_json: dict | None
    version: str | None


class DoclingError(Exception):
    """Docling no responde o no pudo convertir el documento."""


_OPCIONES = {
    "include_converted_doc": "true",
    "convert_to_formats": "json",
    "convert_ocr_lang": "es",
    "convert_table_mode": "accurate",
    "convert_image_export_mode": "placeholder",
    "chunking_max_tokens": "512",
}


def trocear(url: str, nombre: str, contenido: bytes, cliente: httpx.Client | None = None) -> Resultado:
    """Trozos y JSON del documento. `cliente` solo se pasa en los tests (transporte simulado).

    Raises:
        DoclingError: si Docling no responde, responde con error HTTP o no puede convertirlo.
    """
    cliente = cliente or httpx.Client(timeout=TIEMPO_MAX_S)
    try:
        version = cliente.get(f"{url}/version").json().get("docling-serve")
        r = cliente.post(f"{url}/v1/chunk/hybrid/file", data=_OPCIONES, files={"files": (nombre, contenido)})
    except httpx.HTTPError as e:
        raise DoclingError(f"Docling no responde ({type(e).__name__})") from None
    if r.status_code != 200:
        raise DoclingError(f"Docling respondió {r.status_code}: {r.text[:300]}")
    cuerpo = r.json()
    doc = (cuerpo.get("documents") or [{}])[0]
    if doc.get("status") not in ("success", "partial_success"):
        errores = "; ".join(e.get("error_message", "") for e in doc.get("errors") or []) or "sin detalle"
        raise DoclingError(f"Docling no pudo leer el documento: {errores}")
    trozos = [Trozo(texto=c["text"], titulos=c.get("headings") or [], paginas=c.get("page_numbers") or [])
              for c in cuerpo.get("chunks", []) if (c.get("text") or "").strip()]
    return Resultado(trozos=trozos, docling_json=(doc.get("content") or {}).get("json_content"), version=version)
