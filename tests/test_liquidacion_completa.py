"""Liquidación con todo lo de la Ley 941: sueldos, rubros, gastos particulares, pagos del período, redondeo, caja y juicios."""


def _consorcio(cliente, caja_inicial="1000"):
    c = cliente.post("/api/consorcios", json={"nombre": "Completo", "direccion": "Calle 1", "email": "c@ejemplo.com",
                                              "caja_inicial": caja_inicial, "banco_cbu": "123", "banco_alias": "alias.prueba"}).json()
    u1 = cliente.post(f"/api/consorcios/{c['id']}/unidades", json={"nombre": "UF 1", "porcentajes": {"A": 50}}).json()["id"]
    u2 = cliente.post(f"/api/consorcios/{c['id']}/unidades", json={"nombre": "UF 2", "porcentajes": {"A": 50}}).json()["id"]
    return c["id"], u1, u2


def _encargado(cliente, cid):
    cliente.post(f"/api/consorcios/{cid}/encargados", json={"nombre": "Ernesto", "apellido": "Prueba", "letra": "A"})
    eid = cliente.get(f"/api/consorcios/{cid}/encargados").json()[0]["id"]
    for tipo, concepto, imp in (("remuneracion", "Básico", "1000"), ("descuento", "Jubilación", "200"), ("aporte", "F.931", "300")):
        cliente.post(f"/api/encargados/{eid}/sueldos-fijos", json={"tipo": tipo, "concepto": concepto, "importe": imp})
    return eid


def test_sueldo_del_encargado_se_reparte_en_su_grupo(cliente):
    cid, u1, u2 = _consorcio(cliente)
    _encargado(cliente, cid)
    l = cliente.post(f"/api/consorcios/{cid}/liquidaciones", json={"periodo": "2026-09"}).json()
    p = l["personal"][0]
    assert (p["remuneraciones"], p["descuentos"], p["neto"], p["aportes"], p["total"]) == (100000, 20000, 80000, 30000, 110000)
    assert l["totales"] == {"A": 110000}                       # 1000 - 200 + 300 pesos
    l = cliente.post(f"/api/liquidaciones/{l['id']}/cerrar", json={}).json()
    assert [f["expensa"] for f in l["prorrateo"]] == [55000, 55000]


def test_descuentos_mayores_que_el_sueldo_no_dejan_cerrar(cliente):
    cid, *_ = _consorcio(cliente)
    eid = _encargado(cliente, cid)
    l = cliente.post(f"/api/consorcios/{cid}/liquidaciones", json={"periodo": "2026-09"}).json()
    cliente.post(f"/api/liquidaciones/{l['id']}/sueldos", json={"encargado_id": eid, "tipo": "descuento", "concepto": "Error", "importe": "5000"})
    r = cliente.post(f"/api/liquidaciones/{l['id']}/cerrar", json={})
    assert r.status_code == 400 and "negativo" in r.json()["detail"]


def test_gasto_particular_solo_lo_paga_esa_unidad(cliente):
    cid, u1, u2 = _consorcio(cliente)
    lid = cliente.post(f"/api/consorcios/{cid}/liquidaciones", json={"periodo": "2026-09"}).json()["id"]
    cliente.post(f"/api/liquidaciones/{lid}/gastos", json={"letra": "A", "descripcion": "Luz", "importe": "100"})
    cliente.post(f"/api/liquidaciones/{lid}/particulares", json={"unidad_id": u2, "descripcion": "Destapación", "importe": "33,40"})
    l = cliente.post(f"/api/liquidaciones/{lid}/cerrar", json={}).json()
    f = {x["unidad_id"]: x for x in l["prorrateo"]}
    assert f[u1]["particulares"] == 0 and f[u1]["total"] == 5000
    assert f[u2]["particulares"] == 3340
    assert f[u2]["redondeo"] == -40 and f[u2]["total"] == 8300          # $83,40 -> $83 (pesos enteros)
    assert cliente.get(f"/api/unidades/{u2}/cuenta").json()["saldo"] == 8300


