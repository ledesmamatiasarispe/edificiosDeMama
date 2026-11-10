"""Datos de ejemplo INVENTADOS para probar la app (nombres, direcciones y montos ficticios).

Se cargan solos la primera vez, si la base no tiene ningún consorcio. Nunca usar datos reales acá.
"""
from . import expensas as ex
from . import servicios as sv
from .db import transaccion

_SISTEMA = {"id": 0, "nombre": "Datos de ejemplo"}


def cargar_si_vacia() -> None:
    with transaccion() as c:
        if c.execute("SELECT 1 FROM consorcios").fetchone():
            return
    cargar()


def _fechar(lid: int, cerrada_en: str) -> None:
    with transaccion() as c:
        c.execute("UPDATE liquidaciones SET cerrada_en=? WHERE id=?", (cerrada_en, lid))


def cargar() -> None:
    sv.guardar_administracion({"nombre": "Administración Ejemplo", "domicilio": "Calle Inventada 1234", "horarios": "Lunes a viernes de 13 a 18",
                               "cuit": "20-00000000-0", "telefono": "11 0000-0000", "email": "administracion@ejemplo.com",
                               "inscripcion_rpa": "0000", "situacion_fiscal": "Monotributo"})
    rubro = {r["numero"]: r["id"] for r in sv.listar_rubros()}
    prov = {n: sv.guardar_proveedor(None, {"nombre": n, "rubro": r})["id"] for n, r in (
        ("Limpieza Brillante (ejemplo)", "Limpieza"), ("Ascensores Arriba (ejemplo)", "Ascensores"),
        ("Compañía de Luz (ejemplo)", "Servicios"), ("Agua Corriente (ejemplo)", "Servicios"),
        ("Plomería Don Caño (ejemplo)", "Mantenimiento"))}

    # ── Edificio 1: con local, cochera y ascensor (grupo B solo para las viviendas) ──
    a = sv.crear_consorcio({"nombre": "Edificio Los Aromos (ejemplo)", "direccion": "Calle Inventada 1234",
                            "localidad": "Ciudad de Ejemplo", "cp": "1000", "email": "losaromos@ejemplo.com",
                            "interes_mora": "3", "dia_vencimiento": "10", "categoria": "2", "anio_construccion": "1975",
                            "tipo_interes": "simple", "mostrar_inquilino": True, "caja_inicial": "1600000",
                            "banco_titular": "Consorcio Los Aromos (ejemplo)", "banco_nombre": "Banco de Ejemplo",
                            "banco_sucursal": "Centro", "banco_cuenta": "CC 0000-0", "banco_cbu": "0000000000000000000000",
                            "banco_alias": "aromos.ejemplo",
                            "nota_expensas": "Pagar por transferencia indicando la unidad."})["id"]
    sv.guardar_grupos(a, [{"letra": "A", "nombre": "Gastos generales"}, {"letra": "B", "nombre": "Ascensor"}])
    unidades_a = [  # nombre, piso, depto, tipo, % A, % B
        ("UF 1", "PB", "Local", "local", 16, 0), ("UF 2", "1", "A", "vivienda", 14, 16), ("UF 3", "1", "B", "vivienda", 12, 14),
        ("UF 4", "2", "A", "vivienda", 14, 16), ("UF 5", "2", "B", "vivienda", 12, 14), ("UF 6", "3", "A", "vivienda", 14, 20),
        ("UF 7", "3", "B", "vivienda", 12, 20), ("UF 8", "SS", "Cochera", "cochera", 6, 0)]
    ua = [sv.crear_unidad(a, {"nombre": n, "piso": p, "depto": d, "tipo": t, "porcentajes": {"A": pa, "B": pb}})
          for n, p, d, t, pa, pb in unidades_a]
    personas = [("Ana", "Ejemplo"), ("Bruno", "Prueba"), ("Carla", "Ficticia"), ("Diego", "Inventado"), ("Elena", "Muestra"),
                ("Fabián", "Modelo"), ("Gabriela", "Ensayo"), ("Hugo", "Demo")]
    pids = [sv.crear_persona({"nombre": n, "apellido": ap, "telefono": "11 0000-0000", "email": f"{n.lower()}@ejemplo.com"})["id"]
            for n, ap in personas]
    for i, uid in enumerate(ua[:7]):
        sv.vincular(uid, pids[i], "propietario")
    sv.vincular(ua[7], pids[1], "propietario")            # Bruno tiene la cochera además de la UF 2
    inq = sv.crear_persona({"nombre": "Inés", "apellido": "Inquilina", "telefono": "11 1111-1111"})["id"]
    sv.vincular(ua[4], inq, "inquilino")

    for letra, desc, p, imp, rub in (("A", "Limpieza de espacios comunes", "Limpieza Brillante (ejemplo)", "120000", 7),
                                     ("A", "Luz de espacios comunes", "Compañía de Luz (ejemplo)", "65000", 2),
                                     ("A", "Agua", "Agua Corriente (ejemplo)", "48000", 2),
                                     ("A", "Honorarios de administración", None, "75000", 8),
                                     ("A", "Comisión mantenimiento de cuenta", None, "12000", 6),
                                     ("A", "Seguro integral del consorcio", None, "40000", 9),
                                     ("B", "Abono mantenimiento ascensor", "Ascensores Arriba (ejemplo)", "95000", 3)):
        sv.guardar_gasto_fijo(a, None, {"letra": letra, "descripcion": desc, "proveedor_id": prov.get(p), "importe": imp,
                                        "rubro_id": rubro[rub]})
    # encargado con su sueldo (rubro 1): remuneración, descuentos y aportes, todos los meses
    sv.guardar_encargado(a, None, {"nombre": "Ernesto", "apellido": "Encargado (ejemplo)", "cuil": "20-00000000-1", "cargo": "Encargado permanente",
                                   "categoria": "Primera", "fecha_ingreso": "2015-03-01", "letra": "A"})
    enc = sv.listar_encargados(a)[0]["id"]
    for tipo, concepto, imp in (("remuneracion", "Sueldo básico", "780000"), ("remuneracion", "Antigüedad", "70000"),
                                ("descuento", "Jubilación, obra social y sindicato", "187000"),
                                ("aporte", "Contribuciones patronales (F.931)", "230000"), ("aporte", "SUTERH", "35000")):
        sv.guardar_sueldo_fijo(enc, None, {"tipo": tipo, "concepto": concepto, "importe": imp})
    sv.guardar_juicio(a, None, {"juzgado": "Juzgado Civil 0 (ejemplo)", "expediente": "0000/2025", "caratula": "Consorcio c/ Ejemplo s/ cobro de expensas",
                                "monto_reclamado": "300000", "objeto": "Cobro de expensas", "estado": "En trámite", "visible": True})

    # septiembre: cerrada y pagada por casi todos
    sep = ex.abrir_liquidacion(a, {"periodo": "2026-09"})["id"]
    ex.guardar_gasto(sep, None, {"letra": "A", "descripcion": "Arreglo de canilla en terraza", "proveedor_id": prov["Plomería Don Caño (ejemplo)"],
                                 "comprobante": "Factura C 0001-00000123", "importe": "35000", "rubro_id": rubro[4]})
    ex.cerrar_liquidacion(sep, {"vencimiento": "2026-10-10"})
    _fechar(sep, "2026-10-01T10:00:00")
    s = {f["unidad_id"]: f["total"] for f in ex.ver_liquidacion(sep)["prorrateo"]}
    for uid in ua:
        if uid != ua[5]:                                   # la UF 6 no pagó septiembre
            ex.registrar_pago(_SISTEMA, uid, {"fecha": "2026-10-08", "importe": s[uid] / 100, "modalidad": "transferencia"})

    # octubre: cerrada; la UF 6 arrastra deuda con interés y la UF 3 pagó solo una parte
    octu = ex.abrir_liquidacion(a, {"periodo": "2026-10"})["id"]
    ex.cerrar_liquidacion(octu, {"vencimiento": "2026-11-10"})
    _fechar(octu, "2026-11-01T10:00:00")
    o = {f["unidad_id"]: f["total"] for f in ex.ver_liquidacion(octu)["prorrateo"]}
    for uid in (ua[0], ua[1], ua[3], ua[7]):
        ex.registrar_pago(_SISTEMA, uid, {"fecha": "2026-11-05", "importe": o[uid] / 100, "modalidad": "efectivo"})
    ex.registrar_pago(_SISTEMA, ua[2], {"fecha": "2026-11-06", "importe": "100000", "modalidad": "transferencia", "nota": "Pago parcial"})

    # noviembre: abierta, con los gastos fijos y uno extra
    nov = ex.abrir_liquidacion(a, {"periodo": "2026-11"})["id"]
    ex.guardar_gasto(nov, None, {"letra": "A", "descripcion": "Pintura del hall de entrada", "importe": "180000", "rubro_id": rubro[4]})
    ex.guardar_particular(nov, None, {"unidad_id": ua[3], "descripcion": "Destapación de cañería de la unidad", "importe": "32500"})

    # ── Edificio 2: chico, solo viviendas, un solo grupo de gastos y reparto por m² (superficies absoluta) ──
    b = sv.crear_consorcio({"nombre": "Edificio Las Lilas (ejemplo)", "direccion": "Pasaje Ficticio 567",
                            "localidad": "Ciudad de Ejemplo", "email": "laslilas@ejemplo.com",
                            "interes_mora": "2", "dia_vencimiento": "15", "categoria": "4", "superficies": "absoluta"})["id"]
    ub = [sv.crear_unidad(b, {"nombre": f"UF {i + 1}", "piso": str(i // 2 + 1), "depto": "AB"[i % 2], "tipo": "vivienda",
                              "porcentajes": {"A": m2}}) for i, m2 in enumerate((72, 60, 72, 60, 72, 64))]
    for uid, (n, ap) in zip(ub, (("Irene", "Simulada"), ("Julio", "Supuesto"), ("Karina", "Ejemplar"), ("Luis", "Tester"),
                                 ("Marta", "Borrador"), ("Néstor", "Maqueta"))):
        sv.vincular(uid, sv.crear_persona({"nombre": n, "apellido": ap})["id"], "propietario")
    sv.guardar_gasto_fijo(b, None, {"letra": "A", "descripcion": "Limpieza", "proveedor_id": prov["Limpieza Brillante (ejemplo)"], "importe": "90000"})
    sv.guardar_gasto_fijo(b, None, {"letra": "A", "descripcion": "Luz de espacios comunes", "proveedor_id": prov["Compañía de Luz (ejemplo)"],
                                    "importe": "30000"})
    octb = ex.abrir_liquidacion(b, {"periodo": "2026-10"})["id"]
    ex.cerrar_liquidacion(octb, {"vencimiento": "2026-11-15"})
    _fechar(octb, "2026-11-01T10:00:00")
