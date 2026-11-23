"""Guarda los trozos de un documento con sus vectores y lo marca como indexado.

Para qué: es el ÚNICO sitio que escribe en `fragmentos` (si un día los vectores van a una base
vectorial aparte, como Qdrant, solo cambia este fichero y el buscador de la API).

Cómo: en una sola transacción borra los trozos anteriores del documento (por si es un reintento),
inserta los nuevos y apunta «hecho» (cola.marcar_hecho). Todo o nada: un documento nunca queda
con la mitad de sus trozos.

- El vector va como texto «[0.1,0.2,…]» y Postgres lo convierte a `halfvec`: así no hace falta
  la librería de pgvector para Python.
- `busqueda` (búsqueda por palabras) se calcula aquí con `to_tsvector('spanish', unaccent(...))`:
  unaccent no es IMMUTABLE y no puede ir en una columna generada (ver migración 005). Se usa el
  texto del trozo, que ya lleva delante sus títulos (Docling y visio.py los ponen).

Documento borrado mientras se indexaba: insertar sus trozos viola la clave foránea. Se deshace,
se apunta en el log y se sigue con el siguiente; no es un error que haya que ver en la ficha
(el documento ya no existe).

Quién lo usa: procesar.py.
"""

import logging

import cola
import psycopg

log = logging.getLogger("indexador")

_BORRAR = "DELETE FROM fragmentos WHERE documento_id = %s"
_INSERTAR = """
INSERT INTO fragmentos (documento_id, proyecto_id, orden, texto, titulos, paginas, embedding, busqueda)
VALUES (%s, %s, %s, %s, %s, %s, %s::halfvec, to_tsvector('spanish', unaccent(%s)))
"""


def guardar(conn, doc: dict, trozos: list, vectores: list[list[float]], resultado) -> bool:
    """True si quedó guardado; False si el documento se borró mientras se indexaba."""
    filas = [(doc["id"], doc["proyecto_id"], orden, t.texto, list(t.titulos), list(t.paginas),
              "[" + ",".join(str(x) for x in v) + "]", t.texto)
             for orden, (t, v) in enumerate(zip(trozos, vectores, strict=True))]
    try:
        conn.execute(_BORRAR, (doc["id"],))
        if filas:
            with conn.cursor() as cur:
                cur.executemany(_INSERTAR, filas)
        cola.marcar_hecho(conn, doc["id"], resultado.docling_json, resultado.version)
        conn.commit()
    except psycopg.errors.ForeignKeyViolation:
        conn.rollback()
        log.info("Documento %s («%s») borrado mientras se indexaba: se descarta", doc["id"], doc["nombre"])
        return False
    return True