def test_pagos_del_periodo_y_caja(cliente):
    cid, u1, u2 = _consorcio(cliente, caja_inicial="1000")
    lid = cliente.post(f"/api/consorcios/{cid}/liquidaciones", json={"periodo": "2026-09"}).json()["id"]
    cliente.post(f"/api/liquidaciones/{lid}/gastos", json={"letra": "A", "descripcion": "Luz", "importe": "100"})
    l1 = cliente.post(f"/api/liquidaciones/{lid}/cerrar", json={"vencimiento": "2999-01-01"}).json()
    assert l1["caja"]["anterior"] == 100000 and l1["caja"]["egresos"] == 10000 and l1["caja"]["final"] == 90000
    pago = cliente.post(f"/api/unidades/{u1}/pagos", json={"importe": "50"}).json()

    lid2 = cliente.post(f"/api/consorcios/{cid}/liquidaciones", json={"periodo": "2026-10"}).json()["id"]
    cliente.post(f"/api/liquidaciones/{lid2}/gastos", json={"letra": "A", "descripcion": "Luz", "importe": "100"})
    l2 = cliente.post(f"/api/liquidaciones/{lid2}/cerrar", json={}).json()
    f = {x["unidad_id"]: x for x in l2["prorrateo"]}
    assert (f[u1]["saldo_deudor"], f[u1]["pagos"], f[u1]["saldo_anterior"]) == (5000, 5000, 0)
    assert (f[u2]["saldo_deudor"], f[u2]["pagos"], f[u2]["saldo_anterior"]) == (5000, 0, 5000)
    assert l2["caja"]["anterior"] == 90000 and l2["caja"]["ingresos"] == 5000 and l2["caja"]["final"] == 85000
    assert l2["patrimonio"]["a_cobrar"] == sum(x["total"] for x in l2["prorrateo"])

    # un pago anulado después de informado aparece como ajuste en la liquidación siguiente
    cliente.post(f"/api/pagos/{pago['id']}/anular")
    lid3 = cliente.post(f"/api/consorcios/{cid}/liquidaciones", json={"periodo": "2026-11"}).json()["id"]
    cliente.post(f"/api/liquidaciones/{lid3}/gastos", json={"letra": "A", "descripcion": "Luz", "importe": "100"})
    l3 = cliente.post(f"/api/liquidaciones/{lid3}/cerrar", json={}).json()
    f = {x["unidad_id"]: x for x in l3["prorrateo"]}
    assert f[u1]["ajustes"] == 5000 and f[u1]["saldo_anterior"] == 10000


def test_reabrir_devuelve_los_pagos_a_pendientes(cliente):
    cid, u1, u2 = _consorcio(cliente)
    cliente.post(f"/api/unidades/{u1}/pagos", json={"importe": "10"})
    lid = cliente.post(f"/api/consorcios/{cid}/liquidaciones", json={"periodo": "2026-09"}).json()["id"]
    cliente.post(f"/api/liquidaciones/{lid}/gastos", json={"letra": "A", "descripcion": "Luz", "importe": "100"})
    assert cliente.post(f"/api/liquidaciones/{lid}/cerrar", json={}).json()["caja"]["ingresos"] == 1000
    cliente.post(f"/api/liquidaciones/{lid}/reabrir")
    l = cliente.post(f"/api/liquidaciones/{lid}/cerrar", json={}).json()
    assert l["caja"]["ingresos"] == 1000                     # el pago se vuelve a contar una sola vez


def test_rubros_y_administracion(cliente):
    rubros = cliente.get("/api/rubros").json()
    assert [r["numero"] for r in rubros] == list(range(1, 11))
    assert cliente.post("/api/rubros", json={"numero": "2", "nombre": "Repetido"}).status_code == 400
    a = cliente.put("/api/administracion", json={"nombre": "Adm. Prueba", "cuit": "20-1-0", "inscripcion_rpa": "99"}).json()
    assert (a["nombre"], a["inscripcion_rpa"]) == ("Adm. Prueba", "99")
    assert cliente.put("/api/administracion", json={"nombre": ""}).status_code == 400


def test_gasto_con_rubro_y_juicio_visible(cliente):
    cid, *_ = _consorcio(cliente)
    rubro = cliente.get("/api/rubros").json()[1]["id"]
    cliente.post(f"/api/consorcios/{cid}/juicios", json={"juzgado": "Civil 1", "caratula": "X c/ Y", "estado": "En trámite", "monto_reclamado": "1.500"})
    cliente.post(f"/api/consorcios/{cid}/juicios", json={"juzgado": "Civil 2", "caratula": "Oculto", "estado": "Archivado", "visible": False})
    lid = cliente.post(f"/api/consorcios/{cid}/liquidaciones", json={"periodo": "2026-09"}).json()["id"]
    l = cliente.post(f"/api/liquidaciones/{lid}/gastos", json={"letra": "A", "descripcion": "Luz", "importe": "100", "rubro_id": rubro,
                                                             "periodo": "08/2026"}).json()
    assert (l["gastos"][0]["rubro_numero"], l["gastos"][0]["periodo"]) == (2, "08/2026")
    assert [j["caratula"] for j in l["juicios"]] == ["X c/ Y"] and l["juicios"][0]["monto_reclamado"] == 150000


def test_gastos_fijos_copian_su_rubro(cliente):
    cid, *_ = _consorcio(cliente)
    rubro = cliente.get("/api/rubros").json()[2]["id"]
    cliente.post(f"/api/consorcios/{cid}/gastos-fijos", json={"letra": "A", "descripcion": "Abono", "importe": "10", "rubro_id": rubro})
    l = cliente.post(f"/api/consorcios/{cid}/liquidaciones", json={"periodo": "2026-09"}).json()
    assert l["gastos"][0]["rubro_numero"] == 3
