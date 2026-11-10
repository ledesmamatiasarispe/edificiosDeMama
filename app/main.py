"""API y archivos de la pantalla. Rutas delgadas: leen el pedido, llaman a los servicios y devuelven el resultado.

Los cuerpos llegan como dict y se pasan crudos: la validación está en servicios/expensas, así un "7,5" o una
fecha mal escrita termina en un mensaje claro (400) y no en un error interno.
"""
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Body, Depends, FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from . import auth, expensas as ex, servicios as sv, usuarios
from .db import inicializar
from .validar import ErrorDeNegocio, NoEncontrado

FRONTEND = Path(__file__).resolve().parent.parent / "frontend"
VERSION = "0.2.0"


@asynccontextmanager
async def _inicio(_app):
    inicializar()
    yield


app = FastAPI(title="Edificios de Mamá", lifespan=_inicio)
app.mount("/static", StaticFiles(directory=FRONTEND), name="static")

Usuario = Depends(auth.usuario_actual)
Admin = Depends(auth.solo_admin)
Sesion = Depends(auth.sesion)


@app.exception_handler(ErrorDeNegocio)
async def _error_negocio(_req: Request, e: ErrorDeNegocio):
    return JSONResponse({"detail": str(e)}, status_code=400)


@app.exception_handler(NoEncontrado)
async def _no_encontrado(_req: Request, e: NoEncontrado):
    return JSONResponse({"detail": str(e)}, status_code=404)


@app.get("/", include_in_schema=False)
def pantalla():
    html = (FRONTEND / "index.html").read_text(encoding="utf-8")
    for ext in (".js", ".css"):
        html = html.replace(f'{ext}"', f'{ext}?v={VERSION}"')
    return HTMLResponse(html, headers={"Cache-Control": "no-cache"})


# ── sesión ──
@app.post("/api/auth/login")
def login(body: dict = Body(...)):
    return auth.login(str(body.get("usuario", "")), str(body.get("password", "")))


@app.post("/api/auth/logout")
def logout(u: dict = Sesion):
    auth.logout(u["token"])
    return {"ok": True}


@app.get("/api/auth/yo")
def yo(u: dict = Sesion):
    return {k: u[k] for k in ("id", "usuario", "nombre", "es_admin", "debe_cambiar")}


@app.post("/api/auth/password")
def cambiar_mi_password(body: dict = Body(...), u: dict = Sesion):
    usuarios.cambiar_password(u, actual=body.get("actual"), nueva=body.get("nueva"))
    return {"ok": True}


# ── usuarios (solo administradores) ──
@app.get("/api/usuarios")
def listar_usuarios(u: dict = Admin):
    return usuarios.listar()


@app.post("/api/usuarios")
def crear_usuario(body: dict = Body(...), u: dict = Admin):
    return usuarios.crear(u, **{k: body.get(k) for k in ("usuario", "nombre", "password", "es_admin")})


@app.put("/api/usuarios/{uid}")
def actualizar_usuario(uid: int, body: dict = Body(...), u: dict = Admin):
    return usuarios.actualizar(u, uid, nombre=body.get("nombre"), es_admin=bool(body.get("es_admin")))


@app.post("/api/usuarios/{uid}/{accion}")
def alta_baja_usuario(uid: int, accion: str, body: dict = Body(None), u: dict = Admin):
    if accion == "password":
        return usuarios.restablecer_password(u, uid, password=(body or {}).get("password"))
    if accion not in ("alta", "baja"):
        raise NoEncontrado("Acción desconocida.")
    return usuarios.cambiar_alta(u, uid, activo=accion == "alta")


# ── inicio ──
@app.get("/api/resumen")
def resumen(u: dict = Usuario):
    return ex.resumen()


# ── consorcios ──
@app.get("/api/consorcios")
def listar_consorcios(u: dict = Usuario):
    return sv.listar_consorcios()


@app.post("/api/consorcios")
def crear_consorcio(body: dict = Body(...), u: dict = Usuario):
    return sv.crear_consorcio(body)


@app.get("/api/consorcios/{cid}")
def ver_consorcio(cid: int, u: dict = Usuario):
    return sv.ver_consorcio(cid)


