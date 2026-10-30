"""Sirve el frontend React compilado (la «SPA») desde la propia API.

Para qué: que un único contenedor (`web`, puerto 80) entregue tanto la API (/api/*) como la
página web (index.html, JS y CSS que genera `npm run build`).

Por qué existe: React gestiona sus rutas en el navegador (/login, /…). Si el usuario recarga
en /login, el servidor recibe esa ruta y no existe ningún fichero con ese nombre: hay que
devolver index.html para que React la resuelva. Sin esto, recargar daría un 404.

Quién lo usa: main.py, solo si está definida la variable STATIC_DIR (la pone el Dockerfile).
Sin STATIC_DIR la API funciona sola: es lo que permitirá separar frontend (nginx) y API en
contenedores distintos sin cambiar código.

Notas: las rutas /api/* que no existen devuelven 404 en JSON (no index.html), y se comprueba
que ninguna ruta pueda salirse de la carpeta de estáticos (path traversal).
"""

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles


def mount_spa(app: FastAPI, static_dir: str) -> None:
    """Sirve la SPA compilada desde static_dir.

    Monta /assets y añade un catch-all que devuelve el fichero pedido o, si no
    existe, index.html (para que recargar en rutas del cliente funcione).
    Debe llamarse después de registrar los routers de /api.
    """
    root = Path(static_dir).resolve()
    app.mount("/assets", StaticFiles(directory=root / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str):
        """Catch-all de la SPA.

        Raises:
            HTTPException: 404 para rutas /api/* inexistentes, que no deben
                caer en index.html.
        """
        if path == "api" or path.startswith("api/"):
            raise HTTPException(404, "Not Found")
        f = (root / path).resolve()
        # is_relative_to evita salir de static_dir con ../
        if f.is_file() and f.is_relative_to(root):
            return FileResponse(f)
        return FileResponse(root / "index.html")
