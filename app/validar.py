"""Validaciones de campo y errores de negocio, compartidos por todos los módulos de servicios."""
import math
import sqlite3
from datetime import date, datetime


class ErrorDeNegocio(Exception):
    """Lo que el usuario cargó no se puede aceptar; el mensaje se le muestra tal cual."""


class NoEncontrado(Exception):
    pass


def texto(valor, campo: str, obligatorio: bool = True) -> str:
    t = str(valor or "").strip()
    if obligatorio and not t:
        raise ErrorDeNegocio(f"Falta {campo}.")
    return t


def fecha(valor, campo: str, obligatorio: bool = True) -> str | None:
    if valor in (None, ""):
        if obligatorio:
            raise ErrorDeNegocio(f"Falta {campo}.")
        return None
    try:
        return date.fromisoformat(str(valor)[:10]).isoformat()
    except ValueError:
        raise ErrorDeNegocio(f"{campo.capitalize()}: '{valor}' no es una fecha.")


def periodo(valor, campo: str = "el mes") -> str:
    """'2026-10' (año-mes)."""
    t = texto(valor, campo)[:7]
    try:
        date.fromisoformat(t + "-01")
    except ValueError:
        raise ErrorDeNegocio(f"{campo.capitalize()}: '{valor}' no es un mes válido.")
    return t


def numero(valor, campo: str, entero: bool = False, minimo: float = 0, maximo: float = 1e9):
    if valor in (None, ""):
        return None
    try:
        n = float(str(valor).replace(",", "."))
    except ValueError:
        n = None
    if n is None or not math.isfinite(n):
        raise ErrorDeNegocio(f"{campo.capitalize()}: '{valor}' no es un número.")
    if not minimo <= n <= maximo:
        raise ErrorDeNegocio(f"{campo.capitalize()} tiene que estar entre {minimo:g} y {maximo:g}.")
    if entero:
        if n != int(n):
            raise ErrorDeNegocio(f"{campo.capitalize()} tiene que ser un número entero.")
        return int(n)
    return n


def pesos(valor, campo: str, obligatorio: bool = True) -> int | None:
    """Importe en pesos escrito por una persona ('12.500,50', '12500.5', '12500') -> centavos (entero).

    Con coma, la coma es el decimal y los puntos son de miles. Sin coma, un punto seguido de 3 cifras es de miles."""
    t = str(valor if valor is not None else "").strip().replace("$", "").replace(" ", "")
    if not t:
        if obligatorio:
            raise ErrorDeNegocio(f"Falta {campo}.")
        return None
    if "," in t:
        t = t.replace(".", "").replace(",", ".")
    elif t.count(".") > 1 or (t.count(".") == 1 and len(t.split(".")[1]) == 3):
        t = t.replace(".", "")
    try:
        n = float(t)
    except ValueError:
        raise ErrorDeNegocio(f"{campo.capitalize()}: '{valor}' no es un importe.")
    if not math.isfinite(n) or n <= 0 or n > 1e11:
        raise ErrorDeNegocio(f"{campo.capitalize()} tiene que ser mayor que cero.")
    return int(round(n * 100))


def opcion(valor, opciones, campo: str) -> str:
    if valor not in opciones:
        raise ErrorDeNegocio(f"{campo.capitalize()}: elegir una de {', '.join(opciones)}.")
    return valor


def ahora() -> str:
    return datetime.now().isoformat(timespec="seconds")


def fila(c: sqlite3.Connection, sql: str, params: tuple, que: str) -> sqlite3.Row:
    r = c.execute(sql, params).fetchone()
    if not r:
        raise NoEncontrado(f"No existe {que}.")
    return r
