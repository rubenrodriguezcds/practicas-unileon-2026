"""Tests de convertir.py: el camino de cada tipo y la llamada a LibreOffice (sustituida)."""

import subprocess
from pathlib import Path

import convertir
import pytest
from convertir import ConversionError, camino


@pytest.mark.parametrize("nombre, esperado", [
    ("informe.pdf", "docling"), ("INFORME.PDF", "docling"), ("memoria.docx", "docling"),
    ("presentacion.pptx", "docling"), ("presupuesto.xlsx", "docling"), ("acta.png", "docling"),
    ("foto.JPG", "docling"), ("notas.txt", "docling"), ("datos.csv", "docling"), ("leeme.md", "docling"),
    ("memoria.doc", "pdf"), ("presentacion.ppt", "pdf"), ("texto.odt", "pdf"), ("charla.odp", "pdf"),
    ("viejo.vsd", "pdf"), ("cuentas.xls", "xlsx"), ("cuentas.ods", "xlsx"),
    ("arquitectura.vsdx", "visio"), ("programa.exe", None), ("sin_extension", None),
])
def test_camino_de_cada_tipo(nombre, esperado):
    assert camino(nombre) == esperado


def falso_soffice(monkeypatch, returncode=0, escribe=True, stderr=""):
    """Sustituye subprocess.run: «convierte» escribiendo el fichero de salida esperado."""
    llamadas = []

    def run(orden, **kw):
        llamadas.append(orden)
        outdir, destino = Path(orden[orden.index("--outdir") + 1]), orden[orden.index("--convert-to") + 1]
        if escribe:
            (outdir / f"entrada.{destino}").write_bytes(b"%PDF convertido")
        return subprocess.CompletedProcess(orden, returncode, "", stderr)

    monkeypatch.setattr(convertir.subprocess, "run", run)
    return llamadas


def test_convierte_y_devuelve_el_nombre_nuevo(monkeypatch):
    llamadas = falso_soffice(monkeypatch)
    assert convertir.convertir("Memoria final.doc", b"doc", "pdf") == ("Memoria final.pdf", b"%PDF convertido")
    assert "--headless" in llamadas[0] and llamadas[0][-1].endswith("entrada.doc")


def test_codigo_de_error_da_conversion_error_con_el_motivo(monkeypatch):
    falso_soffice(monkeypatch, returncode=1, escribe=False, stderr="Error: source file could not be loaded")
    with pytest.raises(ConversionError, match="could not be loaded"):
        convertir.convertir("roto.doc", b"x", "pdf")


def test_sin_fichero_de_salida_es_error(monkeypatch):
    falso_soffice(monkeypatch, escribe=False)
    with pytest.raises(ConversionError, match="no pudo convertir"):
        convertir.convertir("raro.ppt", b"x", "pdf")


def test_timeout_es_error(monkeypatch):
    def run(orden, **kw):
        raise subprocess.TimeoutExpired(orden, kw["timeout"])
    monkeypatch.setattr(convertir.subprocess, "run", run)
    with pytest.raises(ConversionError, match="tardó más de 120 s"):
        convertir.convertir("enorme.doc", b"x", "pdf")
