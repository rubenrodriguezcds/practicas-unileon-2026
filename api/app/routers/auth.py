from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field

from app.db import find_password_hash, get_conn
from app.security import verify_password

router = APIRouter(prefix="/api/auth")


class LoginIn(BaseModel):
    username: str = Field(min_length=1)
    password: str = Field(min_length=1)


@router.post("/login")
def login(body: LoginIn, request: Request, conn=Depends(get_conn)):
    hashed = find_password_hash(conn, body.username)
    # mismo mensaje para usuario inexistente y contraseña mala
    if hashed is None or not verify_password(body.password, hashed):
        raise HTTPException(401, "Usuario o contraseña incorrectos")
    request.session["username"] = body.username
    return {"username": body.username}


@router.post("/logout", status_code=204)
def logout(request: Request):
    request.session.clear()
    return Response(status_code=204)


@router.get("/me")
def me(request: Request):
    username = request.session.get("username")
    if not username:
        raise HTTPException(401, "No autenticado")
    return {"username": username}
