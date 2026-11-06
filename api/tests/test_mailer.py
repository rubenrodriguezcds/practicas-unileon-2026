"""Tests del envío de correo (mailer.py) sin servidor real.

Para qué: comprobar que cada modo de SMTP_TLS habla con el servidor como debe (Gmail y Outlook
exigen STARTTLS en el 587), que siempre hay timeout y que sin SMTP_HOST el correo va al log.

Cómo: `smtplib.SMTP` y `smtplib.SMTP_SSL` se sustituyen por un doble que apunta las llamadas.
"""

import logging

import pytest

from app import mailer
from tests.factories import make_settings


class FakeSMTP:
    """Imita smtplib.SMTP/SMTP_SSL y guarda lo que se le pide en `calls`."""

    calls = []

    def __init__(self, host, port, timeout, context=None):
        FakeSMTP.calls.append(("connect", host, port, timeout, context is not None))

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        FakeSMTP.calls.append(("quit",))

    def starttls(self, context):
        FakeSMTP.calls.append(("starttls",))

    def login(self, user, password):
        FakeSMTP.calls.append(("login", user, password))

    def send_message(self, msg):
        FakeSMTP.calls.append(("send", msg["From"], msg["To"], msg["Subject"], msg.get_content().strip()))


@pytest.fixture(autouse=True)
def fake_smtp(monkeypatch):
    FakeSMTP.calls = []
    monkeypatch.setattr(mailer.smtplib, "SMTP", FakeSMTP)
    monkeypatch.setattr(mailer.smtplib, "SMTP_SSL", FakeSMTP)


def send(**settings):
    mailer.send_mail(make_settings(**settings), "ana@example.com", "Asunto", "Cuerpo")


def test_starttls_por_defecto_con_login_y_timeout():
    send(smtp_host="smtp.gmail.com", smtp_user="u", smtp_password="p", smtp_from="app@example.com", smtp_timeout=7)
    assert FakeSMTP.calls == [
        ("connect", "smtp.gmail.com", 587, 7, False),
        ("starttls",),
        ("login", "u", "p"),
        ("send", "app@example.com", "ana@example.com", "Asunto", "Cuerpo"),
        ("quit",),
    ]


def test_ssl_cifra_desde_la_conexion():
    send(smtp_host="smtp.example.com", smtp_port=465, smtp_tls="ssl")
    assert FakeSMTP.calls[0] == ("connect", "smtp.example.com", 465, 10, True)
    assert ("starttls",) not in FakeSMTP.calls


def test_none_sin_cifrado_ni_login():
    send(smtp_host="mail.interno", smtp_port=25, smtp_tls="none")
    assert [c[0] for c in FakeSMTP.calls] == ["connect", "send", "quit"]


def test_sin_smtp_host_va_al_log(caplog):
    with caplog.at_level(logging.WARNING):
        send(smtp_host="")
    assert FakeSMTP.calls == []
    assert "modo log" in caplog.text and "ana@example.com" in caplog.text and "Cuerpo" in caplog.text
