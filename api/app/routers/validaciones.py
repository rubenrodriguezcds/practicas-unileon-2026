"""Validaciones de contenido por proyecto: crear, editar, borrar y listar (con su último resultado).

Para qué: el director de proyectos define qué tiene que aparecer en la documentación de un proyecto
(«las VLAN», «la tabla de rutas»…) para darlo por completo, y ve cuáles se cumplen. Diseño en
docs/superpowers/specs/2026-11-27-validaciones-design.md.

Contrato (la sección «Validación» de la ficha depende de él):
  GET    /api/proyectos/{id}/validaciones   → 200 [validación] en orden · 404 proyecto
  POST   /api/proyectos/{id}/validaciones   {"nombre","tipo","criterio"} → 201 validación · 404 · 422
  PUT    /api/validaciones/{id}             {"nombre","tipo","criterio"} → 200 validación (sin resultado) · 404 · 422
  DELETE /api/validaciones/{id}             → 204 · 404
  POST   /api/validaciones/{id}/ejecutar    → 200 validación con su resultado nuevo · 404
                                              (los fallos de Ollama van en el resultado, como «error»)
  validación = {"id","proyecto_id","nombre","tipo","criterio","orden","resultado"}
  resultado  = null (sin validar) o {"estado": "ok"|"falla"|"error","explicacion","resumen","ejecutada",
               "pruebas": [{"documento_id","documento","paginas","texto"}]}
               `pruebas`: un patrón, el primer trozo de cada documento donde aparece; la IA, los
               trozos que cita. `resumen`: resumen corto de la IA de lo encontrado, en las que se
               cumplen (null si no se cumple o si la IA no estaba disponible).
  En todos: 401 sin sesión · 403 si no es administrador · 503 bbdd caída.

Decisiones:
  - `tipo` es "patron" (expresión regular de Postgres sobre el texto de los trozos) o "ia" (una
    pregunta que responde un modelo de lenguaje). Un patrón que Postgres no acepta da 422 con su
    mensaje, al crear y al editar: así no se descubre al validar.
  - Editar una validación borra su resultado: ya no corresponde a lo que se comprueba.
  - Ejecutar un patrón busca en los trozos de los documentos YA indexados del proyecto. Si no
    aparece y quedan documentos sin indexar, la explicación lo avisa: ese ❌ aún no es definitivo.
    Un patrón que falla al ejecutarse queda en «error» con el motivo (no es «no cumple»).
    Si se cumple, la IA escribe un resumen corto con los trozos donde aparece (para el desplegable).
    El ✅/❌ lo decide SOLO el patrón: si la IA falla, el patrón sigue cumpliendo, sin resumen.
  - Ejecutar una de IA: se buscan los 5 trozos del proyecto más parecidos a la pregunta (la
    búsqueda híbrida del buscador) y se le pasan al modelo los que pasan `VALIDACION_UMBRAL` (o que
    coinciden por palabras). El modelo responde en JSON {cumple, trozos, explicacion, resumen}
    (llm.py): los números de TODOS los trozos que lo demuestran y un resumen corto para el desplegable.
    Reglas para que no apruebe sin pruebas: si ningún trozo pasa el umbral, ❌ sin preguntarle;
    «sí» sin citar ningún trozo válido, ❌; las pruebas guardadas son los trozos reales que cita.
    Ollama caído o una respuesta con otra forma → «error» con el motivo.
  - Solo el administrador, como el resto de pantallas de proyectos.

Quién lo usa: main.py lo registra; usa db.py, deps.py, embeddings.py y llm.py.
"""

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, StringConstraints

from app import db, embeddings, llm
from app.db import get_conn
from app.deps import require_admin

# Dos routers (bajo /api/proyectos y bajo /api/validaciones), los dos solo para administrador.
proyectos_router = APIRouter(prefix="/api/proyectos", dependencies=[Depends(require_admin)])
router = APIRouter(prefix="/api/validaciones", dependencies=[Depends(require_admin)])

PROYECTO_NO_EXISTE = "El proyecto no existe"
NO_EXISTE = "La validación no existe"


class ValidacionIn(BaseModel):
    """Cuerpo de POST y PUT. 422 si falta algo, el tipo no es uno de los dos o el texto es demasiado largo."""

    nombre: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
    tipo: Literal["patron", "ia"]
    criterio: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=1000)]


def _comprobar_patron(conn, body: ValidacionIn) -> None:
    if body.tipo == "patron" and (motivo := db.patron_valido(conn, body.criterio)):
        raise HTTPException(422, f"El patrón no es una expresión regular válida: {motivo}")


