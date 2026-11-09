"""Test de /api/health, el endpoint de «estoy vivo».

Para qué: comprobar que la app arranca y responde. Sirve también como prueba rápida tras
desplegar (`curl localhost/api/health`) porque no depende de la base de datos.
"""

def test_health_ok(client):
    """/api/health responde 200 con status ok sin necesitar la bbdd."""
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}
