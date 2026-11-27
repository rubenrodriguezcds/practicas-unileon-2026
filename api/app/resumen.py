"""Resumen con IA del buscador: un párrafo que responde a la pregunta citando los trozos encontrados.

Para qué: encima de los resultados del buscador, como el resumen de un buscador web. Es la base del
chat de la fase 2 (misma idea: buscar los trozos y que el modelo responda solo con ellos).

Cómo: los trozos van numerados en el prompt ([1], [2]…, en el orden en que la página los pinta) y el
modelo cita con esos números. Guardrail: responder SOLO con los fragmentos y, si no está, decir
«No lo encuentro en los documentos» (probado con gemma4:e2b: no se inventa la respuesta).

Opciones fijas: sin streaming (el texto llega entero); `num_ctx` 8192 porque el valor por defecto de
Ollama (4096) se queda corto con varios trozos y los recortaría sin avisar; `keep_alive` 30 min para
que el modelo no se descargue entre búsquedas (cargarlo en frío cuesta ~70 s sin GPU); temperatura
baja para que no adorne.

`encontrado(texto)` dice si el modelo encontró la respuesta: la página pliega los resultados cuando
no, porque el buscador siempre devuelve los más parecidos aunque ninguno lo sea (con trozos cortos,
la puntuación de parecido no basta para separar los irrelevantes; el modelo, que los lee, sí).

Errores: `ResumenNoDisponible` si Ollama no responde (→ 503) y `ResumenError` si responde con error,
p. ej. el modelo no está descargado (→ 502).

Quién lo usa: routers/busqueda.py.
"""

import httpx

TIEMPO_MAX_S = 300  # con el modelo cargado ~7-25 s; en frío y sin GPU, más de un minuto
NO_ENCONTRADO = "No lo encuentro en los documentos"
SISTEMA = (
    "Eres el asistente de un gestor documental. Responde en español, en pocas frases, usando "
    "SOLO la información de los fragmentos. Después de cada dato pon la cita entre corchetes con "
    "el número del fragmento, por ejemplo [1]. Si la respuesta no está en los fragmentos, "
    f"responde exactamente: «{NO_ENCONTRADO}.»"
)


class ResumenError(Exception):
    """Ollama respondió con un error."""


class ResumenNoDisponible(ResumenError):
    """Ollama no responde."""


def resumir(pregunta: str, trozos: list[dict], url: str, modelo: str, cliente: httpx.Client | None = None) -> str:
    """Respuesta del modelo a `pregunta` usando solo `trozos` (los del buscador). `cliente`, solo en tests."""
    if cliente is None:
        with httpx.Client(timeout=TIEMPO_MAX_S) as propio:
            return resumir(pregunta, trozos, url, modelo, propio)
    fragmentos = "\n\n".join(
        f"[{i}] Documento: {t['documento']}, página {', '.join(map(str, t['paginas'])) or '-'}\n{t['texto']}"
        for i, t in enumerate(trozos, 1)
    )
    cuerpo = {
        "model": modelo, "stream": False, "think": False, "keep_alive": "30m",
        "options": {"num_ctx": 8192, "temperature": 0.2},
        "messages": [{"role": "system", "content": SISTEMA},
                     {"role": "user", "content": f"Fragmentos:\n\n{fragmentos}\n\nPregunta: {pregunta}"}],
    }
    try:
        r = cliente.post(f"{url}/api/chat", json=cuerpo)
    except httpx.HTTPError as e:
        raise ResumenNoDisponible(f"Ollama no responde en {url} ({type(e).__name__})") from None
    if r.status_code != 200:
        try:
            motivo = r.json().get("error") or r.text[:300]
        except ValueError:
            motivo = r.text[:300]
        raise ResumenError(f"Ollama respondió {r.status_code}: {motivo}")
    return r.json()["message"]["content"].strip()


def encontrado(texto: str) -> bool:
    """False si el modelo respondió que la respuesta no está en los fragmentos."""
    return NO_ENCONTRADO.lower() not in texto.lower()
