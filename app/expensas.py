"""Expensas: liquidación mensual, prorrateo, cobros, recibos, cuenta corriente y morosos.

Cómo funciona el dinero (todo en centavos):
- Al CERRAR una liquidación se reparte el total de cada grupo de gastos entre las unidades según su porcentaje
  en ese grupo. Los centavos que sobran del redondeo van a las unidades con mayor fracción, así la suma
  de lo que paga cada unidad da exacto el total del gasto.
- Los gastos de cada grupo son los gastos cargados más el costo del personal (remuneraciones - descuentos + aportes)
  del encargado que va en ese grupo. Los gastos particulares se cobran enteros a una sola unidad.
- A cada unidad se le guarda una "foto": saldo deudor (total de la liquidación anterior), pagos desde entonces,
  saldo anterior (lo que quedó debiendo), interés por mora, expensa del mes, gastos particulares y un redondeo
  para que el total quede en pesos enteros. Esa foto no cambia aunque después se carguen pagos.
- Al cerrar, los pagos que todavía no se habían informado quedan asociados a esa liquidación (columna "pagos")
  y se calcula la caja: saldo anterior + ingresos (pagos) - egresos (gastos) = saldo final.
- La cuenta corriente no se guarda aparte: sale de las liquidaciones cerradas (debe) y los pagos no anulados (haber).
  Así nunca puede quedar desfasada.
"""
import json
from datetime import date

from .db import transaccion
from . import servicios as sv
from .servicios import grupo_valido, proveedor_valido, rubro_valido
from .validar import ErrorDeNegocio, ahora, fecha, fila, periodo, pesos, texto

MODALIDADES = ("efectivo", "transferencia", "depósito", "cheque", "otro")
MESES = ("enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre")


def nombre_periodo(p: str) -> str:
    return f"{MESES[int(p[5:7]) - 1]} {p[:4]}"


CARGO = "(lu.interes + lu.expensa + lu.particulares + lu.redondeo)"   # lo que se le cobra a la unidad en una liquidación


def _saldo(c, uid: int) -> int:
    """Lo que debe hoy la unidad (positivo = debe; negativo = tiene saldo a favor)."""
    debe = c.execute(f"SELECT coalesce(sum({CARGO}), 0) FROM liquidacion_unidad lu "
                     "JOIN liquidaciones l ON l.id=lu.liquidacion_id WHERE lu.unidad_id=? AND l.estado='cerrada'", (uid,)).fetchone()[0]
    haber = c.execute("SELECT coalesce(sum(importe), 0) FROM pagos WHERE unidad_id=? AND anulado=0", (uid,)).fetchone()[0]
    return debe - haber


def _no_vencido(c, uid: int, dia: str) -> int:
    """Lo cobrado a la unidad en liquidaciones que todavía no vencieron a ese día."""
    return c.execute(f"SELECT coalesce(sum({CARGO}), 0) FROM liquidacion_unidad lu JOIN liquidaciones l "
                     "ON l.id=lu.liquidacion_id WHERE lu.unidad_id=? AND l.estado='cerrada' AND l.vencimiento >= ?",
                     (uid, dia)).fetchone()[0]


def _intereses_impagos(c, uid: int) -> int:
    """Intereses cobrados que todavía no se pagaron. Se considera que los pagos cancelan primero los intereses."""
    intereses = c.execute("SELECT coalesce(sum(lu.interes), 0) FROM liquidacion_unidad lu JOIN liquidaciones l "
                          "ON l.id=lu.liquidacion_id WHERE lu.unidad_id=? AND l.estado='cerrada'", (uid,)).fetchone()[0]
    pagado = c.execute("SELECT coalesce(sum(importe), 0) FROM pagos WHERE unidad_id=? AND anulado=0", (uid,)).fetchone()[0]
    return max(0, intereses - pagado)


def repartir(total: int, porcentajes: dict[int, float]) -> dict[int, int]:
    """Reparte 'total' centavos (positivo) según porcentajes, sin perder ni inventar centavos."""
    suma = sum(porcentajes.values())
    exactos = {u: total * p / suma for u, p in porcentajes.items()}
    partes = {u: int(v) for u, v in exactos.items()}
    sobrante = total - sum(partes.values())
    for u in sorted(exactos, key=lambda u: (exactos[u] - partes[u], porcentajes[u]), reverse=True)[:sobrante]:
        partes[u] += 1
    return partes


# ── liquidaciones ───────────────────────────────────────────────────────────

