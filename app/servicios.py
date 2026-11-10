"""Casos de uso de la configuración: consorcios, grupos de gastos, unidades, personas, proveedores y gastos fijos.

Las rutas de main.py solo leen el pedido y llaman acá; ninguna valida ni escribe SQL por su cuenta.
Cada función es una transacción completa.
"""
from .db import GRUPOS, transaccion
from .validar import ErrorDeNegocio, fila, numero, opcion, pesos, texto

TIPOS_UNIDAD = ("vivienda", "local", "cochera", "baulera", "otro")
ROLES = ("propietario", "inquilino")


# ── consorcios ──────────────────────────────────────────────────────────────

CATEGORIAS = ("", "1", "2", "3", "4")
SUPERFICIES = ("porcentual", "absoluta")
TIPOS_INTERES = ("simple", "compuesto")
_CAMPOS_CONSORCIO = ("nombre", "direccion", "localidad", "cp", "cuit", "email", "interes_mora", "dia_vencimiento",
                     "nota_expensas", "clave_suterh", "categoria", "anio_construccion", "superficies", "tipo_interes",
                     "mostrar_inquilino", "envia_comprobantes", "imputa_a_deuda", "liquida_mes_vencido",
                     "caja_inicial", "banco_titular", "banco_nombre", "banco_sucursal", "banco_cuenta", "banco_cbu",
                     "banco_alias", "codigo_pago")


def _si_no(valor) -> int:
    return int(valor in (True, 1, "1", "si", "sí", "true", "on"))


def _datos_consorcio(d: dict) -> tuple:
    email = texto(d.get("email"), "el email para enviar y recibir respuestas de las expensas")
    if "@" not in email or "." not in email.split("@")[-1]:
        raise ErrorDeNegocio(f"El email '{email}' no parece válido.")
    return (texto(d.get("nombre"), "el nombre"), texto(d.get("direccion"), "la dirección"),
            texto(d.get("localidad"), "", False), texto(d.get("cp"), "", False), texto(d.get("cuit"), "", False),
            email,
            numero(d.get("interes_mora"), "el interés por mora", maximo=50) or 0,
            numero(d.get("dia_vencimiento"), "el día de vencimiento", entero=True, minimo=1, maximo=28) or 10,
            texto(d.get("nota_expensas"), "", False),
            texto(d.get("clave_suterh"), "", False),
            opcion(str(d.get("categoria") or ""), CATEGORIAS, "la categoría del edificio"),
            numero(d.get("anio_construccion"), "el año de construcción", entero=True, minimo=1800, maximo=2100),
            opcion(d.get("superficies") or "porcentual", SUPERFICIES, "la configuración de superficies"),
            opcion(d.get("tipo_interes") or "simple", TIPOS_INTERES, "el tipo de interés"),
            _si_no(d.get("mostrar_inquilino")), _si_no(d.get("envia_comprobantes")),
            _si_no(d.get("imputa_a_deuda", True)), _si_no(d.get("liquida_mes_vencido", True)),
            _pesos_con_signo(d.get("caja_inicial"), "la caja inicial"),
            *(texto(d.get(k), "", False) for k in ("banco_titular", "banco_nombre", "banco_sucursal", "banco_cuenta",
                                                   "banco_cbu", "banco_alias", "codigo_pago")))


def _pesos_con_signo(valor, campo: str) -> int:
    """Como pesos(), pero acepta cero y negativos (una caja puede arrancar en rojo)."""
    t = str(valor if valor is not None else "").strip()
    if t in ("", "0", "0,00", "0.00"):
        return 0
    negativo = t.startswith("-")
    return -pesos(t.lstrip("-"), campo) if negativo else pesos(t, campo)


def listar_consorcios() -> list[dict]:
    with transaccion() as c:
        return [dict(r) for r in c.execute(
            "SELECT co.*, (SELECT count(*) FROM unidades u WHERE u.consorcio_id=co.id AND u.activa=1) AS unidades "
            "FROM consorcios co ORDER BY co.activo DESC, co.nombre")]


