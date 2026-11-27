"""Tests de guardar.py con una conexión falsa que apunta lo que se ejecuta.

El SQL de verdad se comprueba en la prueba de punta a punta (Task 10) con la bbdd real; aquí se
fija el orden (borrar, insertar, marcar hecho, confirmar) y qué pasa si el documento ya no existe.
"""

import logging

import psycopg
from docling_cliente import Resultado, Trozo
from guardar import guardar

DOC = {"id": 7, "proyecto_id": 3, "nombre": "informe.pdf"}
TROZOS = [Trozo("Resumen\nCuesta 48.500 €.", ["Resumen"], [1]), Trozo("Sin título", [], [])]
VECTORES = [[0.5] * 1024, [0.25] * 1024]
RESULTADO = Resultado(trozos=TROZOS, docling_json={"name": "informe"}, version="1.38.2")


class FalsaConexion:
    def __init__(self, falla_al_insertar=None):
        self.ordenes, self.filas = [], []
        self.falla_al_insertar = falla_al_insertar

    def execute(self, sql, params=None):
        self.ordenes.append(" ".join(sql.split())[:30])

    def cursor(self):
        return self

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def executemany(self, sql, filas):
        self.ordenes.append(" ".join(sql.split())[:30])
        if self.falla_al_insertar:
            raise self.falla_al_insertar
        self.filas.extend(filas)

    def commit(self):
        self.ordenes.append("COMMIT")

    def rollback(self):
        self.ordenes.append("ROLLBACK")


def test_borra_lo_anterior_inserta_marca_hecho_y_confirma():
    conn = FalsaConexion()
    assert guardar(conn, DOC, TROZOS, VECTORES, RESULTADO) is True
    assert conn.ordenes == ["DELETE FROM fragmentos WHERE d", "INSERT INTO fragmentos (docume",
                            "UPDATE indexado SET estado = '", "COMMIT"]


def test_cada_fila_lleva_orden_titulos_paginas_y_vector_como_texto_de_pgvector():
    conn = FalsaConexion()
    guardar(conn, DOC, TROZOS, VECTORES, RESULTADO)
    primera, segunda = conn.filas
    assert primera[:6] == (7, 3, 0, "Resumen\nCuesta 48.500 €.", ["Resumen"], [1])
    assert primera[6] == "[" + ",".join(["0.5"] * 1024) + "]"
    assert primera[7] == "Resumen\nCuesta 48.500 €."  # texto para la búsqueda por palabras
    assert segunda[:6] == (7, 3, 1, "Sin título", [], [])


def test_documento_sin_trozos_no_inserta_pero_queda_hecho():
    conn = FalsaConexion()
    assert guardar(conn, DOC, [], [], RESULTADO) is True
    assert conn.ordenes == ["DELETE FROM fragmentos WHERE d", "UPDATE indexado SET estado = '", "COMMIT"]


def test_documento_borrado_mientras_se_indexaba_se_descarta_sin_fallar(caplog):
    caplog.set_level(logging.INFO)  # es un aviso informativo, no un error
    conn = FalsaConexion(falla_al_insertar=psycopg.errors.ForeignKeyViolation("documento_id no existe"))
    assert guardar(conn, DOC, TROZOS, VECTORES, RESULTADO) is False
    assert conn.ordenes[-1] == "ROLLBACK" and "COMMIT" not in conn.ordenes
    assert "borrado mientras se indexaba" in caplog.text
