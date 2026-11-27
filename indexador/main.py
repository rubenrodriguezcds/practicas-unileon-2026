"""Punto de entrada del indexador: el bucle que coge documentos pendientes y los procesa.

Para qué: corre siempre en segundo plano (contenedor `indexador`, `CMD ["python", "main.py"]`).
Cada vuelta coge un documento de la cola (cola.py) y lo procesa (procesar.py); si no hay nada,
duerme `INDEXADOR_ESPERA_S` segundos.

No muere por causas pasajeras, porque arranca a la vez que el resto:
  - si falta la tabla `indexado` (la API aplica la migración 005 al arrancar y aún no lo ha
    hecho), lo avisa en el log y reintenta a los ESPERA_FALLO_S segundos;
  - si la bbdd no responde, cierra la conexión, espera y vuelve a conectar.
Con la configuración incompleta (faltan POSTGRES_*) sí se para, con un error claro: eso no se
arregla esperando.

Quién lo usa: el Dockerfile. `bucle` recibe sus piezas como parámetros para los tests.
"""

import logging
import os
import time

import cola
import psycopg
from config import leer_config
from procesar import procesar as procesar_documento

ESPERA_FALLO_S = 10

log = logging.getLogger("indexador")


def bucle(env, conectar=psycopg.connect, coger=cola.coger, procesar=procesar_documento,
          dormir=time.sleep, vueltas: int | None = None) -> None:
    """Coge y procesa documentos sin fin (o `vueltas` veces, en los tests)."""
    cfg = leer_config(env)
    log.info("Indexador en marcha: Docling en %s, embeddings con %s en %s",
             cfg.docling_url, cfg.embeddings_modelo, cfg.ollama_url)
    conn = None
    n = 0
    while vueltas is None or n < vueltas:
        n += 1
        try:
            if conn is None or conn.closed:
                conn = conectar(cfg.db_dsn)
            doc = coger(conn, cfg)
            if doc is None:
                dormir(cfg.espera_s)
                continue
            procesar(conn, doc, cfg)
        except psycopg.errors.UndefinedTable:
            log.warning("Falta la tabla «indexado»: la API aún no ha aplicado la migración 005. "
                        "Reintento en %s s", ESPERA_FALLO_S)
            conn.rollback()
            dormir(ESPERA_FALLO_S)
        except psycopg.OperationalError as e:
            log.warning("La bbdd no responde (%s). Reintento en %s s", e, ESPERA_FALLO_S)
            if conn is not None:
                conn.close()
            conn = None
            dormir(ESPERA_FALLO_S)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    bucle(os.environ)