def ver_consorcio(cid: int) -> dict:
    with transaccion() as c:
        co = dict(fila(c, "SELECT * FROM consorcios WHERE id=?", (cid,), "ese consorcio"))
        co["grupos"] = [dict(r) for r in c.execute(
            "SELECT letra, nombre FROM grupos_gasto WHERE consorcio_id=? ORDER BY letra", (cid,))]
        return co


def _sin_nombre_repetido(c, nombre: str, cid: int | None) -> None:
    if c.execute("SELECT 1 FROM consorcios WHERE nombre=? AND id IS NOT ?", (nombre, cid)).fetchone():
        raise ErrorDeNegocio(f"Ya existe un consorcio llamado '{nombre}'.")


def crear_consorcio(d: dict) -> dict:
    datos = _datos_consorcio(d)
    with transaccion() as c:
        _sin_nombre_repetido(c, datos[0], None)
        cid = c.execute(f"INSERT INTO consorcios ({', '.join(_CAMPOS_CONSORCIO)}) VALUES ({', '.join('?' * len(datos))})",
                        datos).lastrowid
        c.execute("INSERT INTO grupos_gasto VALUES (?, 'A', 'Gastos generales')", (cid,))
    return ver_consorcio(cid)


def actualizar_consorcio(cid: int, d: dict) -> dict:
    datos = _datos_consorcio(d)
    with transaccion() as c:
        fila(c, "SELECT id FROM consorcios WHERE id=?", (cid,), "ese consorcio")
        _sin_nombre_repetido(c, datos[0], cid)
        c.execute(f"UPDATE consorcios SET {', '.join(k + '=?' for k in _CAMPOS_CONSORCIO)} WHERE id=?", (*datos, cid))
    return ver_consorcio(cid)


def guardar_grupos(cid: int, grupos: list) -> dict:
    """Los grupos de gastos del consorcio: [{letra, nombre}]. El A siempre existe; uno con gastos no se puede quitar."""
    nuevos = {}
    for g in grupos or []:
        letra = opcion(str(g.get("letra", "")).upper(), GRUPOS, "la letra del grupo")
        nombre = texto(g.get("nombre"), f"el nombre del grupo {letra}", False)
        if nombre:
            nuevos[letra] = nombre
    if "A" not in nuevos:
        raise ErrorDeNegocio("El grupo A (gastos generales) tiene que tener nombre.")
    with transaccion() as c:
        fila(c, "SELECT id FROM consorcios WHERE id=?", (cid,), "ese consorcio")
        for (letra,) in c.execute("SELECT letra FROM grupos_gasto WHERE consorcio_id=?", (cid,)).fetchall():
            if letra in nuevos:
                continue
            usado = c.execute("SELECT 1 FROM gastos g JOIN liquidaciones l ON l.id=g.liquidacion_id WHERE l.consorcio_id=? AND g.letra=? "
                              "UNION SELECT 1 FROM gastos_fijos WHERE consorcio_id=? AND letra=? AND activo=1",
                              (cid, letra, cid, letra)).fetchone()
            if usado:
                raise ErrorDeNegocio(f"El grupo {letra} ya tiene gastos cargados: no se puede quitar.")
            c.execute("DELETE FROM grupos_gasto WHERE consorcio_id=? AND letra=?", (cid, letra))
            c.execute("DELETE FROM unidad_grupo WHERE letra=? AND unidad_id IN (SELECT id FROM unidades WHERE consorcio_id=?)", (letra, cid))
        for letra, nombre in nuevos.items():
            c.execute("INSERT INTO grupos_gasto VALUES (?,?,?) ON CONFLICT DO UPDATE SET nombre=excluded.nombre", (cid, letra, nombre))
    return ver_consorcio(cid)


def cambiar_alta_consorcio(cid: int, activo: bool) -> dict:
    with transaccion() as c:
        fila(c, "SELECT id FROM consorcios WHERE id=?", (cid,), "ese consorcio")
        c.execute("UPDATE consorcios SET activo=? WHERE id=?", (int(activo), cid))
    return ver_consorcio(cid)