@app.put("/api/consorcios/{cid}")
def actualizar_consorcio(cid: int, body: dict = Body(...), u: dict = Usuario):
    return sv.actualizar_consorcio(cid, body)


@app.put("/api/consorcios/{cid}/grupos")
def guardar_grupos(cid: int, body: list = Body(...), u: dict = Usuario):
    return sv.guardar_grupos(cid, body)


@app.post("/api/consorcios/{cid}/alta")
@app.post("/api/consorcios/{cid}/baja")
def alta_baja_consorcio(cid: int, request: Request, u: dict = Usuario):
    accion = request.url.path.rsplit("/", 1)[1]
    return sv.cambiar_alta_consorcio(cid, accion == "alta")


# ── unidades ──
@app.get("/api/consorcios/{cid}/unidades")
def listar_unidades(cid: int, u: dict = Usuario):
    return {"unidades": sv.listar_unidades(cid), "control": sv.control_porcentajes(cid)}


@app.post("/api/consorcios/{cid}/unidades")
def crear_unidad(cid: int, body: dict = Body(...), u: dict = Usuario):
    return {"id": sv.crear_unidad(cid, body)}


@app.put("/api/unidades/{uid}")
def actualizar_unidad(uid: int, body: dict = Body(...), u: dict = Usuario):
    sv.actualizar_unidad(uid, body)
    return {"ok": True}


@app.post("/api/unidades/{uid}/alta")
@app.post("/api/unidades/{uid}/baja")
def alta_baja_unidad(uid: int, request: Request, u: dict = Usuario):
    accion = request.url.path.rsplit("/", 1)[1]
    sv.cambiar_alta_unidad(uid, accion == "alta")
    return {"ok": True}


@app.post("/api/unidades/{uid}/personas")
def vincular(uid: int, body: dict = Body(...), u: dict = Usuario):
    sv.vincular(uid, body.get("persona_id"), body.get("rol"))
    return {"ok": True}


@app.delete("/api/unidades/{uid}/personas/{pid}/{rol}")
def desvincular(uid: int, pid: int, rol: str, u: dict = Usuario):
    sv.desvincular(uid, pid, rol)
    return {"ok": True}


@app.get("/api/unidades/{uid}/cuenta")
def cuenta_corriente(uid: int, u: dict = Usuario):
    return ex.cuenta_corriente(uid)


@app.post("/api/unidades/{uid}/pagos")
def registrar_pago(uid: int, body: dict = Body(...), u: dict = Usuario):
    return ex.registrar_pago(u, uid, body)


# ── personas ──
@app.get("/api/personas")
def listar_personas(consorcio: int | None = None, u: dict = Usuario):
    return sv.listar_personas(consorcio)


@app.post("/api/personas")
def crear_persona(body: dict = Body(...), u: dict = Usuario):
    return sv.crear_persona(body)


@app.put("/api/personas/{pid}")
def actualizar_persona(pid: int, body: dict = Body(...), u: dict = Usuario):
    return sv.actualizar_persona(pid, body)


# ── proveedores ──
@app.get("/api/proveedores")
def listar_proveedores(u: dict = Usuario):
    return sv.listar_proveedores()


@app.post("/api/proveedores")
def crear_proveedor(body: dict = Body(...), u: dict = Usuario):
    return sv.guardar_proveedor(None, body)


@app.put("/api/proveedores/{pid}")
def actualizar_proveedor(pid: int, body: dict = Body(...), u: dict = Usuario):
    return sv.guardar_proveedor(pid, body)


@app.post("/api/proveedores/{pid}/alta")
@app.post("/api/proveedores/{pid}/baja")
def alta_baja_proveedor(pid: int, request: Request, u: dict = Usuario):
    accion = request.url.path.rsplit("/", 1)[1]
    sv.cambiar_alta_proveedor(pid, accion == "alta")
    return {"ok": True}


# ── gastos fijos ──
@app.get("/api/consorcios/{cid}/gastos-fijos")
def listar_gastos_fijos(cid: int, u: dict = Usuario):
    return sv.listar_gastos_fijos(cid)


@app.post("/api/consorcios/{cid}/gastos-fijos")
def crear_gasto_fijo(cid: int, body: dict = Body(...), u: dict = Usuario):
    sv.guardar_gasto_fijo(cid, None, body)
    return {"ok": True}