def listar_liquidaciones(cid: int) -> list[dict]:
    with transaccion() as c:
        fila(c, "SELECT id FROM consorcios WHERE id=?", (cid,), "ese consorcio")
        ls = [dict(r) for r in c.execute(
            "SELECT l.*, (SELECT coalesce(sum(importe),0) FROM gastos WHERE liquidacion_id=l.id) "
            "+ (SELECT coalesce(sum(CASE tipo WHEN 'descuento' THEN -importe ELSE importe END),0) FROM sueldos WHERE liquidacion_id=l.id) "
            "+ (SELECT coalesce(sum(importe),0) FROM gastos_particulares WHERE liquidacion_id=l.id) AS total_gastos, "
            "(SELECT count(*) FROM gastos WHERE liquidacion_id=l.id) AS cantidad_gastos "
            "FROM liquidaciones l WHERE l.consorcio_id=? ORDER BY l.periodo DESC", (cid,))]
        for l in ls:
            l["nombre"] = nombre_periodo(l["periodo"])
        return ls


def abrir_liquidacion(cid: int, d: dict) -> dict:
    """Abre la liquidación de un mes y le copia los gastos fijos y los conceptos de sueldo fijos del consorcio."""
    p = periodo(d.get("periodo"))
    with transaccion() as c:
        fila(c, "SELECT id FROM consorcios WHERE id=? AND activo=1", (cid,), "ese consorcio (o está dado de baja)")
        if c.execute("SELECT 1 FROM liquidaciones WHERE consorcio_id=? AND estado='abierta'", (cid,)).fetchone():
            raise ErrorDeNegocio("Ya hay una liquidación abierta en este consorcio: primero hay que cerrarla.")
        if c.execute("SELECT 1 FROM liquidaciones WHERE consorcio_id=? AND periodo=?", (cid, p)).fetchone():
            raise ErrorDeNegocio(f"Ya existe la liquidación de {nombre_periodo(p)}.")
        ultima = c.execute("SELECT max(periodo) FROM liquidaciones WHERE consorcio_id=?", (cid,)).fetchone()[0]
        if ultima and p < ultima:
            raise ErrorDeNegocio(f"No se puede abrir {nombre_periodo(p)}: ya está liquidado {nombre_periodo(ultima)}, que es posterior.")
        lid = c.execute("INSERT INTO liquidaciones (consorcio_id, periodo, nota) VALUES (?,?,?)",
                        (cid, p, texto(d.get("nota"), "", False))).lastrowid
        c.execute("INSERT INTO gastos (liquidacion_id, letra, descripcion, proveedor_id, importe, rubro_id) "
                  "SELECT ?, letra, descripcion, proveedor_id, importe, rubro_id FROM gastos_fijos WHERE consorcio_id=? AND activo=1",
                  (lid, cid))
        c.execute("INSERT INTO sueldos (liquidacion_id, encargado_id, tipo, concepto, importe) "
                  "SELECT ?, sf.encargado_id, sf.tipo, sf.concepto, sf.importe FROM sueldos_fijos sf JOIN encargados e "
                  "ON e.id=sf.encargado_id WHERE e.consorcio_id=? AND e.activo=1 AND sf.activo=1 ORDER BY sf.id", (lid, cid))
    return ver_liquidacion(lid)


def _liquidacion(c, lid: int):
    return fila(c, "SELECT * FROM liquidaciones WHERE id=?", (lid,), "esa liquidación")


def _abierta(c, lid: int):
    l = _liquidacion(c, lid)
    if l["estado"] != "abierta":
        raise ErrorDeNegocio("La liquidación ya está cerrada: para cambiarla hay que reabrirla.")
    return l