# ── unidades ────────────────────────────────────────────────────────────────

def listar_unidades(cid: int) -> list[dict]:
    """Unidades con sus porcentajes por grupo y sus personas (propietarios e inquilinos)."""
    with transaccion() as c:
        fila(c, "SELECT id FROM consorcios WHERE id=?", (cid,), "ese consorcio")
        us = [dict(r) for r in c.execute("SELECT * FROM unidades WHERE consorcio_id=? ORDER BY activa DESC, id", (cid,))]
        for u in us:
            u["porcentajes"] = {r["letra"]: r["porcentaje"] for r in c.execute(
                "SELECT letra, porcentaje FROM unidad_grupo WHERE unidad_id=?", (u["id"],))}
            u["personas"] = [dict(r) for r in c.execute(
                "SELECT p.id, p.nombre, p.apellido, up.rol FROM unidad_personas up JOIN personas p ON p.id=up.persona_id "
                "WHERE up.unidad_id=? ORDER BY up.rol, p.apellido", (u["id"],))]
        return us


def _datos_unidad(c, cid: int, d: dict, uid: int | None) -> tuple:
    nombre = texto(d.get("nombre"), "el nombre de la unidad (ej. UF 3)")
    if c.execute("SELECT 1 FROM unidades WHERE consorcio_id=? AND nombre=? AND id IS NOT ?", (cid, nombre, uid)).fetchone():
        raise ErrorDeNegocio(f"Ya hay una unidad '{nombre}' en este consorcio.")
    return (nombre, texto(d.get("piso"), "", False), texto(d.get("depto"), "", False),
            opcion(d.get("tipo") or "vivienda", TIPOS_UNIDAD, "el tipo"))


def _guardar_porcentajes(c, cid: int, uid: int, porcentajes: dict) -> None:
    letras = {r[0] for r in c.execute("SELECT letra FROM grupos_gasto WHERE consorcio_id=?", (cid,))}
    c.execute("DELETE FROM unidad_grupo WHERE unidad_id=?", (uid,))
    for letra, valor in (porcentajes or {}).items():
        if letra not in letras:
            raise ErrorDeNegocio(f"El consorcio no tiene grupo de gastos {letra}.")
        absoluta = c.execute("SELECT superficies FROM consorcios WHERE id=?", (cid,)).fetchone()[0] == "absoluta"
        p = numero(valor, f"la superficie en m² del grupo {letra}" if absoluta else f"el porcentaje del grupo {letra}",
                   maximo=1_000_000 if absoluta else 100)
        if p:
            c.execute("INSERT INTO unidad_grupo VALUES (?,?,?)", (uid, letra, round(p, 4)))


def crear_unidad(cid: int, d: dict) -> dict:
    with transaccion() as c:
        fila(c, "SELECT id FROM consorcios WHERE id=?", (cid,), "ese consorcio")
        uid = c.execute("INSERT INTO unidades (consorcio_id, nombre, piso, depto, tipo) VALUES (?,?,?,?,?)",
                        (cid, *_datos_unidad(c, cid, d, None))).lastrowid
        _guardar_porcentajes(c, cid, uid, d.get("porcentajes"))
    return uid


def actualizar_unidad(uid: int, d: dict) -> None:
    with transaccion() as c:
        u = fila(c, "SELECT consorcio_id FROM unidades WHERE id=?", (uid,), "esa unidad")
        c.execute("UPDATE unidades SET nombre=?, piso=?, depto=?, tipo=? WHERE id=?", (*_datos_unidad(c, u["consorcio_id"], d, uid), uid))
        _guardar_porcentajes(c, u["consorcio_id"], uid, d.get("porcentajes"))


def cambiar_alta_unidad(uid: int, activa: bool) -> None:
    with transaccion() as c:
        fila(c, "SELECT id FROM unidades WHERE id=?", (uid,), "esa unidad")
        c.execute("UPDATE unidades SET activa=? WHERE id=?", (int(activa), uid))