@app.put("/api/consorcios/{cid}/gastos-fijos/{gid}")
def actualizar_gasto_fijo(cid: int, gid: int, body: dict = Body(...), u: dict = Usuario):
    sv.guardar_gasto_fijo(cid, gid, body)
    return {"ok": True}


@app.post("/api/gastos-fijos/{gid}/alta")
@app.post("/api/gastos-fijos/{gid}/baja")
def alta_baja_gasto_fijo(gid: int, request: Request, u: dict = Usuario):
    accion = request.url.path.rsplit("/", 1)[1]
    sv.cambiar_alta_gasto_fijo(gid, accion == "alta")
    return {"ok": True}


# ── liquidaciones y gastos ──
@app.get("/api/consorcios/{cid}/liquidaciones")
def listar_liquidaciones(cid: int, u: dict = Usuario):
    return ex.listar_liquidaciones(cid)


@app.post("/api/consorcios/{cid}/liquidaciones")
def abrir_liquidacion(cid: int, body: dict = Body(...), u: dict = Usuario):
    return ex.abrir_liquidacion(cid, body)


@app.get("/api/liquidaciones/{lid}")
def ver_liquidacion(lid: int, u: dict = Usuario):
    return ex.ver_liquidacion(lid)


@app.post("/api/liquidaciones/{lid}/cerrar")
def cerrar_liquidacion(lid: int, body: dict = Body(None), u: dict = Usuario):
    return ex.cerrar_liquidacion(lid, body or {})


@app.post("/api/liquidaciones/{lid}/reabrir")
def reabrir_liquidacion(lid: int, u: dict = Usuario):
    return ex.reabrir_liquidacion(lid)


@app.delete("/api/liquidaciones/{lid}")
def borrar_liquidacion(lid: int, u: dict = Usuario):
    ex.borrar_liquidacion(lid)
    return {"ok": True}


@app.post("/api/liquidaciones/{lid}/gastos")
def crear_gasto(lid: int, body: dict = Body(...), u: dict = Usuario):
    return ex.guardar_gasto(lid, None, body)


@app.put("/api/liquidaciones/{lid}/gastos/{gid}")
def actualizar_gasto(lid: int, gid: int, body: dict = Body(...), u: dict = Usuario):
    return ex.guardar_gasto(lid, gid, body)


@app.delete("/api/gastos/{gid}")
def borrar_gasto(gid: int, u: dict = Usuario):
    return ex.borrar_gasto(gid)


# ── cobros, saldos y morosos ──
@app.get("/api/consorcios/{cid}/pagos")
def listar_pagos(cid: int, desde: str | None = None, hasta: str | None = None, u: dict = Usuario):
    return ex.listar_pagos(cid, desde, hasta)


@app.get("/api/pagos/{pid}")
def ver_recibo(pid: int, u: dict = Usuario):
    return ex.recibo(pid)


@app.post("/api/pagos/{pid}/anular")
def anular_pago(pid: int, u: dict = Usuario):
    return ex.anular_pago(pid)


@app.get("/api/consorcios/{cid}/saldos")
def saldos(cid: int, u: dict = Usuario):
    return ex.saldos(cid)


@app.get("/api/morosos")
def morosos(consorcio: int | None = None, u: dict = Usuario):
    return ex.morosos(consorcio)


def _accion(request: Request) -> bool:
    """Para las rutas .../alta y .../baja: True si es alta."""
    return request.url.path.rsplit("/", 1)[1] == "alta"


# ── administración y rubros ──
@app.get("/api/administracion")
def ver_administracion(u: dict = Usuario):
    return sv.ver_administracion()


@app.put("/api/administracion")
def guardar_administracion(body: dict = Body(...), u: dict = Usuario):
    return sv.guardar_administracion(body)


@app.get("/api/rubros")
def listar_rubros(u: dict = Usuario):
    return sv.listar_rubros()


@app.post("/api/rubros")
def crear_rubro(body: dict = Body(...), u: dict = Usuario):
    return sv.guardar_rubro(None, body)


@app.put("/api/rubros/{rid}")
def actualizar_rubro(rid: int, body: dict = Body(...), u: dict = Usuario):
    return sv.guardar_rubro(rid, body)


