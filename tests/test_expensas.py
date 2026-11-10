"""Reglas de dinero y del circuito completo: consorcio -> unidades -> liquidación -> cierre -> cobro -> saldo."""
import pytest

from app import expensas as ex
from app.validar import ErrorDeNegocio, pesos


@pytest.mark.parametrize("texto, centavos", [
    ("1000", 100000), ("1.000", 100000), ("1.234,56", 123456), ("1234,5", 123450), ("1234.56", 123456),
    ("$ 12.500", 1250000), ("0,01", 1), ("1.000.000", 100000000)])
def test_pesos_acepta_como_lo_escribe_una_persona(texto, centavos):
    assert pesos(texto, "el importe") == centavos


@pytest.mark.parametrize("texto", ["", "abc", "0", "-5", "nan"])
def test_pesos_rechaza_importes_invalidos(texto):
    with pytest.raises(ErrorDeNegocio):
        pesos(texto, "el importe")


def test_repartir_no_pierde_ni_inventa_centavos():
    partes = repartir = ex.repartir(100, {1: 33.3333, 2: 33.3333, 3: 33.3334})
    assert sum(partes.values()) == 100
    assert sorted(repartir.values()) == [33, 33, 34]
    assert sum(ex.repartir(1_000_001, {1: 16, 2: 14, 3: 12, 4: 58}).values()) == 1_000_001


def _armar(cliente, interes="3", tipo="compuesto"):
    c = cliente.post("/api/consorcios", json={"nombre": "Prueba", "direccion": "Calle 1", "email": "prueba@ejemplo.com",
                                                "interes_mora": interes, "tipo_interes": tipo}).json()
    cliente.put(f"/api/consorcios/{c['id']}/grupos", json=[{"letra": "A", "nombre": "Generales"}, {"letra": "B", "nombre": "Ascensor"}])
    u1 = cliente.post(f"/api/consorcios/{c['id']}/unidades", json={"nombre": "UF 1", "tipo": "local", "porcentajes": {"A": 40}}).json()["id"]
    u2 = cliente.post(f"/api/consorcios/{c['id']}/unidades", json={"nombre": "UF 2", "porcentajes": {"A": 60, "B": 100}}).json()["id"]
    return c["id"], u1, u2


def test_circuito_completo(cliente):
    cid, u1, u2 = _armar(cliente)
    lid = cliente.post(f"/api/consorcios/{cid}/liquidaciones", json={"periodo": "2026-09"}).json()["id"]
    assert cliente.post(f"/api/liquidaciones/{lid}/gastos", json={"letra": "A", "descripcion": "Limpieza", "importe": "1000"}).status_code == 200
    cliente.post(f"/api/liquidaciones/{lid}/gastos", json={"letra": "B", "descripcion": "Ascensor", "importe": "500,50"})
    l = cliente.post(f"/api/liquidaciones/{lid}/cerrar", json={"vencimiento": "2026-10-10"}).json()
    assert l["estado"] == "cerrada"
    por_uf = {f["unidad_id"]: f for f in l["prorrateo"]}
    assert por_uf[u1]["expensa"] == 40000                     # 40% de $1000
    assert por_uf[u2]["expensa"] == 60000 + 50050             # 60% de $1000 + todo el ascensor

    # la UF 1 paga todo; la UF 2 paga una parte
    r = cliente.post(f"/api/unidades/{u1}/pagos", json={"importe": "400", "fecha": "2026-10-05"}).json()
    assert r["recibo_numero"] == 1 and r["saldo_actual"] == 0
    r = cliente.post(f"/api/unidades/{u2}/pagos", json={"importe": "100", "fecha": "2026-10-05"}).json()
    assert por_uf[u2]["redondeo"] == 50 and por_uf[u2]["total"] == 110100   # $1100,50 -> $1101 (pesos enteros)
    assert r["recibo_numero"] == 2 and r["saldo_actual"] == 110100 - 10000

    # el mes siguiente, la UF 2 paga interés sobre lo que quedó debiendo
    lid2 = cliente.post(f"/api/consorcios/{cid}/liquidaciones", json={"periodo": "2026-10"}).json()["id"]
    cliente.post(f"/api/liquidaciones/{lid2}/gastos", json={"letra": "A", "descripcion": "Luz", "importe": "100"})
    l2 = cliente.post(f"/api/liquidaciones/{lid2}/cerrar", json={}).json()
    f2 = {f["unidad_id"]: f for f in l2["prorrateo"]}
    assert f2[u2]["saldo_anterior"] == 100100
    assert f2[u2]["saldo_deudor"] == 110100 and f2[u2]["pagos"] == 10000
    assert f2[u2]["interes"] == round(100100 * 0.03)
    assert f2[u1]["interes"] == 0
    assert l2["vencimiento"] == "2026-11-10"

    cc = cliente.get(f"/api/unidades/{u2}/cuenta").json()
    assert cc["saldo"] == f2[u2]["total"] and f2[u2]["total"] % 100 == 0
    morosos = cliente.get("/api/morosos").json()
    assert [m["id"] for m in morosos] == [u2]                 # la deuda de septiembre ya venció