def control_porcentajes(cid: int) -> dict:
    """Cuánto suman los porcentajes de cada grupo entre las unidades activas (tiene que dar 100)."""
    with transaccion() as c:
        return {r["letra"]: round(r["suma"] or 0, 4) for r in c.execute(
            "SELECT g.letra, (SELECT sum(ug.porcentaje) FROM unidad_grupo ug JOIN unidades u ON u.id=ug.unidad_id "
            "WHERE u.consorcio_id=g.consorcio_id AND u.activa=1 AND ug.letra=g.letra) AS suma "
            "FROM grupos_gasto g WHERE g.consorcio_id=? ORDER BY g.letra", (cid,))}


# ── personas (propietarios e inquilinos) ────────────────────────────────────

_CAMPOS_PERSONA = ("nombre", "apellido", "dni", "telefono", "email", "direccion", "nota")


def _datos_persona(d: dict) -> tuple:
    return (texto(d.get("nombre"), "el nombre"), texto(d.get("apellido"), "el apellido"),
            *(texto(d.get(k), "", False) for k in _CAMPOS_PERSONA[2:]))


def listar_personas(cid: int | None = None) -> list[dict]:
    """Todas las personas, o solo las de un consorcio, con las unidades a las que están ligadas."""
    with transaccion() as c:
        sql = ("SELECT DISTINCT p.* FROM personas p" +
               (" JOIN unidad_personas up ON up.persona_id=p.id JOIN unidades u ON u.id=up.unidad_id WHERE u.consorcio_id=?" if cid else "") +
               " ORDER BY p.apellido, p.nombre")
        ps = [dict(r) for r in c.execute(sql, (cid,) if cid else ())]
        for p in ps:
            p["unidades"] = [dict(r) for r in c.execute(
                "SELECT u.id, u.nombre, co.nombre AS consorcio, up.rol FROM unidad_personas up JOIN unidades u ON u.id=up.unidad_id "
                "JOIN consorcios co ON co.id=u.consorcio_id WHERE up.persona_id=? ORDER BY co.nombre, u.id", (p["id"],))]
        return ps


def crear_persona(d: dict) -> dict:
    with transaccion() as c:
        pid = c.execute(f"INSERT INTO personas ({', '.join(_CAMPOS_PERSONA)}) VALUES (?,?,?,?,?,?,?)", _datos_persona(d)).lastrowid
        return dict(c.execute("SELECT * FROM personas WHERE id=?", (pid,)).fetchone())


def actualizar_persona(pid: int, d: dict) -> dict:
    with transaccion() as c:
        fila(c, "SELECT id FROM personas WHERE id=?", (pid,), "esa persona")
        c.execute(f"UPDATE personas SET {', '.join(k + '=?' for k in _CAMPOS_PERSONA)} WHERE id=?", (*_datos_persona(d), pid))
        return dict(c.execute("SELECT * FROM personas WHERE id=?", (pid,)).fetchone())


def vincular(uid: int, pid: int, rol: str) -> None:
    rol = opcion(rol, ROLES, "el rol")
    with transaccion() as c:
        fila(c, "SELECT id FROM unidades WHERE id=?", (uid,), "esa unidad")
        fila(c, "SELECT id FROM personas WHERE id=?", (pid,), "esa persona")
        c.execute("INSERT OR IGNORE INTO unidad_personas VALUES (?,?,?)", (uid, pid, rol))


def desvincular(uid: int, pid: int, rol: str) -> None:
    with transaccion() as c:
        c.execute("DELETE FROM unidad_personas WHERE unidad_id=? AND persona_id=? AND rol=?", (uid, pid, rol))


# ── proveedores ─────────────────────────────────────────────────────────────

def listar_proveedores() -> list[dict]:
    with transaccion() as c:
        return [dict(r) for r in c.execute("SELECT * FROM proveedores ORDER BY activo DESC, nombre")]