def ver_liquidacion(lid: int) -> dict:
    """La liquidación con sus gastos y, si está cerrada, el prorrateo por unidad. Si está abierta, una vista previa."""
    with transaccion() as c:
        l = dict(_liquidacion(c, lid))
        l["nombre"] = nombre_periodo(l["periodo"])
        co = c.execute("SELECT * FROM consorcios WHERE id=?", (l["consorcio_id"],)).fetchone()
        l["consorcio"] = dict(co)
        l["grupos"] = [dict(r) for r in c.execute("SELECT letra, nombre FROM grupos_gasto WHERE consorcio_id=? ORDER BY letra",
                                                  (l["consorcio_id"],))]
        l["gastos"] = [dict(r) for r in c.execute(
            "SELECT g.*, p.nombre AS proveedor, r.numero AS rubro_numero, r.nombre AS rubro FROM gastos g "
            "LEFT JOIN proveedores p ON p.id=g.proveedor_id LEFT JOIN rubros r ON r.id=g.rubro_id "
            "WHERE g.liquidacion_id=? ORDER BY coalesce(r.numero, 99), g.letra, g.id", (lid,))]
        l["particulares"] = [dict(r) for r in c.execute(
            "SELECT gp.*, u.nombre AS unidad, u.piso, u.depto FROM gastos_particulares gp JOIN unidades u ON u.id=gp.unidad_id "
            "WHERE gp.liquidacion_id=? ORDER BY u.id, gp.id", (lid,))]
        l["personal"] = _personal(c, lid)
        l["totales"] = _totales(c, lid)
        l["total_particulares"] = sum(g["importe"] for g in l["particulares"])
        l["administracion"] = dict(c.execute("SELECT * FROM administracion WHERE id=1").fetchone())
        l["juicios"] = [dict(r) for r in c.execute("SELECT * FROM juicios WHERE consorcio_id=? AND visible=1 ORDER BY id",
                                                   (l["consorcio_id"],))]
        if l["estado"] == "cerrada":
            filas = c.execute("SELECT lu.*, u.nombre, u.piso, u.depto, u.tipo FROM liquidacion_unidad lu JOIN unidades u ON u.id=lu.unidad_id "
                              "WHERE lu.liquidacion_id=? ORDER BY u.id", (lid,)).fetchall()
            l["prorrateo"] = [_fila_prorrateo(c, dict(r)) for r in filas]
            l["avisos"] = []
            l["caja"] = l["patrimonio"] = None
            if l["caja_anterior"] is not None:   # (las cerradas antes de existir la caja no tienen esos datos)
                final = l["caja_anterior"] + l["caja_ingresos"] - l["caja_egresos"]
                l["caja"] = {"anterior": l["caja_anterior"], "ingresos": l["caja_ingresos"], "egresos": l["caja_egresos"], "final": final,
                             "egresos_por_grupo": l["totales"], "egresos_particulares": l["total_particulares"]}
                a_cobrar = sum(f["total"] for f in l["prorrateo"])
                l["patrimonio"] = {"disponibilidades": final, "a_cobrar": a_cobrar, "neto": final + a_cobrar}
        else:
            try:
                l["prorrateo"] = [_fila_prorrateo(c, r) for r in _calcular(c, l)]
                l["avisos"] = []
            except ErrorDeNegocio as e:
                l["prorrateo"], l["avisos"] = [], [str(e)]
        return l


def _fila_prorrateo(c, r: dict) -> dict:
    r["por_grupo"] = json.loads(r["por_grupo"]) if isinstance(r["por_grupo"], str) else r["por_grupo"]
    r["total"] = r["saldo_anterior"] + r["interes"] + r["expensa"] + r["particulares"] + r["redondeo"]
    r["ajustes"] = r["saldo_anterior"] - (r["saldo_deudor"] - r["pagos"])   # anulaciones u otros cambios de la cuenta
    r["propietarios"] = ", ".join(f"{p['apellido']}, {p['nombre']}" for p in c.execute(
        "SELECT p.nombre, p.apellido FROM unidad_personas up JOIN personas p ON p.id=up.persona_id "
        "WHERE up.unidad_id=? AND up.rol='propietario' ORDER BY p.apellido", (r["unidad_id"],)))
    r["inquilinos"] = ", ".join(f"{p['apellido']}, {p['nombre']}" for p in c.execute(
        "SELECT p.nombre, p.apellido FROM unidad_personas up JOIN personas p ON p.id=up.persona_id "
        "WHERE up.unidad_id=? AND up.rol='inquilino' ORDER BY p.apellido", (r["unidad_id"],)))
    return r


