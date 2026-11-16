"""Pide a Docling los trozos ya preparados de una muestra, el formato que iría al asistente.

Docling trocea por secciones (`/v1/chunk/hybrid/file`) y cada trozo trae su texto, los títulos
de los que cuelga y el número de página o diapositiva: es justo lo que se convierte en vector y
se cita en la respuesta, sin más conversiones. Uso: `python trocear.py muestras/memoria.docx`.
"""

import json
import os
import sys
from pathlib import Path

import httpx

DOCLING = os.environ.get("DOCLING_URL", "http://docling:5001")

ruta = Path(sys.argv[1])
with ruta.open("rb") as f:
    r = httpx.post(f"{DOCLING}/v1/chunk/hybrid/file", files={"files": (ruta.name, f)},
                   timeout=900)
r.raise_for_status()
trozos = [{k: c[k] for k in ("chunk_index", "headings", "page_numbers", "num_tokens", "text")}
          for c in r.json()["chunks"]]
salida = Path("salidas") / "trozos"
salida.mkdir(parents=True, exist_ok=True)
(salida / f"{ruta.name}.json").write_text(json.dumps(trozos, ensure_ascii=False, indent=1),
                                          encoding="utf-8")
print(json.dumps(trozos, ensure_ascii=False, indent=1))
