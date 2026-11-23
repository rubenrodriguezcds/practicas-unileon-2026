"""Tests del bucle principal (main.py) con la bbdd, la cola y el procesado sustituidos.

Se fija que el indexador no muere: sin la tabla `indexado` (la API aún no aplicó la migración
005) o con la bbdd caída espera 10 s y reintenta; sin trabajo duerme `espera_s`.
"""

import psycopg
import pytest
from main import ESPERA_FALLO_S, bucle

ENV = {"POSTGRES_DB": "gestor", "POSTGRES_USER": "app", "POSTGRES_PASSWORD": "x"}


class Escena:
    """Lo que devuelve `coger` en cada vuelta: un documento, None (sin trabajo) o una excepción."""

    def __init__(self, *pasos):
        self.pasos = list(pasos)
        self.esperas, self.procesados, self.conexiones = [], [], 0

    def conectar(self, dsn):
        self.conexiones += 1
        return FalsaConexion()

    def coger(self, conn, cfg):
        paso = self.pasos.pop(0)
        if isinstance(paso, Exception):
            raise paso
        return paso

    def procesar(self, conn, doc, cfg):
        self.procesados.append(doc["id"])
        return "hecho"

    def dormir(self, s):
        self.esperas.append(s)

    def lanzar(self):
        bucle(ENV, conectar=self.conectar, coger=self.coger, procesar=self.procesar, dormir=self.dormir,
              vueltas=len(self.pasos))


class FalsaConexion:
    closed = False

    def rollback(self):
        pass

    def close(self):
        self.closed = True


def test_procesa_lo_que_hay_y_duerme_cuando_no_hay_trabajo():
    e = Escena({"id": 1}, {"id": 2}, None)
    e.lanzar()
    assert e.procesados == [1, 2]
    assert e.esperas == [5]
    assert e.conexiones == 1  # la conexión se reutiliza entre vueltas


def test_sin_la_tabla_indexado_avisa_espera_y_reintenta(caplog):
    e = Escena(psycopg.errors.UndefinedTable("no existe la relación «indexado»"), {"id": 1})
    e.lanzar()
    assert e.esperas == [ESPERA_FALLO_S]
    assert e.procesados == [1]
    assert "migración 005" in caplog.text


def test_bbdd_caida_reconecta_tras_esperar(caplog):
    e = Escena(psycopg.OperationalError("connection refused"), {"id": 1})
    e.lanzar()
    assert e.esperas == [ESPERA_FALLO_S]
    assert e.conexiones == 2
    assert e.procesados == [1]
    assert "bbdd no responde" in caplog.text


def test_config_incompleta_no_arranca():
    from config import ConfigError
    with pytest.raises(ConfigError, match="POSTGRES_PASSWORD"):
        bucle({"POSTGRES_DB": "gestor", "POSTGRES_USER": "app"}, vueltas=1)
