"""Buscador de prueba del asistente: GET /api/busqueda.

Para qué: escribir una pregunta y ver los trozos de documentos que más se le parecen, con sus
puntuaciones. Es la forma de comprobar que el indexado sirve (fase 1) y la base del chat (fase 2).

Cómo: la pregunta se convierte en vector (app/embeddings.py, bge-m3 en Ollama) y la bbdd hace una
búsqueda híbrida, por significado y por palabras, combinadas con RRF (db.search_fragments).

Contrato (la página «Buscador» depende de él):
  GET /api/busqueda?q=<pregunta>&proyecto_id=<opcional>
    → 200 [{"documento_id","documento","proyecto_id","proyecto","titulos","paginas","texto",
            "puntuacion_vector","puntuacion_texto","puntuacion"}], de más a menos parecido (máx. 10)
    · 401 sin sesión · 403 si no es administrador
    · 422 pregunta vacía, de más de 500 caracteres, o proyecto_id no numérico
    · 503 Ollama no responde · 502 Ollama responde con error (p. ej. modelo no descargado)

Solo el administrador, como el resto de pantallas de proyectos: aún no hay permisos por proyecto,
y la búsqueda devuelve texto de cualquier documento.

Quién lo usa: main.py lo registra; usa embeddings.py, db.py y deps.py.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from app import db, embeddings
from app.db import get_conn
from app.deps import require_admin

router = APIRouter(prefix="/api/busqueda", dependencies=[Depends(require_admin)])

PREGUNTA_MAX = 500


@router.get("")
def buscar(request: Request,
           q: Annotated[str, Query(max_length=PREGUNTA_MAX)],
           proyecto_id: int | None = None,
           conn=Depends(get_conn)):
    """Trozos más parecidos a la pregunta `q`, opcionalmente solo de un proyecto."""
    pregunta = q.strip()
    if not pregunta:
        raise HTTPException(422, "Escribe una pregunta")
    s = request.app.state.settings
    try:
        vector = embeddings.vectorizar_pregunta(pregunta, s.ollama_url, s.embeddings_modelo)
    except embeddings.OllamaNoDisponible as e:
        raise HTTPException(503, f"El buscador no está disponible: {e}") from None
    except embeddings.EmbeddingsError as e:
        raise HTTPException(502, str(e)) from None
    return db.search_fragments(conn, vector, pregunta, proyecto_id)