def _calcular(c, l: dict) -> list[dict]:
    """El prorrateo de una liquidación abierta, sin guardarlo."""
    cid = l["consorcio_id"]
    co = c.execute("SELECT interes_mora, superficies, tipo_interes FROM consorcios WHERE id=?", (cid,)).fetchone()
    unidades = c.execute("SELECT id, nombre, piso, depto, tipo FROM unidades WHERE consorcio_id=? AND activa=1 ORDER BY id", (cid,)).fetchall()
    if not unidades:
        raise ErrorDeNegocio("El consorcio no tiene unidades activas.")
    reparto = {u["id"]: {} for u in unidades}
    for letra, total in _totales(c, l["id"]).items():
        if total == 0:
            continue
        if total < 0:
            raise ErrorDeNegocio(f"El total del grupo {letra} da negativo: revisar los descuentos del sueldo.")
        pcts = {r["unidad_id"]: r["porcentaje"] for r in c.execute(
            "SELECT ug.unidad_id, ug.porcentaje FROM unidad_grupo ug JOIN unidades u ON u.id=ug.unidad_id "
            "WHERE u.consorcio_id=? AND u.activa=1 AND ug.letra=? AND ug.porcentaje > 0", (cid, letra))}
        suma = sum(pcts.values())
        if co["superficies"] == "absoluta":   # m²: cada unidad paga según su parte de la superficie total del grupo
            if suma <= 0:
                raise ErrorDeNegocio(f"Ninguna unidad tiene superficie cargada en el grupo {letra}. "
                                     "Cargarla en Consorcios > Unidades antes de cerrar.")
        elif abs(suma - 100) > 0.01:
            raise ErrorDeNegocio(f"Los porcentajes del grupo {letra} suman {suma:.2f}% y tienen que sumar 100%. "
                                 "Corregirlos en Consorcios > Unidades antes de cerrar.")
        for uid, importe in repartir(total, pcts).items():
            reparto[uid][letra] = importe
    particulares = {r[0]: r[1] for r in c.execute(
        "SELECT unidad_id, sum(importe) FROM gastos_particulares WHERE liquidacion_id=? GROUP BY unidad_id", (l["id"],))}
    anterior = c.execute("SELECT id FROM liquidaciones WHERE consorcio_id=? AND estado='cerrada' AND periodo<? "
                         "ORDER BY periodo DESC LIMIT 1", (cid, l["periodo"])).fetchone()
    filas = []
    for u in unidades:
        saldo = _saldo(c, u["id"])
        deudor = c.execute(f"SELECT lu.saldo_anterior + {CARGO} FROM liquidacion_unidad lu WHERE lu.liquidacion_id=? AND lu.unidad_id=?",
                           (anterior["id"], u["id"])).fetchone() if anterior else None
        pagos = c.execute("SELECT coalesce(sum(importe), 0) FROM pagos WHERE unidad_id=? AND anulado=0 AND liquidacion_id IS NULL",
                          (u["id"],)).fetchone()[0]
        vencido = max(0, saldo - _no_vencido(c, u["id"], date.today().isoformat()))
        if co["tipo_interes"] == "simple":
            vencido -= min(vencido, _intereses_impagos(c, u["id"]))   # simple: no se cobra interés sobre interés
        interes = round(vencido * co["interes_mora"] / 100)   # solo sobre lo que ya pasó su vencimiento
        expensa = sum(reparto[u["id"]].values())
        part = particulares.get(u["id"], 0)
        sin_redondeo = saldo + interes + expensa + part
        redondeo = (sin_redondeo + 50) // 100 * 100 - sin_redondeo     # al peso entero más cercano
        filas.append({"liquidacion_id": l["id"], "unidad_id": u["id"], "nombre": u["nombre"], "piso": u["piso"], "depto": u["depto"],
                      "tipo": u["tipo"], "saldo_deudor": deudor[0] if deudor else saldo + pagos, "pagos": pagos,
                      "saldo_anterior": saldo, "interes": interes, "por_grupo": reparto[u["id"]], "expensa": expensa,
                      "particulares": part, "redondeo": redondeo})
    return filas


def _totales(c, lid: int) -> dict[str, int]:
    """Total a repartir por grupo: gastos cargados + costo del personal que va en ese grupo."""
    tot = {}
    for r in c.execute("SELECT letra, sum(importe) FROM gastos WHERE liquidacion_id=? GROUP BY letra", (lid,)):
        tot[r[0]] = tot.get(r[0], 0) + r[1]
    for r in c.execute("SELECT e.letra, sum(CASE s.tipo WHEN 'descuento' THEN -s.importe ELSE s.importe END) FROM sueldos s "
                       "JOIN encargados e ON e.id=s.encargado_id WHERE s.liquidacion_id=? GROUP BY e.letra", (lid,)):
        tot[r[0]] = tot.get(r[0], 0) + r[1]
    return dict(sorted(tot.items()))


def _personal(c, lid: int) -> list[dict]:
    """Por encargado: sus conceptos de sueldo del mes, separados, con los subtotales que muestra la liquidación."""
    out = []
    for e in c.execute("SELECT DISTINCT e.* FROM sueldos s JOIN encargados e ON e.id=s.encargado_id WHERE s.liquidacion_id=? "
                       "ORDER BY e.apellido", (lid,)).fetchall():
        items = [dict(r) for r in c.execute("SELECT * FROM sueldos WHERE liquidacion_id=? AND encargado_id=? ORDER BY id", (lid, e["id"]))]
        suma = lambda t: sum(i["importe"] for i in items if i["tipo"] == t)
        neto = suma("remuneracion") - suma("descuento")
        out.append({"encargado": dict(e), "items": items, "remuneraciones": suma("remuneracion"), "descuentos": suma("descuento"),
                    "neto": neto, "aportes": suma("aporte"), "total": neto + suma("aporte")})
    return out


