"""Tests de las reglas de tipos y nombres de los documentos (app/documentos.py).

Para qué: garantizar que solo se admiten los tipos de la lista, que un nombre de archivo
no puede arrastrar rutas ni caracteres de control, y que la cabecera de descarga conserva
los acentos sin permitir inyectar comillas.
"""

import pytest

from app.documentos import TipoArchivo, charset_texto, content_disposition, limpiar_nombre, tipo_de

DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


def test_tipo_de_pdf_y_sin_distinguir_mayusculas():
    assert tipo_de("a.pdf") == TipoArchivo("application/pdf", True)
    assert tipo_de("INFORME.PDF").content_type == "application/pdf"


def test_tipo_de_texto_e_imagenes_se_ven():
    assert tipo_de("notas.md") == TipoArchivo("text/plain; charset=utf-8", True)
    assert tipo_de("x.png").visible
    assert tipo_de("x.jpeg").content_type == tipo_de("x.jpg").content_type == "image/jpeg"


def test_tipo_de_office_se_descarga_sin_verse():
    assert tipo_de("x.docx").visible is False
    assert tipo_de("x.docx").content_type == DOCX


@pytest.mark.parametrize("nombre", ["x.html", "x.svg", "x.exe", "sin_extension", "x."])
def test_tipo_de_rechaza_lo_no_permitido(nombre):
    assert tipo_de(nombre) is None


def test_limpiar_nombre_quita_rutas_espacios_y_control():
    assert limpiar_nombre("C:\\Users\\a\\informe.pdf") == "informe.pdf"
    assert limpiar_nombre("../../etc/informe.pdf") == "informe.pdf"
    assert limpiar_nombre("  a.pdf  ") == "a.pdf"
    assert limpiar_nombre("a\x00b.pdf") == "ab.pdf"


def test_limpiar_nombre_normaliza_los_acentos_de_mac():
    assert limpiar_nombre("técnica.pdf") == "técnica.pdf"


def test_charset_de_texto():
    assert charset_texto("año".encode()) == "utf-8"
    assert charset_texto("﻿año".encode()) == "utf-8"  # con BOM, como lo guarda el Bloc de notas
    assert charset_texto("año".encode("cp1252")) == "windows-1252"


@pytest.mark.parametrize("nombre", ["", "   ", "a" * 252 + ".pdf"])
def test_limpiar_nombre_rechaza_vacio_o_largo(nombre):
    with pytest.raises(ValueError):
        limpiar_nombre(nombre)


def test_content_disposition_con_acentos():
    esperado = "filename=\"Memoria tecnica.pdf\"; filename*=UTF-8''Memoria%20t%C3%A9cnica.pdf"
    assert content_disposition("Memoria técnica.pdf", False) == f"attachment; {esperado}"
    assert content_disposition("Memoria técnica.pdf", True) == f"inline; {esperado}"


def test_content_disposition_no_deja_comillas():
    assert content_disposition('a"b.pdf', False).startswith('attachment; filename="ab.pdf";')
