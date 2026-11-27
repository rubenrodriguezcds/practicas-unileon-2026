"""Cola de documentos por indexar, en la propia Postgres.

Para qué: elegir el siguiente documento que hay que indexar y apuntar cómo acaba.

Por qué en Postgres y no en RabbitMQ/Kafka: el estado se deriva. Un documento sin fila en
`indexado` está pendiente, así que la subida no cambia y ningún documento puede quedarse fuera
de la cola (con un broker aparte, guardar el documento y publicar el mensaje son dos pasos y
el segundo puede perderse). El volumen es pequeño y no añade contenedores.

Cómo: `FOR UPDATE OF d SKIP LOCKED` bloquea el documento elegido y hace que otro indexador
se lo salte, así que se pueden lanzar varios sin que procesen el mismo. Al cogerlo se apunta
«procesando» y se confirma enseguida: el trabajo largo (Docling, embeddings) va fuera de la
transacción y no deja bloqueos abiertos.

Reintentos: un «error» vuelve a cogerse mientras `intentos < max_intentos`, esperando
`intentos` minutos (si Docling u Ollama están caídos no se gastan los tres intentos en segundos).
Un «procesando» de más de `colgado_min` minutos se da por colgado (el indexador murió a mitad).

Quién lo usa: main.py (coger), procesar.py (marcar_error) y guardar.py (marcar_hecho).
"""

from psycopg.types.json import Jsonb

_COLGADOS_SIN_INTENTOS = """
UPDATE indexado SET estado = 'error', actualizado = now(),
       error = 'Se quedó a medias demasiadas veces (¿documento demasiado grande?)'
WHERE estado = 'procesando' AND actualizado < now() - make_interval(mins => %(colgado)s)
  AND intentos >= %(max)s
"""

_ELEGIR = """
SELECT d.id, d.proyecto_id, d.nombre, d.contenido
FROM documentos d LEFT JOIN indexado i ON i.documento_id = d.id
WHERE i.documento_id IS NULL
   OR (i.estado = 'error' AND i.intentos < %(max)s
       AND i.actualizado < now() - make_interval(mins => i.intentos))
   OR (i.estado = 'procesando' AND i.intentos < %(max)s
       AND i.actualizado < now() - make_interval(mins => %(colgado)s))
ORDER BY d.id
LIMIT 1
FOR UPDATE OF d SKIP LOCKED
"""

_APUNTAR = """
INSERT INTO indexado (documento_id, estado, intentos) VALUES (%s, 'procesando', 1)
ON CONFLICT (documento_id) DO UPDATE
SET estado = 'procesando', intentos = indexado.intentos + 1, error = NULL, actualizado = now()
"""


def coger(conn, cfg) -> dict | None:
    """Siguiente documento por indexar, ya apuntado como «procesando»; None si no hay ninguno.

    Devuelve {id, proyecto_id, nombre, contenido (bytes)}. Confirma su propia transacción.
    """
    params = {"max": cfg.max_intentos, "colgado": cfg.colgado_min}
    conn.execute(_COLGADOS_SIN_INTENTOS, params)
    # binary=True: sin él, Postgres manda el contenido en hexadecimal (el doble de bytes).
    row = conn.execute(_ELEGIR, params, binary=True).fetchone()
    if row is None:
        conn.commit()
        return None
    conn.execute(_APUNTAR, (row[0],))
    conn.commit()
    return {"id": row[0], "proyecto_id": row[1], "nombre": row[2], "contenido": bytes(row[3])}


def marcar_hecho(conn, documento_id: int, docling_json: dict | None, version: str | None) -> None:
    """Apunta el documento como indexado. NO confirma: va en la transacción de guardar.py."""
    conn.execute(
        "UPDATE indexado SET estado = 'hecho', error = NULL, docling_json = %s, docling_version = %s,"
        " actualizado = now() WHERE documento_id = %s",
        (Jsonb(docling_json) if docling_json is not None else None, version, documento_id),
    )


def marcar_error(conn, documento_id: int, motivo: str) -> None:
    """Apunta el fallo con su motivo (lo que verá la ficha del proyecto) y confirma."""
    conn.rollback()  # por si la transacción quedó rota por el fallo
    conn.execute(
        "UPDATE indexado SET estado = 'error', error = %s, actualizado = now() WHERE documento_id = %s",
        (motivo[:1000], documento_id),
    )
    conn.commit()
