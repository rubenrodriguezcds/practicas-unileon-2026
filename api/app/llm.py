"""Pedir al modelo de lenguaje de Ollama una respuesta en JSON con un esquema fijo.

Para qué: cuando el programa tiene que USAR la respuesta del modelo (no solo enseñarla), hace falta
que llegue con una forma conocida, p. ej. {"cumple": true, "trozo": 2, "explicacion": "…"}. Ollama
lo garantiza con `format`: el modelo solo puede generar JSON que cumple el esquema dado.

Genérico a propósito: lo usan las validaciones con IA (routers/validaciones.py) y lo puede usar
cualquier otra pieza que necesite una respuesta estructurada (p. ej. el chat de la fase 2).

Opciones fijas, como en resumen.py: sin streaming, sin «pensar» (`think: false`, que en CPU tarda
mucho y no hace falta), temperatura 0 (la misma pregunta da la misma respuesta), `num_ctx` 8192 (el
valor por defecto de Ollama, 4096, recortaría los trozos sin avisar) y `keep_alive` 30 min (cargar el
modelo en frío cuesta ~70 s sin GPU).

Errores: `LLMNoDisponible` si Ollama no responde y `LLMError` si responde con error o con algo que no
es un objeto JSON.
"""

import json

import httpx

TIEMPO_MAX_S = 300  # con el modelo cargado, segundos; en frío y sin GPU, más de un minuto


class LLMError(Exception):
    """Ollama respondió con un error o con algo que no es el JSON pedido."""


class LLMNoDisponible(LLMError):
    """Ollama no responde."""


def chat_json(url: str, modelo: str, mensajes: list[dict], esquema: dict, cliente: httpx.Client | None = None) -> dict:
    """Respuesta del modelo a `mensajes`, ya convertida en un dict que sigue `esquema`. `cliente`, solo en tests."""
    if cliente is None:
        with httpx.Client(timeout=TIEMPO_MAX_S) as propio:
            return chat_json(url, modelo, mensajes, esquema, propio)
    cuerpo = {"model": modelo, "messages": mensajes, "format": esquema, "stream": False, "think": False,
              "keep_alive": "30m", "options": {"temperature": 0, "num_ctx": 8192}}
    try:
        r = cliente.post(f"{url}/api/chat", json=cuerpo)
    except httpx.HTTPError as e:
        raise LLMNoDisponible(f"Ollama no responde en {url} ({type(e).__name__})") from None
    if r.status_code != 200:
        try:
            motivo = r.json().get("error") or r.text[:300]
        except ValueError:
            motivo = r.text[:300]
        raise LLMError(f"Ollama respondió {r.status_code}: {motivo}")
    try:
        datos = json.loads(r.json()["message"]["content"])
    except (ValueError, KeyError, TypeError):
        datos = None
    if not isinstance(datos, dict):
        raise LLMError("La IA no respondió en el formato esperado")
    return datos
