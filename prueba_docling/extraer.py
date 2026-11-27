"""Manda cada muestra a Docling y mide qué sale.

Por cada documento guarda en `salidas/<variante>/` el Markdown (lo que se trocearía para el
asistente) y el JSON de Docling (estructura con número de página de cada elemento, para citar),
y añade una fila a `resultados.csv`: estado, tiempo, páginas, tablas, caracteres y cuántas de
las frases conocidas (`muestras/esperado.json`) aparecen. Visio no lo lee Docling: se pasa antes
a PDF con LibreOffice. Uso en README.md.
"""

import argparse
import csv
import json
import os
import re
import subprocess
import time
from pathlib import Path

import httpx

DOCLING = os.environ.get("DOCLING_URL", "http://docling:5001")
MUESTRAS = Path("muestras")
A_PDF = {".vsdx", ".vsd"}  # formatos que Docling no acepta y se convierten antes
ANTIGUOS = {".doc", ".ppt"}


def a_pdf(ruta: Path, destino: Path) -> Path:
    destino.mkdir(parents=True, exist_ok=True)
    subprocess.run(["soffice", "--headless", "--convert-to", "pdf", "--outdir", str(destino),
                    str(ruta)], check=True, capture_output=True)
    return destino / f"{ruta.stem}.pdf"


def normalizar(texto: str) -> str:
    # Markdown escapa algunos signos y parte líneas: se compara sin eso.
    return re.sub(r"\s+", " ", texto.replace("\\", "")).strip().lower()


def convertir(ruta: Path, ocr: bool, tablas: str) -> dict:
    with ruta.open("rb") as f:
        r = httpx.post(
            f"{DOCLING}/v1/convert/file",
            files={"files": (ruta.name, f)},
            data={"to_formats": ["md", "json"], "do_ocr": str(ocr).lower(), "ocr_lang": ["es"],
                  "table_mode": tablas, "image_export_mode": "placeholder"},
            timeout=900,
        )
    r.raise_for_status()
    return r.json()


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--variante", default="base", help="nombre de la carpeta de salida")
    p.add_argument("--tablas", choices=["fast", "accurate"], default="accurate")
    p.add_argument("--sin-ocr", action="store_true")
    p.add_argument("--convertir-antiguos", action="store_true",
                   help="pasar .doc/.ppt a PDF con LibreOffice antes de Docling")
    args = p.parse_args()

    salida = Path("salidas") / args.variante
    salida.mkdir(parents=True, exist_ok=True)
    esperado = json.loads((MUESTRAS / "esperado.json").read_text(encoding="utf-8"))
    filas = []
    for ruta in sorted(MUESTRAS.iterdir()):
        if ruta.name == "esperado.json":
            continue
        fila = {"documento": ruta.name, "estado": "", "segundos": "", "paginas": "",
                "tablas": "", "caracteres": "", "frases": "", "con_pagina": "", "error": ""}
        enviado = ruta
        if ruta.suffix in A_PDF or (args.convertir_antiguos and ruta.suffix in ANTIGUOS):
            enviado = a_pdf(ruta, salida / "convertidos")
        inicio = time.perf_counter()
        try:
            res = convertir(enviado, not args.sin_ocr, args.tablas)
        except httpx.HTTPError as e:
            fila.update(estado="error", error=str(e)[:200])
            filas.append(fila)
            print(f"{ruta.name}: ERROR {e}")
            continue
        fila["segundos"] = round(time.perf_counter() - inicio, 1)
        doc = res.get("document") or {}
        md = doc.get("md_content") or ""
        js = doc.get("json_content") or {}
        (salida / f"{ruta.name}.md").write_text(md, encoding="utf-8")
        (salida / f"{ruta.name}.json").write_text(json.dumps(js, ensure_ascii=False, indent=1),
                                                   encoding="utf-8")
        textos = js.get("texts", [])
        frases = esperado.get(ruta.name, [])
        encontradas = sum(normalizar(f) in normalizar(md) for f in frases)
        fila.update(
            estado=res.get("status", ""),
            paginas=len(js.get("pages", {})),
            tablas=len(js.get("tables", [])),
            caracteres=len(md),
            frases=f"{encontradas}/{len(frases)}",
            # Elementos de texto que saben de qué página vienen (lo que permite citar).
            con_pagina=f"{sum(bool(t.get('prov')) for t in textos)}/{len(textos)}",
            error="; ".join(str(e) for e in res.get("errors", []))[:200],
        )
        filas.append(fila)
        print(f"{ruta.name}: {fila['estado']} {fila['segundos']} s, frases {fila['frases']}")

    with (salida / "resultados.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(filas[0]))
        w.writeheader()
        w.writerows(filas)
    print(f"Resultados en {salida}/resultados.csv")


if __name__ == "__main__":
    main()