def guardar_proveedor(pid: int | None, d: dict) -> dict:
    datos = (texto(d.get("nombre"), "el nombre"), texto(d.get("rubro"), "", False),
             texto(d.get("cuit"), "", False), texto(d.get("telefono"), "", False))
    with transaccion() as c:
        if c.execute("SELECT 1 FROM proveedores WHERE nombre=? AND id IS NOT ?", (datos[0], pid)).fetchone():
            raise ErrorDeNegocio(f"Ya existe el proveedor '{datos[0]}'.")
        if pid:
            fila(c, "SELECT id FROM proveedores WHERE id=?", (pid,), "ese proveedor")
            c.execute("UPDATE proveedores SET nombre=?, rubro=?, cuit=?, telefono=? WHERE id=?", (*datos, pid))
        else:
            pid = c.execute("INSERT INTO proveedores (nombre, rubro, cuit, telefono) VALUES (?,?,?,?)", datos).lastrowid
        return dict(c.execute("SELECT * FROM proveedores WHERE id=?", (pid,)).fetchone())


def cambiar_alta_proveedor(pid: int, activo: bool) -> None:
    with transaccion() as c:
        fila(c, "SELECT id FROM proveedores WHERE id=?", (pid,), "ese proveedor")
        c.execute("UPDATE proveedores SET activo=? WHERE id=?", (int(activo), pid))


def proveedor_valido(c, valor) -> int | None:
    if valor in (None, ""):
        return None
    fila(c, "SELECT id FROM proveedores WHERE id=?", (valor,), "ese proveedor")
    return int(valor)


def grupo_valido(c, cid: int, letra) -> str:
    letra = str(letra or "A").upper()
    if not c.execute("SELECT 1 FROM grupos_gasto WHERE consorcio_id=? AND letra=?", (cid, letra)).fetchone():
        raise ErrorDeNegocio(f"El consorcio no tiene grupo de gastos {letra}.")
    return letra


# ── gastos fijos (se repiten todos los meses) ───────────────────────────────

def listar_gastos_fijos(cid: int) -> list[dict]:
    with transaccion() as c:
        return [dict(r) for r in c.execute(
            "SELECT gf.*, p.nombre AS proveedor, r.numero AS rubro_numero, r.nombre AS rubro FROM gastos_fijos gf "
            "LEFT JOIN proveedores p ON p.id=gf.proveedor_id LEFT JOIN rubros r ON r.id=gf.rubro_id "
            "WHERE gf.consorcio_id=? ORDER BY gf.activo DESC, r.numero, gf.letra, gf.descripcion", (cid,))]


def guardar_gasto_fijo(cid: int, gid: int | None, d: dict) -> None:
    with transaccion() as c:
        fila(c, "SELECT id FROM consorcios WHERE id=?", (cid,), "ese consorcio")
        datos = (grupo_valido(c, cid, d.get("letra")), texto(d.get("descripcion"), "la descripción"),
                 proveedor_valido(c, d.get("proveedor_id")), pesos(d.get("importe"), "el importe"), rubro_valido(c, d.get("rubro_id")))
        if gid:
            fila(c, "SELECT id FROM gastos_fijos WHERE id=? AND consorcio_id=?", (gid, cid), "ese gasto fijo")
            c.execute("UPDATE gastos_fijos SET letra=?, descripcion=?, proveedor_id=?, importe=?, rubro_id=? WHERE id=?", (*datos, gid))
        else:
            c.execute("INSERT INTO gastos_fijos (consorcio_id, letra, descripcion, proveedor_id, importe, rubro_id) VALUES (?,?,?,?,?,?)",
                      (cid, *datos))


def cambiar_alta_gasto_fijo(gid: int, activo: bool) -> None:
    with transaccion() as c:
        fila(c, "SELECT id FROM gastos_fijos WHERE id=?", (gid,), "ese gasto fijo")
        c.execute("UPDATE gastos_fijos SET activo=? WHERE id=?", (int(activo), gid))


def rubro_valido(c, valor) -> int | None:
    if valor in (None, ""):
        return None
    fila(c, "SELECT id FROM rubros WHERE id=?", (valor,), "ese rubro")
    return int(valor)