@proyectos_router.get("/{proyecto_id}/validaciones")
def listar(proyecto_id: int, conn=Depends(get_conn)):
    """Validaciones del proyecto, con su último resultado y la prueba."""
    validaciones = db.list_validations(conn, proyecto_id)
    if validaciones is None:
        raise HTTPException(404, PROYECTO_NO_EXISTE)
    return validaciones


@proyectos_router.post("/{proyecto_id}/validaciones", status_code=201)
def crear(proyecto_id: int, body: ValidacionIn, conn=Depends(get_conn)):
    """Añade una validación al final de la lista del proyecto."""
    _comprobar_patron(conn, body)
    validacion = db.create_validation(conn, proyecto_id, body.nombre, body.tipo, body.criterio)
    if validacion is None:
        raise HTTPException(404, PROYECTO_NO_EXISTE)
    return validacion


@router.put("/{validacion_id}")
def editar(validacion_id: int, body: ValidacionIn, conn=Depends(get_conn)):
    """Cambia nombre, tipo o criterio; el resultado anterior se borra."""
    _comprobar_patron(conn, body)
    validacion = db.update_validation(conn, validacion_id, body.nombre, body.tipo, body.criterio)
    if validacion is None:
        raise HTTPException(404, NO_EXISTE)
    return validacion


@router.delete("/{validacion_id}", status_code=204)
def borrar(validacion_id: int, conn=Depends(get_conn)):
    if not db.delete_validation(conn, validacion_id):
        raise HTTPException(404, NO_EXISTE)
    return Response(status_code=204)


def _plural(n: int, singular: str, plural: str) -> str:
    return f"{n} {singular if n == 1 else plural}"


def explicar_patron(b: dict) -> tuple[str, str]:
    """(estado, explicación) a partir de lo que devuelve db.run_pattern."""
    if b["trozos"]:
        return "ok", (f"Aparece en {_plural(b['trozos'], 'trozo', 'trozos')} de "
                      f"{_plural(b['documentos'], 'documento', 'documentos')}")
    texto = ("El proyecto no tiene documentos indexados" if not b["indexados"]
             else "No aparece en ningún documento del proyecto")
    return "falla", texto + _aviso_pendientes(b["pendientes"])


def _aviso_pendientes(n: int) -> str:
    """Un ❌ con documentos aún sin indexar no es definitivo: se avisa."""
    if not n:
        return ""
    return (f" ({_plural(n, 'documento aún no está indexado', 'documentos aún no están indexados')}:"
            " vuelve a validar cuando termine)")


TROZOS_IA = 5
SISTEMA_IA = (
    "Eres un revisor de documentación técnica. Te dan una pregunta sobre un proyecto y unos fragmentos "
    "numerados de sus documentos. Decide si los fragmentos muestran que la respuesta es SÍ, usando SOLO "
    "lo que dicen los fragmentos. Responde en JSON: «cumple» (true o false); «trozos» (la lista con los "
    "números de TODOS los fragmentos que lo demuestran, vacía si ninguno); «explicacion» (una frase en "
    "español); y «resumen» (dos o tres frases cortas: qué se ha encontrado y en qué documentos, citando "
    "los documentos por su NOMBRE y nunca por el número del fragmento; vacío si no se cumple). Si ningún "
    "fragmento lo muestra claramente, cumple es false y trozos está vacía."
)
ESQUEMA_IA = {
    "type": "object",
    "properties": {"cumple": {"type": "boolean"}, "trozos": {"type": "array", "items": {"type": "integer"}},
                   "explicacion": {"type": "string"}, "resumen": {"type": "string"}},
    "required": ["cumple", "trozos", "explicacion", "resumen"],
}
FORMATO_RARO = "La IA no respondió en el formato esperado"


def _lugar(t: dict) -> str:
    """«diseño_red.pdf · pág. 3» (Word no tiene páginas fijas: solo el nombre)."""
    if not t["paginas"]:
        return t["documento"]
    return f"{t['documento']} · {'pág.' if len(t['paginas']) == 1 else 'págs.'} {', '.join(map(str, t['paginas']))}"


SISTEMA_RESUMEN = (
    "Eres un revisor de documentación técnica. Te dan el nombre de una comprobación que se ha cumplido y "
    "los fragmentos de los documentos donde aparece. Escribe en JSON «resumen»: dos o tres frases cortas "
    "en español con lo que se ha encontrado y en qué documentos, citándolos por su NOMBRE y nunca por "
    "un número, usando SOLO lo que dicen los fragmentos."
)
ESQUEMA_RESUMEN = {"type": "object", "properties": {"resumen": {"type": "string"}}, "required": ["resumen"]}
TROZOS_RESUMEN = 5  # basta para resumir; menos que leer = antes (sin GPU, leer es lo lento)