def test_no_cobra_interes_sobre_deuda_que_todavia_no_vencio(cliente):
    cid, u1, u2 = _armar(cliente)
    lid = cliente.post(f"/api/consorcios/{cid}/liquidaciones", json={"periodo": "2026-09"}).json()["id"]
    cliente.post(f"/api/liquidaciones/{lid}/gastos", json={"letra": "A", "descripcion": "Limpieza", "importe": "1000"})
    cliente.post(f"/api/liquidaciones/{lid}/cerrar", json={"vencimiento": "2999-01-01"})
    lid2 = cliente.post(f"/api/consorcios/{cid}/liquidaciones", json={"periodo": "2026-10"}).json()["id"]
    cliente.post(f"/api/liquidaciones/{lid2}/gastos", json={"letra": "A", "descripcion": "Luz", "importe": "100"})
    l2 = cliente.post(f"/api/liquidaciones/{lid2}/cerrar", json={}).json()
    assert all(f["interes"] == 0 for f in l2["prorrateo"])
    assert all(f["saldo_anterior"] > 0 for f in l2["prorrateo"])


def test_no_cierra_si_los_porcentajes_no_suman_100(cliente):
    cid, u1, u2 = _armar(cliente)
    cliente.put(f"/api/unidades/{u1}", json={"nombre": "UF 1", "tipo": "local", "porcentajes": {"A": 30}})
    lid = cliente.post(f"/api/consorcios/{cid}/liquidaciones", json={"periodo": "2026-09"}).json()["id"]
    cliente.post(f"/api/liquidaciones/{lid}/gastos", json={"letra": "A", "descripcion": "Limpieza", "importe": "1000"})
    r = cliente.post(f"/api/liquidaciones/{lid}/cerrar", json={})
    assert r.status_code == 400 and "suman 90" in r.json()["detail"]
    assert cliente.get(f"/api/liquidaciones/{lid}").json()["avisos"]


def test_cerrada_no_se_modifica_y_se_puede_reabrir(cliente):
    cid, u1, u2 = _armar(cliente)
    lid = cliente.post(f"/api/consorcios/{cid}/liquidaciones", json={"periodo": "2026-09"}).json()["id"]
    cliente.post(f"/api/liquidaciones/{lid}/gastos", json={"letra": "A", "descripcion": "Limpieza", "importe": "1000"})
    cliente.post(f"/api/liquidaciones/{lid}/cerrar", json={})
    assert cliente.post(f"/api/liquidaciones/{lid}/gastos", json={"letra": "A", "descripcion": "X", "importe": "1"}).status_code == 400
    assert cliente.post(f"/api/liquidaciones/{lid}/reabrir").json()["estado"] == "abierta"
    assert cliente.get(f"/api/unidades/{u1}/cuenta").json()["saldo"] == 0


def test_una_sola_abierta_y_sin_meses_repetidos(cliente):
    cid, *_ = _armar(cliente)
    assert cliente.post(f"/api/consorcios/{cid}/liquidaciones", json={"periodo": "2026-09"}).status_code == 200
    r = cliente.post(f"/api/consorcios/{cid}/liquidaciones", json={"periodo": "2026-10"})
    assert r.status_code == 400 and "abierta" in r.json()["detail"]


def test_gastos_fijos_se_copian_al_abrir(cliente):
    cid, *_ = _armar(cliente)
    cliente.post(f"/api/consorcios/{cid}/gastos-fijos", json={"letra": "A", "descripcion": "Sueldo", "importe": "850.000"})
    l = cliente.post(f"/api/consorcios/{cid}/liquidaciones", json={"periodo": "2026-09"}).json()
    assert [(g["descripcion"], g["importe"]) for g in l["gastos"]] == [("Sueldo", 85_000_000)]


def test_anular_pago_lo_saca_del_saldo(cliente):
    cid, u1, _ = _armar(cliente)
    p = cliente.post(f"/api/unidades/{u1}/pagos", json={"importe": "100"}).json()
    assert p["saldo_actual"] == -10000                         # saldo a favor
    assert cliente.post(f"/api/pagos/{p['id']}/anular").json()["saldo_actual"] == 0
    assert cliente.post(f"/api/pagos/{p['id']}/anular").status_code == 400


def test_sin_sesion_no_se_ve_nada(cliente):
    cliente.headers.pop("Authorization")
    assert cliente.get("/api/consorcios").status_code == 401


def test_datos_de_ejemplo_cargan_y_cierran(base_ejemplos):
    resumen = {c["nombre"]: c for c in ex.resumen()}
    assert len(resumen) == 2
    aromos = resumen["Edificio Los Aromos (ejemplo)"]
    assert aromos["unidades"] == 8 and aromos["ultima"]["estado"] == "abierta"


