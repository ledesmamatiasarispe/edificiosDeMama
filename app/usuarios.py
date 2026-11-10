"""Usuarios del sistema: alta, rol, baja y contraseñas.

Reglas que evitan quedarse afuera: siempre queda al menos un administrador activo, nadie se da de baja a sí mismo,
y la baja o el cambio de contraseña cierran las sesiones abiertas de esa persona. Una contraseña puesta por un
administrador (alta o restablecer) es provisoria: el usuario la tiene que cambiar al entrar.
"""
import sqlite3

from .auth import hash_password, verificar_password
from .db import transaccion
from .validar import ErrorDeNegocio, NoEncontrado, texto

MINIMO_PASSWORD = 6
_COLS = "id, usuario, nombre, es_admin, activo, debe_cambiar"


def _password_valida(password) -> str:
    p = str(password or "")
    if len(p) < MINIMO_PASSWORD:
        raise ErrorDeNegocio(f"La contraseña tiene que tener al menos {MINIMO_PASSWORD} caracteres.")
    return p


def _usuario(c, uid: int) -> sqlite3.Row:
    u = c.execute(f"SELECT {_COLS} FROM usuarios WHERE id=?", (uid,)).fetchone()
    if not u:
        raise NoEncontrado("No existe ese usuario.")
    return u


def _exigir_otro_admin(c, uid: int, accion: str) -> None:
    otros = c.execute("SELECT count(*) FROM usuarios WHERE es_admin=1 AND activo=1 AND id<>?", (uid,)).fetchone()[0]
    if not otros:
        raise ErrorDeNegocio(f"No se puede {accion}: es el único administrador activo. Primero hay que nombrar otro administrador.")


def _cerrar_sesiones(c, uid: int, excepto_token: str | None = None) -> None:
    c.execute("UPDATE sesiones SET activa=0 WHERE usuario_id=? AND token IS NOT ?", (uid, excepto_token))


def listar() -> list[dict]:
    with transaccion() as c:
        return [dict(r) for r in c.execute(f"SELECT {_COLS} FROM usuarios ORDER BY activo DESC, es_admin DESC, nombre")]


def crear(admin: dict, *, usuario, nombre, password, es_admin=False) -> dict:
    usuario = texto(usuario, "el nombre de usuario").lower()
    if " " in usuario:
        raise ErrorDeNegocio("El nombre de usuario va sin espacios.")
    nombre = texto(nombre, "el nombre")
    salt, h = hash_password(_password_valida(password))
    with transaccion() as c:
        if c.execute("SELECT 1 FROM usuarios WHERE usuario=?", (usuario,)).fetchone():
            raise ErrorDeNegocio(f"Ya existe el usuario '{usuario}'.")
        cur = c.execute("INSERT INTO usuarios (usuario, nombre, password_hash, salt, es_admin, debe_cambiar) VALUES (?,?,?,?,?,1)",
                        (usuario, nombre, h, salt, int(bool(es_admin))))
        return dict(_usuario(c, cur.lastrowid))


def actualizar(admin: dict, uid: int, *, nombre, es_admin) -> dict:
    nombre = texto(nombre, "el nombre")
    with transaccion() as c:
        u = _usuario(c, uid)
        if u["es_admin"] and not es_admin:
            _exigir_otro_admin(c, uid, "quitarle el rol de administrador")
        c.execute("UPDATE usuarios SET nombre=?, es_admin=? WHERE id=?", (nombre, int(bool(es_admin)), uid))
        return dict(_usuario(c, uid))


def cambiar_alta(admin: dict, uid: int, *, activo: bool) -> dict:
    """Dar de baja no borra al usuario: solo le impide entrar."""
    with transaccion() as c:
        u = _usuario(c, uid)
        if not activo:
            if uid == admin["id"]:
                raise ErrorDeNegocio("No podés darte de baja a vos mismo: lo tiene que hacer otro administrador.")
            if u["es_admin"]:
                _exigir_otro_admin(c, uid, "darlo de baja")
            _cerrar_sesiones(c, uid)
        c.execute("UPDATE usuarios SET activo=? WHERE id=?", (int(activo), uid))
        return dict(_usuario(c, uid))


def restablecer_password(admin: dict, uid: int, *, password) -> dict:
    if uid == admin["id"]:
        raise ErrorDeNegocio("Para tu propia contraseña usá \"Cambiar contraseña\".")
    salt, h = hash_password(_password_valida(password))
    with transaccion() as c:
        _usuario(c, uid)
        c.execute("UPDATE usuarios SET password_hash=?, salt=?, debe_cambiar=1 WHERE id=?", (h, salt, uid))
        _cerrar_sesiones(c, uid)
        return dict(_usuario(c, uid))


def cambiar_password(usuario: dict, *, actual, nueva) -> None:
    nueva = _password_valida(nueva)
    with transaccion() as c:
        u = c.execute("SELECT password_hash, salt FROM usuarios WHERE id=?", (usuario["id"],)).fetchone()
        if not verificar_password(str(actual or ""), u["salt"], u["password_hash"]):
            raise ErrorDeNegocio("La contraseña actual no es correcta.")
        if verificar_password(nueva, u["salt"], u["password_hash"]):
            raise ErrorDeNegocio("La contraseña nueva tiene que ser distinta de la actual.")
        salt, h = hash_password(nueva)
        c.execute("UPDATE usuarios SET password_hash=?, salt=?, debe_cambiar=0 WHERE id=?", (h, salt, usuario["id"]))
        _cerrar_sesiones(c, usuario["id"], excepto_token=usuario["token"])
