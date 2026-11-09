"""Captcha ALTCHA: comprueba que quien envía el login o el reseteo no es un bot.

Para qué: el navegador pide un reto (`new_challenge`), resuelve un pequeño cálculo (prueba de
trabajo, ~1 s) y lo envía junto con el formulario; `verify` comprueba la solución.

Por qué ALTCHA: es open source y lo servimos nosotros. No necesita cuentas en Google ni en
Cloudflare, no rastrea al usuario ni pide aceptar cookies. Solo necesita ALTCHA_HMAC_KEY, la
clave con la que la API firma los retos (quien la conozca podría fabricarlos).

Quién lo usa: routers/captcha.py (entrega retos) y routers/auth.py (login y reseteo).

Notas:
  - Los retos caducan a los 5 minutos (va dentro de la firma, no se puede alargar).
  - Un reto vale UNA vez: su firma se apunta en `captchas_usados` y un reenvío se rechaza. Así
    un bot no puede resolver un reto y reutilizarlo en mil intentos.
  - ALTCHA_ENABLED=false desactiva la comprobación (main.py lo avisa en el log). Los retos se
    siguen entregando para que el widget del navegador funcione igual.
"""

import base64
import json
import time

import altcha
from fastapi import HTTPException

from app import db
from app.config import Settings

CHALLENGE_TTL = 300  # segundos
ALGORITHM = "PBKDF2/SHA-256"
INVALID = "Verificación anti-bot no válida"


def new_challenge(s: Settings) -> dict:
    """Crea un reto firmado que caduca en CHALLENGE_TTL segundos (formato del widget ALTCHA)."""
    key = s.altcha_hmac_key or "captcha-desactivado"  # sin captcha la firma no se comprueba
    return altcha.create_challenge(
        ALGORITHM, s.altcha_cost, hmac_secret=key, expires_at=int(time.time()) + CHALLENGE_TTL
    ).to_dict()


def verify(s: Settings, conn, payload: str | None) -> None:
    """Comprueba la solución del captcha y la marca como usada.

    Raises:
        HTTPException: 400 si falta, es inválida, ha caducado o ya se usó.
    """
    if not s.altcha_enabled:
        return
    if not payload or not altcha.verify_solution(payload, s.altcha_hmac_key).verified:
        raise HTTPException(400, INVALID)
    # verify_solution ya ha validado el formato, la firma y la caducidad
    challenge = json.loads(base64.b64decode(payload))["challenge"]
    if not db.mark_captcha_used(conn, challenge["signature"], challenge["parameters"]["expiresAt"]):
        raise HTTPException(400, INVALID)
