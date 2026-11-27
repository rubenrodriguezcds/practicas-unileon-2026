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

  GET /api/busqueda/resumen?q=<pregunta>&proyecto_id=<opcional>
    → 200 {"resumen": str | null, "fuentes": n, "encontrado": bool}: párrafo de IA que cita
      [1]…[n], los n primeros resultados de la misma búsqueda (los de arriba de la página);
      `encontrado` es false si el modelo dice que la respuesta no está (la página pliega entonces
      los resultados). Sin resultados: resumen null y encontrado false, sin llamar al modelo. Va aparte de la búsqueda para que los resultados salgan al instante y el
      resumen (segundos) llegue después.
    · mismos 401/403/422 · 503/502 si falla Ollama (embeddings o modelo de chat)

Solo el administrador, como el resto de pantallas de proyectos: aún no hay permisos por proyecto,
y la búsqueda devuelve texto de cualquier documento.

Quién lo usa: main.py lo registra; usa embeddings.py, resumen.py, db.py y deps.py.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from app import db, embeddings, resumen
from app.db import get_conn
from app.deps import require_admin

router = APIRouter(prefix="/api/busqueda", dependencies=[Depends(require_admin)])

PREGUNTA_MAX = 500
TROZOS_RESUMEN = 4  # menos trozos = menos que leer para el modelo = resumen antes (sin GPU, leer es lo lento)


def _buscar(request: Request, q: str, proyecto_id: int | None, conn, k: int = 10) -> tuple[str, list[dict]]:
    """Pregunta limpia y sus `k` trozos más parecidos; 422/503/502 como dice el contrato."""
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
    return pregunta, db.search_fragments(conn, vector, pregunta, proyecto_id, k)


@router.get("")
def buscar(request: Request,
           q: Annotated[str, Query(max_length=PREGUNTA_MAX)],
           proyecto_id: int | None = None,
           conn=Depends(get_conn)):
    """Trozos más parecidos a la pregunta `q`, opcionalmente solo de un proyecto."""
    return _buscar(request, q, proyecto_id, conn)[1]


@router.get("/resumen")
def resumir(request: Request,
            q: Annotated[str, Query(max_length=PREGUNTA_MAX)],
            proyecto_id: int | None = None,
            conn=Depends(get_conn)):
    """Resumen con IA de los primeros trozos de la búsqueda, citando [1]…[n]."""
    pregunta, trozos = _buscar(request, q, proyecto_id, conn, TROZOS_RESUMEN)
    if not trozos:
        return {"resumen": None, "fuentes": 0, "encontrado": False}
    s = request.app.state.settings
    try:
        texto = resumen.resumir(pregunta, trozos, s.ollama_url, s.chat_modelo)
    except resumen.ResumenNoDisponible as e:
        raise HTTPException(503, f"El resumen no está disponible: {e}") from None
    except resumen.ResumenError as e:
        raise HTTPException(502, str(e)) from None
    return {"resumen": texto, "fuentes": len(trozos), "encontrado": resumen.encontrado(texto)}