@app.post("/api/rubros/{rid}/alta")
@app.post("/api/rubros/{rid}/baja")
def alta_baja_rubro(rid: int, request: Request, u: dict = Usuario):
    sv.cambiar_alta_rubro(rid, _accion(request))
    return {"ok": True}


# ── encargados y sus conceptos de sueldo fijos ──
@app.get("/api/consorcios/{cid}/encargados")
def listar_encargados(cid: int, u: dict = Usuario):
    return sv.listar_encargados(cid)


@app.post("/api/consorcios/{cid}/encargados")
def crear_encargado(cid: int, body: dict = Body(...), u: dict = Usuario):
    sv.guardar_encargado(cid, None, body)
    return {"ok": True}


@app.put("/api/consorcios/{cid}/encargados/{eid}")
def actualizar_encargado(cid: int, eid: int, body: dict = Body(...), u: dict = Usuario):
    sv.guardar_encargado(cid, eid, body)
    return {"ok": True}


@app.post("/api/encargados/{eid}/alta")
@app.post("/api/encargados/{eid}/baja")
def alta_baja_encargado(eid: int, request: Request, u: dict = Usuario):
    sv.cambiar_alta_encargado(eid, _accion(request))
    return {"ok": True}


@app.post("/api/encargados/{eid}/sueldos-fijos")
def crear_sueldo_fijo(eid: int, body: dict = Body(...), u: dict = Usuario):
    sv.guardar_sueldo_fijo(eid, None, body)
    return {"ok": True}


@app.put("/api/encargados/{eid}/sueldos-fijos/{sid}")
def actualizar_sueldo_fijo(eid: int, sid: int, body: dict = Body(...), u: dict = Usuario):
    sv.guardar_sueldo_fijo(eid, sid, body)
    return {"ok": True}


@app.post("/api/sueldos-fijos/{sid}/alta")
@app.post("/api/sueldos-fijos/{sid}/baja")
def alta_baja_sueldo_fijo(sid: int, request: Request, u: dict = Usuario):
    sv.cambiar_alta_sueldo_fijo(sid, _accion(request))
    return {"ok": True}


# ── juicios ──
@app.get("/api/consorcios/{cid}/juicios")
def listar_juicios(cid: int, u: dict = Usuario):
    return sv.listar_juicios(cid)


@app.post("/api/consorcios/{cid}/juicios")
def crear_juicio(cid: int, body: dict = Body(...), u: dict = Usuario):
    sv.guardar_juicio(cid, None, body)
    return {"ok": True}


@app.put("/api/consorcios/{cid}/juicios/{jid}")
def actualizar_juicio(cid: int, jid: int, body: dict = Body(...), u: dict = Usuario):
    sv.guardar_juicio(cid, jid, body)
    return {"ok": True}


@app.delete("/api/juicios/{jid}")
def borrar_juicio(jid: int, u: dict = Usuario):
    sv.borrar_juicio(jid)
    return {"ok": True}


# ── gastos particulares y sueldos de una liquidación ──
@app.post("/api/liquidaciones/{lid}/particulares")
def crear_particular(lid: int, body: dict = Body(...), u: dict = Usuario):
    return ex.guardar_particular(lid, None, body)


@app.put("/api/liquidaciones/{lid}/particulares/{gid}")
def actualizar_particular(lid: int, gid: int, body: dict = Body(...), u: dict = Usuario):
    return ex.guardar_particular(lid, gid, body)


@app.delete("/api/particulares/{gid}")
def borrar_particular(gid: int, u: dict = Usuario):
    return ex.borrar_particular(gid)


@app.post("/api/liquidaciones/{lid}/sueldos")
def crear_sueldo(lid: int, body: dict = Body(...), u: dict = Usuario):
    return ex.guardar_sueldo(lid, None, body)


@app.put("/api/liquidaciones/{lid}/sueldos/{sid}")
def actualizar_sueldo(lid: int, sid: int, body: dict = Body(...), u: dict = Usuario):
    return ex.guardar_sueldo(lid, sid, body)


@app.delete("/api/sueldos/{sid}")
def borrar_sueldo(sid: int, u: dict = Usuario):
    return ex.borrar_sueldo(sid)