def resumir_patron(conn, v: dict, pruebas: list[int], s) -> str | None:
    """Resumen corto de la IA de dónde aparece un patrón que se cumple; None si la IA falla o no dice nada."""
    trozos = db.get_fragments(conn, pruebas[:TROZOS_RESUMEN])
    if not trozos:
        return None
    fragmentos = "\n\n".join(f"{_lugar(t)}\n{t['texto']}" for t in trozos)
    mensajes = [{"role": "system", "content": SISTEMA_RESUMEN},
                {"role": "user", "content": f"Comprobación: {v['nombre']}\n\nFragmentos:\n\n{fragmentos}"}]
    try:
        resumen = llm.chat_json(s.ollama_url, s.chat_modelo, mensajes, ESQUEMA_RESUMEN).get("resumen")
    except llm.LLMError:
        return None  # sin resumen; el ✅ del patrón no depende de la IA
    if not isinstance(resumen, str):
        return None
    return resumen.strip() or None


def validar_con_ia(conn, v: dict, s) -> tuple[str, str, list[int], str | None]:
    """(estado, explicación, fragmento_id de las pruebas, resumen) de una validación de IA."""
    cuentas = db.document_counts(conn, v["proyecto_id"])
    aviso = _aviso_pendientes(cuentas["pendientes"])
    if not cuentas["indexados"]:
        return "falla", "El proyecto no tiene documentos indexados" + aviso, [], None
    try:
        vector = embeddings.vectorizar_pregunta(v["criterio"], s.ollama_url, s.embeddings_modelo)
    except embeddings.EmbeddingsError as e:
        return "error", str(e), [], None
    trozos = [t for t in db.search_fragments(conn, vector, v["criterio"], v["proyecto_id"], TROZOS_IA)
              if (t["puntuacion_vector"] or 0) >= s.validacion_umbral or t["puntuacion_texto"] is not None]
    if not trozos:
        return "falla", "No aparece en ningún documento del proyecto (ningún trozo se parece lo suficiente)" + aviso, [], None
    fragmentos = "\n\n".join(f"[{i}] {_lugar(t)}\n{t['texto']}" for i, t in enumerate(trozos, 1))
    mensajes = [{"role": "system", "content": SISTEMA_IA},
                {"role": "user", "content": f"Fragmentos:\n\n{fragmentos}\n\nPregunta: {v['criterio']}"}]
    try:
        r = llm.chat_json(s.ollama_url, s.chat_modelo, mensajes, ESQUEMA_IA)
    except llm.LLMError as e:
        return "error", str(e), [], None
    cumple, citados, explicacion, resumen = (r.get(k) for k in ("cumple", "trozos", "explicacion", "resumen"))
    if not (isinstance(cumple, bool) and isinstance(citados, list) and isinstance(explicacion, str)
            and isinstance(resumen, str)
            and all(isinstance(n, int) and not isinstance(n, bool) for n in citados)):
        return "error", FORMATO_RARO, [], None
    if not cumple:
        return "falla", explicacion.strip() + aviso, [], None
    # Solo valen los números de trozos que se le pasaron; en su orden y sin repetir.
    pruebas = list(dict.fromkeys(trozos[n - 1]["fragmento_id"] for n in citados if 1 <= n <= len(trozos)))
    if not pruebas:
        return "falla", "La IA dijo que sí, pero no indicó en qué trozo lo encontró", [], None
    return "ok", explicacion.strip(), pruebas, resumen.strip() or None


@router.post("/{validacion_id}/ejecutar")
def ejecutar(validacion_id: int, request: Request, conn=Depends(get_conn)):
    """Comprueba la validación contra los documentos del proyecto y guarda el resultado."""
    v = db.get_validation(conn, validacion_id)
    if v is None:
        raise HTTPException(404, NO_EXISTE)
    if v["tipo"] == "ia":
        estado, explicacion, pruebas, resumen = validar_con_ia(conn, v, request.app.state.settings)
        db.save_result(conn, validacion_id, estado, explicacion, pruebas, resumen)
        return db.get_validation(conn, validacion_id)
    try:
        estado, explicacion = explicar_patron(b := db.run_pattern(conn, v["proyecto_id"], v["criterio"]))
        pruebas = b["fragmentos"] if estado == "ok" else []
    except db.PatronNoValido as e:
        estado, explicacion, pruebas = "error", f"El patrón no es una expresión regular válida: {e}", []
    resumen = resumir_patron(conn, v, pruebas, request.app.state.settings) if estado == "ok" else None
    db.save_result(conn, validacion_id, estado, explicacion, pruebas, resumen)
    return db.get_validation(conn, validacion_id)