# ── administración (datos del encabezado de las expensas) ──────────────────

_CAMPOS_ADMIN = ("nombre", "domicilio", "horarios", "cuit", "telefono", "email", "inscripcion_rpa", "situacion_fiscal")


def ver_administracion() -> dict:
    with transaccion() as c:
        return dict(c.execute("SELECT * FROM administracion WHERE id=1").fetchone())


def guardar_administracion(d: dict) -> dict:
    datos = [texto(d.get(k), "", False) for k in _CAMPOS_ADMIN]
    if not datos[0]:
        raise ErrorDeNegocio("Falta el nombre de la administración.")
    with transaccion() as c:
        c.execute(f"UPDATE administracion SET {', '.join(k + '=?' for k in _CAMPOS_ADMIN)} WHERE id=1", datos)
    return ver_administracion()


# ── rubros ──────────────────────────────────────────────────────────────────

def listar_rubros() -> list[dict]:
    with transaccion() as c:
        return [dict(r) for r in c.execute("SELECT * FROM rubros ORDER BY numero")]


def guardar_rubro(rid: int | None, d: dict) -> dict:
    numero_r = numero(d.get("numero"), "el número de rubro", entero=True, minimo=1, maximo=99)
    if numero_r is None:
        raise ErrorDeNegocio("Falta el número de rubro.")
    nombre = texto(d.get("nombre"), "el nombre del rubro")
    with transaccion() as c:
        if c.execute("SELECT 1 FROM rubros WHERE numero=? AND id IS NOT ?", (numero_r, rid)).fetchone():
            raise ErrorDeNegocio(f"Ya existe el rubro número {numero_r}.")
        if rid:
            fila(c, "SELECT id FROM rubros WHERE id=?", (rid,), "ese rubro")
            c.execute("UPDATE rubros SET numero=?, nombre=? WHERE id=?", (numero_r, nombre, rid))
        else:
            rid = c.execute("INSERT INTO rubros (numero, nombre) VALUES (?,?)", (numero_r, nombre)).lastrowid
        return dict(c.execute("SELECT * FROM rubros WHERE id=?", (rid,)).fetchone())


def cambiar_alta_rubro(rid: int, activo: bool) -> None:
    with transaccion() as c:
        fila(c, "SELECT id FROM rubros WHERE id=?", (rid,), "ese rubro")
        c.execute("UPDATE rubros SET activo=? WHERE id=?", (int(activo), rid))


# ── encargados y sus conceptos de sueldo fijos ─────────────────────────────

TIPOS_SUELDO = ("remuneracion", "descuento", "aporte")
_CAMPOS_ENCARGADO = ("nombre", "apellido", "dni", "cuil", "telefono", "cargo", "categoria", "fecha_ingreso", "letra")


def listar_encargados(cid: int) -> list[dict]:
    with transaccion() as c:
        fila(c, "SELECT id FROM consorcios WHERE id=?", (cid,), "ese consorcio")
        es = [dict(r) for r in c.execute("SELECT * FROM encargados WHERE consorcio_id=? ORDER BY activo DESC, apellido", (cid,))]
        for e in es:
            e["fijos"] = [dict(r) for r in c.execute(
                "SELECT * FROM sueldos_fijos WHERE encargado_id=? ORDER BY activo DESC, "
                "CASE tipo WHEN 'remuneracion' THEN 0 WHEN 'descuento' THEN 1 ELSE 2 END, id", (e["id"],))]
        return es


