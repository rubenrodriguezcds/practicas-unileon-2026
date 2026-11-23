"""Texto y conexiones de los diagramas Visio (.vsdx), que Docling no lee.

Para qué: en un diagrama lo que da sentido son las flechas («Usuarios → Portal de facturación»), y
al pasarlo a PDF solo queda el texto suelto de las cajas. Este módulo saca, por cada página, el
texto de las formas y las conexiones entre ellas, para que se puedan buscar y citar.

Formato: un Trozo por página, con título «Diagrama: <página>» y su número de página. El título va
también delante del texto, igual que en los trozos de Docling (que se vectorizan tal cual), para
que la búsqueda trate los dos del mismo modo.

Los .vsd (binario antiguo) no los abre `vsdx`: van solo por LibreOffice → PDF → Docling (sin
conexiones), como decide convertir.py.

Quién lo usa: procesar.py, para los .vsdx (además de los trozos que da Docling del PDF).
Basado en prueba_docling/visio.py.
"""

import tempfile
from pathlib import Path

from docling_cliente import Trozo
from vsdx import VisioFile


class VisioError(Exception):
    """El contenido no es un .vsdx que se pueda abrir."""


def trozos_visio(contenido: bytes) -> list[Trozo]:
    """Un trozo por página con texto: título, formas y conexiones «A → B».

    Raises:
        VisioError: si el fichero está vacío, corrupto o no es un .vsdx.
    """
    # `vsdx` solo abre rutas: se escribe en un directorio temporal que se borra al terminar.
    with tempfile.TemporaryDirectory() as tmp:
        ruta = Path(tmp) / "diagrama.vsdx"
        ruta.write_bytes(contenido)
        try:
            with VisioFile(str(ruta)) as vis:
                return [t for n, pagina in enumerate(vis.pages, start=1) if (t := _trozo(n, pagina))]
        except Exception as e:  # zipfile.BadZipFile, KeyError, XML mal formado…: todos son «no se puede leer»
            raise VisioError(f"No se pudo leer el diagrama Visio ({type(e).__name__}: {e})") from None


def _trozo(n: int, pagina) -> Trozo | None:
    """Trozo de una página, o None si no tiene ningún texto (no aporta nada a la búsqueda)."""
    textos = {}
    for forma in pagina.all_shapes:
        texto = (forma.text or "").strip()
        if texto:
            textos[forma.ID] = texto
    # Cada conector tiene dos «Connect» (su inicio y su fin): se juntan en «origen → destino».
    extremos: dict[str, dict[str, str]] = {}
    for c in pagina.connects:
        extremos.setdefault(c.connector_shape_id, {})[c.from_rel] = c.shape_id
    flechas = [f"{textos.get(e.get('BeginX'), '?')} → {textos.get(e.get('EndX'), '?')}" for e in extremos.values()]
    if not textos and not flechas:
        return None
    titulo = f"Diagrama: {pagina.name}"
    lineas = [titulo, *textos.values()]
    if flechas:
        lineas += ["Conexiones:", *flechas]
    return Trozo(texto="\n".join(lineas), titulos=[titulo], paginas=[n])
