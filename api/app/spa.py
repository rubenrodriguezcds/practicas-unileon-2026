from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles


def mount_spa(app: FastAPI, static_dir: str) -> None:
    root = Path(static_dir).resolve()
    app.mount("/assets", StaticFiles(directory=root / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str):
        if path == "api" or path.startswith("api/"):
            raise HTTPException(404, "Not Found")
        f = (root / path).resolve()
        # is_relative_to evita salir de static_dir con ../
        if f.is_file() and f.is_relative_to(root):
            return FileResponse(f)
        return FileResponse(root / "index.html")
