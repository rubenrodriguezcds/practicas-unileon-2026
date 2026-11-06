"""Tests del aplicador de migraciones (migrations.py) sin Postgres.

Para qué: comprobar que solo se aplican las migraciones pendientes, en orden y una vez, y que
el email del admin se rellena sin pisar uno que ya exista. Además, que la migración de la
issue #4 es idempotente (IF NOT EXISTS), como exigen las reglas del proyecto.

Cómo: una conexión de mentira que apunta el SQL ejecutado y simula la tabla de control.
"""

from contextlib import nullcontext

from app.migrations import MIGRATIONS_DIR, apply_migrations


class FakeConn:
    def __init__(self, done=()):
        self.done = list(done)
        self.sql = []

    def execute(self, sql, params=None):
        self.sql.append((sql, params))
        if sql.startswith("INSERT INTO migraciones_aplicadas"):
            self.done.append(params[0])
        return self

    def fetchall(self):
        return [(n,) for n in self.done]

    def transaction(self):
        return nullcontext()


def write(tmp_path, *names):
    for n in names:
        (tmp_path / n).write_text(f"-- {n}", encoding="utf-8")
    return tmp_path


def test_aplica_las_pendientes_en_orden(tmp_path):
    d = write(tmp_path, "002_b.sql", "001_a.sql")
    conn = FakeConn()
    assert apply_migrations(conn, None, d) == ["001_a.sql", "002_b.sql"]
    assert apply_migrations(conn, None, d) == []  # la segunda vez no hay nada que hacer


def test_salta_las_ya_aplicadas(tmp_path):
    d = write(tmp_path, "001_a.sql", "002_b.sql")
    conn = FakeConn(done=["001_a.sql"])
    assert apply_migrations(conn, None, d) == ["002_b.sql"]
    assert ("-- 001_a.sql", None) not in conn.sql


def test_email_del_admin_solo_si_esta_vacio(tmp_path):
    conn = FakeConn()
    apply_migrations(conn, "admin@example.com", tmp_path)
    sql, params = conn.sql[-1]
    assert "email IS NULL" in sql and params == ("admin@example.com",)


def test_sin_email_del_admin_no_toca_usuarios(tmp_path):
    conn = FakeConn()
    apply_migrations(conn, None, tmp_path)
    assert not any("UPDATE usuarios" in s for s, _ in conn.sql)


def test_migracion_001_es_idempotente():
    sql = (MIGRATIONS_DIR / "001_reseteo_y_captcha.sql").read_text(encoding="utf-8")
    statements = [s.strip() for s in sql.split(";") if s.strip() and not s.strip().startswith("--")]
    for s in statements:
        code = "\n".join(line for line in s.splitlines() if not line.strip().startswith("--"))
        assert "IF NOT EXISTS" in code, code