def cerrar_liquidacion(lid: int, d: dict) -> dict:
    with transaccion() as c:
        l = dict(_abierta(c, lid))
        if not any(c.execute(f"SELECT 1 FROM {t} WHERE liquidacion_id=?", (lid,)).fetchone()
                   for t in ("gastos", "sueldos", "gastos_particulares")):
            raise ErrorDeNegocio("La liquidación no tiene gastos cargados.")
        dia = c.execute("SELECT dia_vencimiento FROM consorcios WHERE id=?", (l["consorcio_id"],)).fetchone()[0]
        anio, mes = int(l["periodo"][:4]), int(l["periodo"][5:7])
        siguiente = date(anio + mes // 12, mes % 12 + 1, dia).isoformat()
        vence = fecha(d.get("vencimiento"), "el vencimiento", False) or siguiente
        filas = _calcular(c, l)
        for f in filas:
            c.execute("INSERT INTO liquidacion_unidad (liquidacion_id, unidad_id, saldo_anterior, interes, por_grupo, expensa, "
                      "saldo_deudor, pagos, particulares, redondeo) VALUES (?,?,?,?,?,?,?,?,?,?)",
                      (lid, f["unidad_id"], f["saldo_anterior"], f["interes"], json.dumps(f["por_grupo"]), f["expensa"],
                       f["saldo_deudor"], f["pagos"], f["particulares"], f["redondeo"]))
        # caja: arranca de la liquidación anterior (o de la caja inicial del consorcio)
        prev = c.execute("SELECT caja_anterior + caja_ingresos - caja_egresos FROM liquidaciones WHERE consorcio_id=? "
                         "AND estado='cerrada' AND periodo<? AND caja_anterior IS NOT NULL ORDER BY periodo DESC LIMIT 1",
                         (l["consorcio_id"], l["periodo"])).fetchone()
        caja_anterior = prev[0] if prev else c.execute("SELECT caja_inicial FROM consorcios WHERE id=?", (l["consorcio_id"],)).fetchone()[0]
        ingresos = sum(f["pagos"] for f in filas)
        egresos = sum(_totales(c, lid).values()) + c.execute(
            "SELECT coalesce(sum(importe), 0) FROM gastos_particulares WHERE liquidacion_id=?", (lid,)).fetchone()[0]
        c.execute("UPDATE pagos SET liquidacion_id=? WHERE liquidacion_id IS NULL AND anulado=0 AND unidad_id IN "
                  "(SELECT id FROM unidades WHERE consorcio_id=? AND activa=1)", (lid, l["consorcio_id"]))
        c.execute("UPDATE liquidaciones SET estado='cerrada', vencimiento=?, cerrada_en=?, caja_anterior=?, caja_ingresos=?, "
                  "caja_egresos=? WHERE id=?", (vence, ahora(), caja_anterior, ingresos, egresos, lid))
    return ver_liquidacion(lid)


def reabrir_liquidacion(lid: int) -> dict:
    """Solo la última cerrada del consorcio, y si no hay otra abierta: borra el prorrateo para poder corregir."""
    with transaccion() as c:
        l = _liquidacion(c, lid)
        if l["estado"] != "cerrada":
            raise ErrorDeNegocio("La liquidación ya está abierta.")
        posterior = c.execute("SELECT periodo FROM liquidaciones WHERE consorcio_id=? AND periodo>?",
                              (l["consorcio_id"], l["periodo"])).fetchone()
        if posterior:
            raise ErrorDeNegocio(f"No se puede reabrir: ya existe la liquidación de {nombre_periodo(posterior[0])}.")
        c.execute("DELETE FROM liquidacion_unidad WHERE liquidacion_id=?", (lid,))
        c.execute("UPDATE pagos SET liquidacion_id=NULL WHERE liquidacion_id=?", (lid,))
        c.execute("UPDATE liquidaciones SET estado='abierta', vencimiento=NULL, cerrada_en=NULL, caja_anterior=NULL, "
                  "caja_ingresos=NULL, caja_egresos=NULL WHERE id=?", (lid,))
    return ver_liquidacion(lid)


def borrar_liquidacion(lid: int) -> None:
    """Una liquidación abierta se puede descartar entera (con sus gastos)."""
    with transaccion() as c:
        _abierta(c, lid)
        for t in ("gastos", "sueldos", "gastos_particulares"):
            c.execute(f"DELETE FROM {t} WHERE liquidacion_id=?", (lid,))
        c.execute("DELETE FROM liquidaciones WHERE id=?", (lid,))


# ── gastos de una liquidación ───────────────────────────────────────────────

def guardar_gasto(lid: int, gid: int | None, d: dict) -> dict:
    with transaccion() as c:
        l = _abierta(c, lid)
        datos = (grupo_valido(c, l["consorcio_id"], d.get("letra")), texto(d.get("descripcion"), "la descripción"),
                 proveedor_valido(c, d.get("proveedor_id")), texto(d.get("comprobante"), "", False), pesos(d.get("importe"), "el importe"),
                 rubro_valido(c, d.get("rubro_id")), texto(d.get("periodo"), "", False))
        if gid:
            fila(c, "SELECT id FROM gastos WHERE id=? AND liquidacion_id=?", (gid, lid), "ese gasto")
            c.execute("UPDATE gastos SET letra=?, descripcion=?, proveedor_id=?, comprobante=?, importe=?, rubro_id=?, periodo=? "
                      "WHERE id=?", (*datos, gid))
        else:
            c.execute("INSERT INTO gastos (liquidacion_id, letra, descripcion, proveedor_id, comprobante, importe, rubro_id, periodo) "
                      "VALUES (?,?,?,?,?,?,?,?)", (lid, *datos))
    return ver_liquidacion(lid)


# ── gastos particulares (de una sola unidad) ────────────────────────────────

def guardar_particular(lid: int, gid: int | None, d: dict) -> dict:
    with transaccion() as c:
        l = _abierta(c, lid)
        uid = d.get("unidad_id")
        fila(c, "SELECT id FROM unidades WHERE id=? AND consorcio_id=? AND activa=1", (uid or 0, l["consorcio_id"]), "esa unidad en este consorcio")
        datos = (int(uid), texto(d.get("descripcion"), "la descripción"), pesos(d.get("importe"), "el importe"))
        if gid:
            fila(c, "SELECT id FROM gastos_particulares WHERE id=? AND liquidacion_id=?", (gid, lid), "ese gasto particular")
            c.execute("UPDATE gastos_particulares SET unidad_id=?, descripcion=?, importe=? WHERE id=?", (*datos, gid))
        else:
            c.execute("INSERT INTO gastos_particulares (liquidacion_id, unidad_id, descripcion, importe) VALUES (?,?,?,?)", (lid, *datos))
    return ver_liquidacion(lid)


def borrar_particular(gid: int) -> dict:
    with transaccion() as c:
        g = fila(c, "SELECT liquidacion_id FROM gastos_particulares WHERE id=?", (gid,), "ese gasto particular")
        _abierta(c, g["liquidacion_id"])
        c.execute("DELETE FROM gastos_particulares WHERE id=?", (gid,))
    return ver_liquidacion(g["liquidacion_id"])


# ── sueldos del personal en una liquidación ─────────────────────────────────

def guardar_sueldo(lid: int, sid: int | None, d: dict) -> dict:
    with transaccion() as c:
        l = _abierta(c, lid)
        eid = d.get("encargado_id")
        fila(c, "SELECT id FROM encargados WHERE id=? AND consorcio_id=?", (eid or 0, l["consorcio_id"]), "ese encargado en este consorcio")
        datos = (int(eid), sv.opcion(d.get("tipo"), sv.TIPOS_SUELDO, "el tipo de concepto"), texto(d.get("concepto"), "el concepto"),
                 pesos(d.get("importe"), "el importe"))
        if sid:
            fila(c, "SELECT id FROM sueldos WHERE id=? AND liquidacion_id=?", (sid, lid), "ese concepto")
            c.execute("UPDATE sueldos SET encargado_id=?, tipo=?, concepto=?, importe=? WHERE id=?", (*datos, sid))
        else:
            c.execute("INSERT INTO sueldos (liquidacion_id, encargado_id, tipo, concepto, importe) VALUES (?,?,?,?,?)", (lid, *datos))
    return ver_liquidacion(lid)


def borrar_sueldo(sid: int) -> dict:
    with transaccion() as c:
        s = fila(c, "SELECT liquidacion_id FROM sueldos WHERE id=?", (sid,), "ese concepto")
        _abierta(c, s["liquidacion_id"])
        c.execute("DELETE FROM sueldos WHERE id=?", (sid,))
    return ver_liquidacion(s["liquidacion_id"])


def borrar_gasto(gid: int) -> dict:
    with transaccion() as c:
        g = fila(c, "SELECT liquidacion_id FROM gastos WHERE id=?", (gid,), "ese gasto")
        _abierta(c, g["liquidacion_id"])
        c.execute("DELETE FROM gastos WHERE id=?", (gid,))
    return ver_liquidacion(g["liquidacion_id"])


# ── cobros y recibos ────────────────────────────────────────────────────────

def _unidad(c, uid: int):
    return fila(c, "SELECT u.*, co.nombre AS consorcio, co.direccion FROM unidades u JOIN consorcios co ON co.id=u.consorcio_id "
                   "WHERE u.id=?", (uid,), "esa unidad")


def registrar_pago(usuario: dict, uid: int, d: dict) -> dict:
    with transaccion() as c:
        u = _unidad(c, uid)
        datos = (fecha(d.get("fecha") or date.today().isoformat(), "la fecha"), pesos(d.get("importe"), "el importe"),
                 (d.get("modalidad") or "efectivo"), texto(d.get("pago_quien"), "", False), texto(d.get("nota"), "", False))
        if datos[2] not in MODALIDADES:
            raise ErrorDeNegocio(f"La forma de pago tiene que ser una de: {', '.join(MODALIDADES)}.")
        numero = c.execute("SELECT coalesce(max(p.recibo_numero), 0) + 1 FROM pagos p JOIN unidades x ON x.id=p.unidad_id "
                           "WHERE x.consorcio_id=?", (u["consorcio_id"],)).fetchone()[0]
        pid = c.execute("INSERT INTO pagos (unidad_id, fecha, importe, modalidad, pago_quien, nota, recibo_numero, registrado_por, "
                        "registrado_en) VALUES (?,?,?,?,?,?,?,?,?)", (uid, *datos, numero, usuario["nombre"], ahora())).lastrowid
    return recibo(pid)


def anular_pago(pid: int) -> dict:
    """Un pago mal cargado no se borra: se anula (deja de contar) y el número de recibo queda registrado como anulado."""
    with transaccion() as c:
        p = fila(c, "SELECT anulado FROM pagos WHERE id=?", (pid,), "ese pago")
        if p["anulado"]:
            raise ErrorDeNegocio("Ese pago ya estaba anulado.")
        c.execute("UPDATE pagos SET anulado=1 WHERE id=?", (pid,))
    return recibo(pid)


def recibo(pid: int) -> dict:
    with transaccion() as c:
        p = dict(fila(c, "SELECT * FROM pagos WHERE id=?", (pid,), "ese pago"))
        u = _unidad(c, p["unidad_id"])
        p.update(unidad=u["nombre"], piso=u["piso"], depto=u["depto"], consorcio=u["consorcio"], direccion=u["direccion"],
                 consorcio_id=u["consorcio_id"], saldo_actual=_saldo(c, p["unidad_id"]))
        p["propietarios"] = ", ".join(f"{r['apellido']}, {r['nombre']}" for r in c.execute(
            "SELECT p.nombre, p.apellido FROM unidad_personas up JOIN personas p ON p.id=up.persona_id "
            "WHERE up.unidad_id=? AND up.rol='propietario'", (p["unidad_id"],)))
        return p


def listar_pagos(cid: int, desde: str | None = None, hasta: str | None = None) -> list[dict]:
    with transaccion() as c:
        fila(c, "SELECT id FROM consorcios WHERE id=?", (cid,), "ese consorcio")
        return [dict(r) for r in c.execute(
            "SELECT p.*, u.nombre AS unidad FROM pagos p JOIN unidades u ON u.id=p.unidad_id WHERE u.consorcio_id=? "
            "AND p.fecha >= coalesce(?, '0000') AND p.fecha <= coalesce(?, '9999') ORDER BY p.fecha DESC, p.recibo_numero DESC",
            (cid, fecha(desde, "desde", False), fecha(hasta, "hasta", False)))]


# ── cuenta corriente, saldos y morosos ──────────────────────────────────────

def cuenta_corriente(uid: int) -> dict:
    with transaccion() as c:
        u = dict(_unidad(c, uid))
        movs = []
        for r in c.execute("SELECT l.periodo, l.cerrada_en, l.vencimiento, lu.interes, lu.expensa, lu.particulares, lu.redondeo "
                           "FROM liquidacion_unidad lu "
                           "JOIN liquidaciones l ON l.id=lu.liquidacion_id WHERE lu.unidad_id=? AND l.estado='cerrada'", (uid,)):
            dia = r["cerrada_en"][:10]
            if r["interes"]:
                movs.append({"fecha": dia, "concepto": f"Interés por mora ({nombre_periodo(r['periodo'])})", "debe": r["interes"], "haber": 0, "orden": 0})
            movs.append({"fecha": dia, "concepto": f"Expensas {nombre_periodo(r['periodo'])} (vence {r['vencimiento']})",
                         "debe": r["expensa"], "haber": 0, "orden": 1})
            if r["particulares"]:
                movs.append({"fecha": dia, "concepto": f"Gastos particulares ({nombre_periodo(r['periodo'])})",
                             "debe": r["particulares"], "haber": 0, "orden": 1})
            if r["redondeo"]:
                movs.append({"fecha": dia, "concepto": "Redondeo", "debe": r["redondeo"], "haber": 0, "orden": 1})
        for r in c.execute("SELECT * FROM pagos WHERE unidad_id=? AND anulado=0", (uid,)):
            movs.append({"fecha": r["fecha"], "concepto": f"Pago {r['modalidad']} - recibo {r['recibo_numero']}", "debe": 0,
                         "haber": r["importe"], "orden": 2, "pago_id": r["id"]})
        movs.sort(key=lambda m: (m["fecha"], m["orden"]))
        saldo = 0
        for m in movs:
            saldo += m["debe"] - m["haber"]
            m["saldo"] = saldo
        u["movimientos"], u["saldo"] = movs, saldo
        return u


def saldos(cid: int) -> list[dict]:
    """Saldo de cada unidad, con la parte vencida (lo que pasó su fecha de vencimiento sin pagarse) y el último pago."""
    hoy = date.today().isoformat()
    with transaccion() as c:
        fila(c, "SELECT id FROM consorcios WHERE id=?", (cid,), "ese consorcio")
        filas = []
        for u in c.execute("SELECT id, nombre, piso, depto, tipo FROM unidades WHERE consorcio_id=? AND activa=1 ORDER BY id", (cid,)).fetchall():
            saldo = _saldo(c, u["id"])
            no_vencido = _no_vencido(c, u["id"], hoy)
            ultimo = c.execute("SELECT max(fecha) FROM pagos WHERE unidad_id=? AND anulado=0", (u["id"],)).fetchone()[0]
            props = ", ".join(f"{r['apellido']}, {r['nombre']}" for r in c.execute(
                "SELECT p.nombre, p.apellido FROM unidad_personas up JOIN personas p ON p.id=up.persona_id "
                "WHERE up.unidad_id=? AND up.rol='propietario'", (u["id"],)))
            filas.append({**dict(u), "saldo": saldo, "vencido": max(0, saldo - no_vencido), "ultimo_pago": ultimo, "propietarios": props})
        return filas


def morosos(cid: int | None = None) -> list[dict]:
    with transaccion() as c:
        ids = [r[0] for r in c.execute("SELECT id FROM consorcios WHERE activo=1" + (" AND id=?" if cid else "") + " ORDER BY nombre",
                                       (cid,) if cid else ())]
        nombres = {r["id"]: r["nombre"] for r in c.execute("SELECT id, nombre FROM consorcios")}
    out = []
    for i in ids:
        out += [{**f, "consorcio_id": i, "consorcio": nombres[i]} for f in saldos(i) if f["vencido"] > 0]
    return out


def resumen() -> list[dict]:
    """Para la pantalla de inicio: por consorcio, unidades, última liquidación, deuda total y morosos."""
    hoy = date.today().isoformat()
    with transaccion() as c:
        cons = [dict(r) for r in c.execute("SELECT id, nombre, direccion FROM consorcios WHERE activo=1 ORDER BY nombre")]
        for co in cons:
            l = c.execute("SELECT id, periodo, estado FROM liquidaciones WHERE consorcio_id=? ORDER BY periodo DESC LIMIT 1",
                          (co["id"],)).fetchone()
            co["ultima"] = {**dict(l), "nombre": nombre_periodo(l["periodo"])} if l else None
            co["cobrado_hoy"] = c.execute("SELECT coalesce(sum(p.importe),0) FROM pagos p JOIN unidades u ON u.id=p.unidad_id "
                                          "WHERE u.consorcio_id=? AND p.fecha=? AND p.anulado=0", (co["id"], hoy)).fetchone()[0]
    for co in cons:
        s = saldos(co["id"])
        co["unidades"] = len(s)
        co["deuda_total"] = sum(max(0, f["saldo"]) for f in s)
        co["morosos"] = sum(1 for f in s if f["vencido"] > 0)
    return cons