def _dos_meses_con_deuda(cliente, tipo):
    """UF 2 no paga septiembre (vencido) ni octubre; se cierra noviembre y se mira el interés."""
    cid, u1, u2 = _armar(cliente, tipo=tipo)
    for periodo, vence in (("2026-08", "2026-09-10"), ("2026-09", "2026-10-10")):
        lid = cliente.post(f"/api/consorcios/{cid}/liquidaciones", json={"periodo": periodo}).json()["id"]
        cliente.post(f"/api/liquidaciones/{lid}/gastos", json={"letra": "A", "descripcion": "Limpieza", "importe": "1000"})
        cliente.post(f"/api/liquidaciones/{lid}/cerrar", json={"vencimiento": vence})
    lid = cliente.post(f"/api/consorcios/{cid}/liquidaciones", json={"periodo": "2026-10"}).json()["id"]
    cliente.post(f"/api/liquidaciones/{lid}/gastos", json={"letra": "A", "descripcion": "Luz", "importe": "100"})
    l = cliente.post(f"/api/liquidaciones/{lid}/cerrar", json={}).json()
    return {f["unidad_id"]: f for f in l["prorrateo"]}[u2]


def test_interes_simple_no_cobra_interes_sobre_interes(cliente):
    f = _dos_meses_con_deuda(cliente, "simple")
    # agosto 60000 + interés de septiembre (3% de 60000 = 1800) + septiembre 60000: el interés simple es sobre 120000
    assert f["saldo_anterior"] == 121800
    assert f["interes"] == 3600


def test_interes_compuesto_cobra_interes_sobre_interes(cliente):
    f = _dos_meses_con_deuda(cliente, "compuesto")
    assert f["saldo_anterior"] == 121800
    assert f["interes"] == round(121800 * 0.03)


def test_superficies_absolutas_reparte_por_metros(cliente):
    c = cliente.post("/api/consorcios", json={"nombre": "Metros", "direccion": "Calle 2", "email": "m@ejemplo.com",
                                              "superficies": "absoluta"}).json()
    u1 = cliente.post(f"/api/consorcios/{c['id']}/unidades", json={"nombre": "UF 1", "porcentajes": {"A": 50}}).json()["id"]
    u2 = cliente.post(f"/api/consorcios/{c['id']}/unidades", json={"nombre": "UF 2", "porcentajes": {"A": 150}}).json()["id"]
    lid = cliente.post(f"/api/consorcios/{c['id']}/liquidaciones", json={"periodo": "2026-09"}).json()["id"]
    cliente.post(f"/api/liquidaciones/{lid}/gastos", json={"letra": "A", "descripcion": "Limpieza", "importe": "1000"})
    l = cliente.post(f"/api/liquidaciones/{lid}/cerrar", json={}).json()
    assert {f["unidad_id"]: f["expensa"] for f in l["prorrateo"]} == {u1: 25000, u2: 75000}


def test_datos_del_consorcio_se_guardan(cliente):
    datos = {"nombre": "Completo", "direccion": "Calle 3", "email": "c@ejemplo.com", "clave_suterh": "123",
             "categoria": "3", "anio_construccion": "1980", "tipo_interes": "compuesto", "mostrar_inquilino": True,
             "envia_comprobantes": True, "imputa_a_deuda": False, "liquida_mes_vencido": False}
    c = cliente.post("/api/consorcios", json=datos).json()
    assert (c["clave_suterh"], c["categoria"], c["anio_construccion"], c["tipo_interes"]) == ("123", "3", 1980, "compuesto")
    assert (c["mostrar_inquilino"], c["envia_comprobantes"], c["imputa_a_deuda"], c["liquida_mes_vencido"]) == (1, 1, 0, 0)


def test_consorcio_sin_email_no_se_guarda(cliente):
    r = cliente.post("/api/consorcios", json={"nombre": "Sin mail", "direccion": "Calle 4"})
    assert r.status_code == 400 and "email" in r.json()["detail"]


def test_base_vieja_se_actualiza(tmp_path, monkeypatch):
    import sqlite3
    from app import db
    viejo = tmp_path / "vieja.db"
    con = sqlite3.connect(viejo)
    con.executescript(db.ESQUEMA.replace("CHECK (porcentaje >= 0)", "CHECK (porcentaje >= 0 AND porcentaje <= 100)")
                      .replace("    -- más columnas en _COLUMNAS_NUEVAS (se agregan también a bases ya creadas)\n", ""))
    con.execute("INSERT INTO consorcios (nombre, direccion) VALUES ('Viejo', 'Calle')")
    con.execute("INSERT INTO unidades (consorcio_id, nombre) VALUES (1, 'UF 1')")
    con.execute("INSERT INTO unidad_grupo VALUES (1, 'A', 100)")
    con.commit(); con.close()
    monkeypatch.setattr(db, "DB_PATH", viejo)
    db.inicializar(con_ejemplos=False)
    with db.transaccion() as c:
        assert tuple(c.execute("SELECT tipo_interes, imputa_a_deuda FROM consorcios").fetchone()) == ("simple", 1)
        c.execute("INSERT INTO unidad_grupo VALUES (1, 'B', 250)")    # ahora acepta m²
        assert c.execute("SELECT count(*) FROM unidad_grupo").fetchone()[0] == 2
