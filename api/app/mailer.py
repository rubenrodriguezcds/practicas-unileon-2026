"""Envío de correo por SMTP (o al log, en desarrollo).

Para qué: mandar la contraseña nueva del reseteo al email del usuario.

Por qué existe: concentra el correo en un sitio. Usa `smtplib`, de la librería estándar (sin
dependencias), y todo se configura en el `.env`: cambiar de proveedor (Gmail, Outlook, el
servidor de la empresa) es cambiar SMTP_HOST/PORT/USER/PASSWORD/FROM/TLS, sin tocar código.

Quién lo usa: routers/auth.py (reseteo de contraseña).

Notas:
  - SMTP_TLS: `starttls` (puerto 587; Gmail y Outlook), `ssl` (puerto 465) o `none` (servidores
    internos sin cifrado). Con cifrado se verifica el certificado del servidor.
  - Timeout (SMTP_TIMEOUT): un servidor que no responde no deja la petición colgada.
  - Modo log: sin SMTP_HOST, el correo se escribe en el log (`docker compose logs web`) con la
    contraseña EN CLARO. Solo para desarrollo.
  - Los errores (smtplib.SMTPException u OSError) se propagan: decide quien llama.
"""

import logging
import smtplib
import ssl
from email.message import EmailMessage

from app.config import Settings

logger = logging.getLogger(__name__)


def send_mail(s: Settings, to: str, subject: str, body: str) -> None:
    """Envía un correo de texto plano a `to` con la configuración SMTP de `s`.

    Raises:
        smtplib.SMTPException, OSError: si el servidor rechaza el correo o no responde.
    """
    if not s.smtp_host:
        logger.warning("Correo en modo log (sin SMTP_HOST, solo desarrollo) para %s: %s\n%s", to, subject, body)
        return

    msg = EmailMessage()
    msg["From"], msg["To"], msg["Subject"] = s.smtp_from, to, subject
    msg.set_content(body)

    if s.smtp_tls == "ssl":
        smtp = smtplib.SMTP_SSL(s.smtp_host, s.smtp_port, timeout=s.smtp_timeout, context=ssl.create_default_context())
    else:
        smtp = smtplib.SMTP(s.smtp_host, s.smtp_port, timeout=s.smtp_timeout)
    with smtp:
        if s.smtp_tls == "starttls":
            smtp.starttls(context=ssl.create_default_context())
        if s.smtp_user:
            smtp.login(s.smtp_user, s.smtp_password)
        smtp.send_message(msg)
