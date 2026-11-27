"""Tests de procesar.py: el camino completo de un documento, con dobles de cada pieza.

Ninguna pieza real se usa: LibreOffice, Docling, Visio, Ollama y la bbdd se sustituyen por
funciones que apuntan con qué se las llamó, para comprobar el orden y qué llega a cada una.
"""

import pytest
from config import Config
from convertir import ConversionError
from docling_cliente import DoclingError, Resultado, Trozo
from embeddings import EmbeddingsError
from procesar import Dependencias, procesar
from visio import VisioError

CFG = Config(db_dsn="postgresql://x", docling_url="http://docling:5001",
             ollama_url="http://ollama:11434", embeddings_modelo="bge-m3")
CONN = object()  # procesar solo la pasa a guardar y marcar_error


def doc(nombre="informe.pdf", contenido=b"%PDF-original"):
    return {"id": 7, "proyecto_id": 3, "nombre": nombre, "contenido": contenido}


class Dobles:
    """Dependencias falsas que apuntan sus llamadas en `self.llamadas`."""

    def __init__(self, trozos=None, fallo=None, donde=None):
        self.llamadas = []
        self.trozos = [Trozo("Resumen\nLa migración costará 48.500 €.", ["Resumen"], [1])] if trozos is None else trozos
        self.fallo, self.donde = fallo, donde

    def _quizas_falla(self, pieza):
        if self.donde == pieza:
            raise self.fallo

    def convertir(self, nombre, contenido, destino):
        self.llamadas.append(("convertir", nombre, destino))
        self._quizas_falla("convertir")
        return f"{nombre.rpartition('.')[0]}.{destino}", b"%PDF-convertido"

    def trocear(self, url, nombre, contenido):
        self.llamadas.append(("trocear", url, nombre, contenido))
        self._quizas_falla("trocear")
        return Resultado(trozos=list(self.trozos), docling_json={"name": nombre}, version="1.38.2")

    def trozos_visio(self, contenido):
        self.llamadas.append(("visio", contenido))
        self._quizas_falla("visio")
        return [Trozo("Diagrama: Arquitectura\nUsuarios → Portal", ["Diagrama: Arquitectura"], [1])]

    def vectorizar(self, textos, url, modelo):
        self.llamadas.append(("vectorizar", textos, url, modelo))
        self._quizas_falla("vectorizar")
        return [[0.1] * 1024 for _ in textos]

    def guardar(self, conn, documento, trozos, vectores, resultado):
        self.llamadas.append(("guardar", documento["id"], [t.texto for t in trozos], len(vectores), resultado.version))
        self._quizas_falla("guardar")
        return self.guardado

    guardado = True

    def marcar_error(self, conn, documento_id, motivo):
        self.llamadas.append(("error", documento_id, motivo))

    def dependencias(self):
        return Dependencias(convertir=self.convertir, trocear=self.trocear, trozos_visio=self.trozos_visio,
                            vectorizar=self.vectorizar, guardar=self.guardar, marcar_error=self.marcar_error)

    def piezas(self):
        return [ll[0] for ll in self.llamadas]


def test_pdf_va_directo_a_docling_vectoriza_y_guarda():
    d = Dobles()
    assert procesar(CONN, doc(), CFG, d.dependencias()) == "hecho"
    assert d.piezas() == ["trocear", "vectorizar", "guardar"]
    assert d.llamadas[0] == ("trocear", "http://docling:5001", "informe.pdf", b"%PDF-original")
    assert d.llamadas[1] == ("vectorizar", ["Resumen\nLa migración costará 48.500 €."], "http://ollama:11434", "bge-m3")
    assert d.llamadas[2] == ("guardar", 7, ["Resumen\nLa migración costará 48.500 €."], 1, "1.38.2")


@pytest.mark.parametrize("nombre, destino, convertido", [("memoria.doc", "pdf", "memoria.pdf"),
                                                         ("cuentas.ods", "xlsx", "cuentas.xlsx")])
def test_formatos_antiguos_pasan_antes_por_libreoffice(nombre, destino, convertido):
    d = Dobles()
    assert procesar(CONN, doc(nombre, b"original"), CFG, d.dependencias()) == "hecho"
    assert d.llamadas[0] == ("convertir", nombre, destino)
    assert d.llamadas[1] == ("trocear", "http://docling:5001", convertido, b"%PDF-convertido")


def test_vsdx_pasa_a_pdf_y_anade_los_trozos_de_visio_del_original():
    d = Dobles()
    assert procesar(CONN, doc("arquitectura.vsdx", b"vsdx-original"), CFG, d.dependencias()) == "hecho"
    assert d.piezas() == ["convertir", "trocear", "visio", "vectorizar", "guardar"]
    assert d.llamadas[2] == ("visio", b"vsdx-original")  # las conexiones salen del .vsdx, no del PDF
    assert d.llamadas[-1][2] == ["Resumen\nLa migración costará 48.500 €.", "Diagrama: Arquitectura\nUsuarios → Portal"]


def test_documento_sin_texto_termina_hecho_sin_llamar_a_ollama():
    d = Dobles(trozos=[])
    assert procesar(CONN, doc("en_blanco.pdf"), CFG, d.dependencias()) == "hecho"
    assert d.piezas() == ["trocear", "guardar"]
    assert d.llamadas[-1] == ("guardar", 7, [], 0, "1.38.2")


def test_tipo_no_soportado_queda_en_error_sin_llamar_a_nada():
    d = Dobles()
    assert procesar(CONN, doc("programa.exe"), CFG, d.dependencias()) == "error"
    assert d.llamadas == [("error", 7, "El asistente no sabe leer archivos .exe")]


@pytest.mark.parametrize("donde, fallo", [
    ("convertir", ConversionError("LibreOffice no pudo convertir memoria.doc: roto")),
    ("trocear", DoclingError("Docling no responde (ConnectError)")),
    ("visio", VisioError("No se pudo leer el diagrama Visio (BadZipFile: x)")),
    ("vectorizar", EmbeddingsError("Ollama no responde en http://ollama:11434 (ConnectError)")),
])
def test_fallo_conocido_queda_en_error_con_su_motivo(donde, fallo):
    nombre = {"convertir": "memoria.doc", "visio": "a.vsdx"}.get(donde, "informe.pdf")
    d = Dobles(fallo=fallo, donde=donde)
    assert procesar(CONN, doc(nombre), CFG, d.dependencias()) == "error"
    assert d.llamadas[-1] == ("error", 7, str(fallo))
    assert "guardar" not in d.piezas()


def test_fallo_inesperado_tambien_queda_en_error_y_no_en_procesando():
    d = Dobles(fallo=KeyError("Page"), donde="trocear")
    assert procesar(CONN, doc(), CFG, d.dependencias()) == "error"
    assert d.llamadas[-1] == ("error", 7, "Error inesperado al indexar (KeyError: 'Page')")


def test_documento_borrado_mientras_se_indexaba_queda_descartado_sin_error():
    d = Dobles()
    d.guardado = False  # guardar.py vio la clave foránea rota: el documento ya no existe
    assert procesar(CONN, doc(), CFG, d.dependencias()) == "descartado"
    assert "error" not in d.piezas()
