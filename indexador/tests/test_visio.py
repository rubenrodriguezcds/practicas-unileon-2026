"""Tests de visio.py con la muestra ficticia `datos/arquitectura.vsdx` (copiada de prueba_docling/).

La muestra tiene una página «Arquitectura» con tres formas (Usuarios, Portal de facturación, Base de
datos de clientes) unidas por dos conectores.
"""

from pathlib import Path

import pytest
from docling_cliente import Trozo
from visio import VisioError, trozos_visio

MUESTRA = (Path(__file__).parent / "datos" / "arquitectura.vsdx").read_bytes()


def test_un_trozo_por_pagina_con_titulo_y_numero():
    trozos = trozos_visio(MUESTRA)
    assert len(trozos) == 1
    assert isinstance(trozos[0], Trozo)
    assert trozos[0].titulos == ["Diagrama: Arquitectura"]
    assert trozos[0].paginas == [1]


def test_el_texto_lleva_las_formas_y_las_conexiones():
    texto = trozos_visio(MUESTRA)[0].texto
    for forma in ("Usuarios", "Portal de facturación", "Base de datos de clientes"):
        assert forma in texto
    assert "Usuarios → Portal de facturación" in texto
    assert "Portal de facturación → Base de datos de clientes" in texto


def test_el_texto_empieza_por_su_titulo_como_los_trozos_de_docling():
    # Docling ya pone los títulos delante del texto de cada trozo y se vectoriza tal cual:
    # los de Visio tienen que ir igual para que la búsqueda los trate del mismo modo.
    assert trozos_visio(MUESTRA)[0].texto.startswith("Diagrama: Arquitectura\n")


@pytest.mark.parametrize("contenido", [b"", b"esto no es un vsdx", b"PK\x03\x04roto"])
def test_un_fichero_que_no_es_visio_da_visio_error(contenido):
    with pytest.raises(VisioError, match="No se pudo leer el diagrama Visio"):
        trozos_visio(contenido)