def guardar_encargado(cid: int, eid: int | None, d: dict) -> None:
    from .validar import fecha as _fecha
    with transaccion() as c:
        fila(c, "SELECT id FROM consorcios WHERE id=?", (cid,), "ese consorcio")
        datos = (texto(d.get("nombre"), "el nombre"), texto(d.get("apellido"), "el apellido"),
                 *(texto(d.get(k), "", False) for k in ("dni", "cuil", "telefono", "cargo", "categoria")),
                 _fecha(d.get("fecha_ingreso"), "la fecha de ingreso", False), grupo_valido(c, cid, d.get("letra")))
        if eid:
            fila(c, "SELECT id FROM encargados WHERE id=? AND consorcio_id=?", (eid, cid), "ese encargado")
            c.execute(f"UPDATE encargados SET {', '.join(k + '=?' for k in _CAMPOS_ENCARGADO)} WHERE id=?", (*datos, eid))
        else:
            c.execute(f"INSERT INTO encargados (consorcio_id, {', '.join(_CAMPOS_ENCARGADO)}) VALUES (?{', ?' * len(datos)})", (cid, *datos))


def cambiar_alta_encargado(eid: int, activo: bool) -> None:
    with transaccion() as c:
        fila(c, "SELECT id FROM encargados WHERE id=?", (eid,), "ese encargado")
        c.execute("UPDATE encargados SET activo=? WHERE id=?", (int(activo), eid))


def guardar_sueldo_fijo(eid: int, sid: int | None, d: dict) -> None:
    datos = (opcion(d.get("tipo"), TIPOS_SUELDO, "el tipo de concepto"), texto(d.get("concepto"), "el concepto"),
             pesos(d.get("importe"), "el importe"))
    with transaccion() as c:
        fila(c, "SELECT id FROM encargados WHERE id=?", (eid,), "ese encargado")
        if sid:
            fila(c, "SELECT id FROM sueldos_fijos WHERE id=? AND encargado_id=?", (sid, eid), "ese concepto")
            c.execute("UPDATE sueldos_fijos SET tipo=?, concepto=?, importe=? WHERE id=?", (*datos, sid))
        else:
            c.execute("INSERT INTO sueldos_fijos (encargado_id, tipo, concepto, importe) VALUES (?,?,?,?)", (eid, *datos))


def cambiar_alta_sueldo_fijo(sid: int, activo: bool) -> None:
    with transaccion() as c:
        fila(c, "SELECT id FROM sueldos_fijos WHERE id=?", (sid,), "ese concepto")
        c.execute("UPDATE sueldos_fijos SET activo=? WHERE id=?", (int(activo), sid))


# ── juicios ─────────────────────────────────────────────────────────────────

def listar_juicios(cid: int, solo_visibles: bool = False) -> list[dict]:
    with transaccion() as c:
        return [dict(r) for r in c.execute("SELECT * FROM juicios WHERE consorcio_id=?" + (" AND visible=1" if solo_visibles else "") +
                                           " ORDER BY id", (cid,))]


def guardar_juicio(cid: int, jid: int | None, d: dict) -> None:
    monto = d.get("monto_reclamado")
    datos = (texto(d.get("juzgado"), "el juzgado"), texto(d.get("expediente"), "", False), texto(d.get("caratula"), "la carátula"),
             pesos(monto, "el monto reclamado") if str(monto or "").strip() else None,
             texto(d.get("objeto"), "", False), texto(d.get("estado"), "el estado"), _si_no(d.get("visible", True)))
    with transaccion() as c:
        fila(c, "SELECT id FROM consorcios WHERE id=?", (cid,), "ese consorcio")
        if jid:
            fila(c, "SELECT id FROM juicios WHERE id=? AND consorcio_id=?", (jid, cid), "ese juicio")
            c.execute("UPDATE juicios SET juzgado=?, expediente=?, caratula=?, monto_reclamado=?, objeto=?, estado=?, visible=? "
                      "WHERE id=?", (*datos, jid))
        else:
            c.execute("INSERT INTO juicios (consorcio_id, juzgado, expediente, caratula, monto_reclamado, objeto, estado, visible) "
                      "VALUES (?,?,?,?,?,?,?,?)", (cid, *datos))


def borrar_juicio(jid: int) -> None:
    with transaccion() as c:
        fila(c, "SELECT id FROM juicios WHERE id=?", (jid,), "ese juicio")
        c.execute("DELETE FROM juicios WHERE id=?", (jid,))
