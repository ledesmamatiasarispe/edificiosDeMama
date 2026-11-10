"""Login por nombre de usuario con token Bearer y sesiones en la base.

La contraseña se guarda con PBKDF2 (estándar de la librería), nunca en texto.
"""
import hashlib
import hmac
import secrets
from datetime import datetime, timedelta
from typing import Optional

from fastapi import Depends, Header, HTTPException

from .db import transaccion

HORAS_SESION = 12
_ITERACIONES = 200_000


def hash_password(password: str, salt: str | None = None) -> tuple[str, str]:
    salt = salt or secrets.token_hex(16)
    h = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), _ITERACIONES).hex()
    return salt, h


def verificar_password(password: str, salt: str, guardado: str) -> bool:
    return hmac.compare_digest(hash_password(password, salt)[1], guardado)


def login(usuario: str, password: str) -> dict:
    with transaccion() as c:
        u = c.execute("SELECT id, usuario, nombre, password_hash, salt, es_admin, debe_cambiar FROM usuarios "
                      "WHERE usuario=? AND activo=1", (str(usuario or "").strip(),)).fetchone()
        if not u or not verificar_password(password, u["salt"], u["password_hash"]):
            raise HTTPException(401, "Usuario o contraseña incorrectos")
        token = secrets.token_hex(32)
        vence = (datetime.now() + timedelta(hours=HORAS_SESION)).isoformat()
        c.execute("INSERT INTO sesiones (token, usuario_id, vence_en) VALUES (?,?,?)", (token, u["id"], vence))
    return {"token": token, "usuario": {"id": u["id"], "usuario": u["usuario"], "nombre": u["nombre"],
                                        "es_admin": bool(u["es_admin"]), "debe_cambiar": bool(u["debe_cambiar"])}}


def logout(token: str) -> None:
    with transaccion() as c:
        c.execute("UPDATE sesiones SET activa=0 WHERE token=?", (token,))


def _token(authorization: Optional[str]) -> str:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "Hay que iniciar sesión")
    return authorization.split(" ", 1)[1].strip()


def sesion(authorization: Optional[str] = Header(None)) -> dict:
    """La sesión, aunque tenga pendiente cambiar la contraseña: solo para ver quién es, cambiarla o salir."""
    token = _token(authorization)
    with transaccion() as c:
        u = c.execute("SELECT u.id, u.usuario, u.nombre, u.es_admin, u.debe_cambiar FROM sesiones s JOIN usuarios u ON u.id = s.usuario_id "
                      "WHERE s.token=? AND s.activa=1 AND s.vence_en>? AND u.activo=1",
                      (token, datetime.now().isoformat())).fetchone()
    if not u:
        raise HTTPException(401, "La sesión venció: iniciar sesión de nuevo")
    return {"id": u["id"], "usuario": u["usuario"], "nombre": u["nombre"], "es_admin": bool(u["es_admin"]),
            "debe_cambiar": bool(u["debe_cambiar"]), "token": token}


def usuario_actual(usuario: dict = Depends(sesion)) -> dict:
    """Para todo lo demás: con una contraseña provisoria no se hace nada hasta cambiarla."""
    if usuario["debe_cambiar"]:
        raise HTTPException(403, "Antes de seguir hay que cambiar la contraseña provisoria")
    return usuario


def solo_admin(usuario: dict = Depends(usuario_actual)) -> dict:
    """Manejar usuarios es solo de administradores."""
    if not usuario["es_admin"]:
        raise HTTPException(403, "Solo un administrador puede hacer esto")
    return usuario
