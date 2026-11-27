"""Procesa un documento de principio a fin: convertir, trocear, vectorizar y guardar.

Para qué: une las piezas del indexador en el orden de la spec:
  camino (convertir.py) → LibreOffice si hace falta → Docling (trozos + JSON) → Visio (.vsdx:
  conexiones «A → B» sacadas del original) → embeddings (Ollama) → guardar.

Nada falla en silencio y nada se queda en «procesando»: cualquier fallo, conocido (LibreOffice,
Docling, Visio, Ollama) o inesperado (un fichero corrupto puede lanzar KeyError, BadZipFile…),
acaba en `marcar_error` con un motivo legible, que se ve en la ficha del proyecto. Los fallos se
reintentan según cola.py. Un documento sin texto (PDF en blanco, imagen sin letras) termina en
«hecho» con 0 trozos y sin llamar a Ollama, en vez de reintentarse sin fin.

Las piezas entran como `Dependencias` para que los tests usen dobles sin servicios reales.

Quién lo usa: main.py.
"""

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass

import cola
import convertir
import docling_cliente
import embeddings
import guardar
import visio
from convertir import ConversionError
from docling_cliente import DoclingError
from embeddings import EmbeddingsError
from visio import VisioError

log = logging.getLogger("indexador")

_CONOCIDOS = (ConversionError, DoclingError, VisioError, EmbeddingsError)


@dataclass(frozen=True)
class Dependencias:
    convertir: Callable = convertir.convertir
    trocear: Callable = docling_cliente.trocear
    trozos_visio: Callable = visio.trozos_visio
    vectorizar: Callable = embeddings.vectorizar
    guardar: Callable = guardar.guardar
    marcar_error: Callable = cola.marcar_error


def procesar(conn, doc: dict, cfg, dep: Dependencias = Dependencias()) -> str:
    """Indexa `doc` ({id, proyecto_id, nombre, contenido}); devuelve "hecho", "error" o "descartado"."""
    inicio = time.monotonic()
    nombre, contenido = doc["nombre"], doc["contenido"]
    ruta = convertir.camino(nombre)
    if ruta is None:
        return _error(conn, doc, dep, f"El asistente no sabe leer archivos .{convertir.extension(nombre)}")
    try:
        if ruta in ("pdf", "visio"):
            nombre, contenido = dep.convertir(nombre, contenido, "pdf")
        elif ruta == "xlsx":
            nombre, contenido = dep.convertir(nombre, contenido, "xlsx")
        resultado = dep.trocear(cfg.docling_url, nombre, contenido)
        trozos = list(resultado.trozos)
        if ruta == "visio":
            trozos += dep.trozos_visio(doc["contenido"])  # del .vsdx original: el PDF no tiene las flechas
        vectores = dep.vectorizar([t.texto for t in trozos], cfg.ollama_url, cfg.embeddings_modelo) if trozos else []
        guardado = dep.guardar(conn, doc, trozos, vectores, resultado)
    except _CONOCIDOS as e:
        return _error(conn, doc, dep, str(e))
    except Exception as e:  # noqa: BLE001 — un documento raro no puede dejarse en «procesando»
        log.exception("Fallo inesperado con el documento %s («%s»)", doc["id"], doc["nombre"])
        return _error(conn, doc, dep, f"Error inesperado al indexar ({type(e).__name__}: {e})")
    if not guardado:
        return "descartado"  # se borró mientras se indexaba; guardar.py ya lo dejó en el log
    log.info("Documento %s («%s») indexado: %d trozos en %.1f s",
             doc["id"], doc["nombre"], len(trozos), time.monotonic() - inicio)
    return "hecho"


def _error(conn, doc: dict, dep: Dependencias, motivo: str) -> str:
    log.warning("Documento %s («%s») con error: %s", doc["id"], doc["nombre"], motivo)
    dep.marcar_error(conn, doc["id"], motivo)
    return "error"
