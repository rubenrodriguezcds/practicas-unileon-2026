"""Saca el contenido de los diagramas Visio (.vsdx), que Docling no lee.

Por cada página: el texto de cada forma y las conexiones «A → B» entre formas, que es lo que
da sentido a un diagrama y se pierde si solo se pasa a PDF. Escribe `salidas/visio/<nombre>.md`
con el mismo formato que usaría el indexado. Los .vsd (binario antiguo) no los abre `vsdx`:
habría que pasarlos antes a PDF con LibreOffice, como hace `extraer.py`.
"""

from pathlib import Path

from vsdx import VisioFile

MUESTRAS = Path("muestras")
SALIDA = Path("salidas") / "visio"


def extraer(ruta: Path) -> str:
    lineas = [f"# {ruta.stem}"]
    with VisioFile(str(ruta)) as vis:
        for n, pagina in enumerate(vis.pages, start=1):
            lineas.append(f"\n## Página {n}: {pagina.name}\n")
            textos = {}
            for forma in pagina.all_shapes:
                texto = (forma.text or "").strip()
                if texto:
                    textos[forma.ID] = texto
                    lineas.append(f"- {texto}")
            # Cada conector tiene dos Connect (inicio y fin): se juntan en «origen → destino».
            extremos = {}
            for c in pagina.connects:
                extremos.setdefault(c.connector_shape_id, {})[c.from_rel] = c.shape_id
            flechas = [f"- {textos.get(e.get('BeginX'), '?')} → {textos.get(e.get('EndX'), '?')}"
                       for e in extremos.values()]
            if flechas:
                lineas.append("\nConexiones:\n")
                lineas.extend(flechas)
    return "\n".join(lineas) + "\n"


def main() -> None:
    SALIDA.mkdir(parents=True, exist_ok=True)
    for ruta in sorted(MUESTRAS.glob("*.vsdx")):
        md = extraer(ruta)
        (SALIDA / f"{ruta.name}.md").write_text(md, encoding="utf-8")
        print(md)


if __name__ == "__main__":
    main()
