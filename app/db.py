"""Base SQLite: esquema, conexión y datos de ejemplo.

sqlite3 directo (sin ORM), claves foráneas activadas y todo el esquema en un solo lugar.
Los importes de dinero se guardan SIEMPRE en centavos (número entero), nunca con decimales sueltos.
"""
import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = Path(os.environ.get("EDIF_DB", ROOT / "data" / "edificios.db"))

GRUPOS = ("A", "B", "C", "D", "E")

ESQUEMA = """
CREATE TABLE IF NOT EXISTS usuarios (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    usuario       TEXT    NOT NULL UNIQUE COLLATE NOCASE,   -- con lo que entra (ej. "mama")
    nombre        TEXT    NOT NULL,
    password_hash TEXT    NOT NULL,
    salt          TEXT    NOT NULL,
    es_admin      INTEGER NOT NULL DEFAULT 0,
    activo        INTEGER NOT NULL DEFAULT 1,
    debe_cambiar  INTEGER NOT NULL DEFAULT 0     -- contraseña provisoria: cambiarla al entrar
);
CREATE TABLE IF NOT EXISTS sesiones (
    token      TEXT PRIMARY KEY,
    usuario_id INTEGER NOT NULL REFERENCES usuarios(id),
    vence_en   TEXT    NOT NULL,
    activa     INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS consorcios (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    nombre            TEXT    NOT NULL UNIQUE COLLATE NOCASE,
    direccion         TEXT    NOT NULL,
    localidad         TEXT    NOT NULL DEFAULT '',
    cp                TEXT    NOT NULL DEFAULT '',
    cuit              TEXT    NOT NULL DEFAULT '',
    email             TEXT    NOT NULL DEFAULT '',
    interes_mora      REAL    NOT NULL DEFAULT 0,       -- % mensual sobre la deuda vencida
    dia_vencimiento   INTEGER NOT NULL DEFAULT 10,      -- día del mes siguiente en que vencen las expensas
    nota_expensas     TEXT    NOT NULL DEFAULT '',
    activo            INTEGER NOT NULL DEFAULT 1
    -- más columnas en _COLUMNAS_NUEVAS (se agregan también a bases ya creadas)
);
-- Grupos de gastos (A = generales; B, C... para gastos que pagan solo algunas unidades, ej. ascensor)
CREATE TABLE IF NOT EXISTS grupos_gasto (
    consorcio_id INTEGER NOT NULL REFERENCES consorcios(id),
    letra        TEXT    NOT NULL CHECK (letra IN ('A','B','C','D','E')),
    nombre       TEXT    NOT NULL,
    PRIMARY KEY (consorcio_id, letra)
);
CREATE TABLE IF NOT EXISTS unidades (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    consorcio_id  INTEGER NOT NULL REFERENCES consorcios(id),
    nombre        TEXT    NOT NULL,                     -- "UF 3"
    piso          TEXT    NOT NULL DEFAULT '',
    depto         TEXT    NOT NULL DEFAULT '',
    tipo          TEXT    NOT NULL DEFAULT 'vivienda' CHECK (tipo IN ('vivienda','local','cochera','baulera','otro')),
    activa        INTEGER NOT NULL DEFAULT 1,
    UNIQUE (consorcio_id, nombre)
);
-- Porcentaje de cada unidad en cada grupo de gastos (los de un grupo suman 100)
CREATE TABLE IF NOT EXISTS unidad_grupo (
    unidad_id  INTEGER NOT NULL REFERENCES unidades(id),
    letra      TEXT    NOT NULL,
    porcentaje REAL    NOT NULL CHECK (porcentaje >= 0),   -- % (superficies porcentual) o m² (superficies absoluta)
    PRIMARY KEY (unidad_id, letra)
);
CREATE TABLE IF NOT EXISTS personas (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    nombre     TEXT    NOT NULL,
    apellido   TEXT    NOT NULL,
    dni        TEXT    NOT NULL DEFAULT '',
    telefono   TEXT    NOT NULL DEFAULT '',
    email      TEXT    NOT NULL DEFAULT '',
    direccion  TEXT    NOT NULL DEFAULT '',
    nota       TEXT    NOT NULL DEFAULT ''
);
-- Quién es dueño o inquilino de cada unidad
CREATE TABLE IF NOT EXISTS unidad_personas (
    unidad_id  INTEGER NOT NULL REFERENCES unidades(id),
    persona_id INTEGER NOT NULL REFERENCES personas(id),
    rol        TEXT    NOT NULL CHECK (rol IN ('propietario','inquilino')),
    PRIMARY KEY (unidad_id, persona_id, rol)
);
CREATE TABLE IF NOT EXISTS proveedores (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    nombre    TEXT    NOT NULL UNIQUE COLLATE NOCASE,
    rubro     TEXT    NOT NULL DEFAULT '',
    cuit      TEXT    NOT NULL DEFAULT '',
    telefono  TEXT    NOT NULL DEFAULT '',
    activo    INTEGER NOT NULL DEFAULT 1
);
-- Liquidación mensual de expensas de un consorcio
CREATE TABLE IF NOT EXISTS liquidaciones (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    consorcio_id INTEGER NOT NULL REFERENCES consorcios(id),
    periodo      TEXT    NOT NULL,                       -- "2026-10" (mes de los gastos)
    estado       TEXT    NOT NULL DEFAULT 'abierta' CHECK (estado IN ('abierta','cerrada')),
    vencimiento  TEXT,                                   -- fecha en que vence el pago (al cerrar)
    nota         TEXT    NOT NULL DEFAULT '',
    cerrada_en   TEXT,
    UNIQUE (consorcio_id, periodo)
);
CREATE TABLE IF NOT EXISTS gastos (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    liquidacion_id  INTEGER NOT NULL REFERENCES liquidaciones(id),
    letra           TEXT    NOT NULL,
    descripcion     TEXT    NOT NULL,
    proveedor_id    INTEGER REFERENCES proveedores(id),
    comprobante     TEXT    NOT NULL DEFAULT '',
    importe         INTEGER NOT NULL CHECK (importe > 0)  -- centavos
);
-- Gastos que se repiten todos los meses: se copian al abrir una liquidación nueva
CREATE TABLE IF NOT EXISTS gastos_fijos (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    consorcio_id  INTEGER NOT NULL REFERENCES consorcios(id),
    letra         TEXT    NOT NULL,
    descripcion   TEXT    NOT NULL,
    proveedor_id  INTEGER REFERENCES proveedores(id),
    importe       INTEGER NOT NULL CHECK (importe > 0),
    activo        INTEGER NOT NULL DEFAULT 1
);
-- Resultado del prorrateo al cerrar: lo que le toca a cada unidad ese mes (todo en centavos)
CREATE TABLE IF NOT EXISTS liquidacion_unidad (
    liquidacion_id INTEGER NOT NULL REFERENCES liquidaciones(id),
    unidad_id      INTEGER NOT NULL REFERENCES unidades(id),
    saldo_anterior INTEGER NOT NULL,
    interes        INTEGER NOT NULL,
    por_grupo      TEXT    NOT NULL,      -- JSON {"A": 123400, "B": 5600}
    expensa        INTEGER NOT NULL,      -- suma de los grupos
    PRIMARY KEY (liquidacion_id, unidad_id)
);
CREATE TABLE IF NOT EXISTS pagos (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    unidad_id     INTEGER NOT NULL REFERENCES unidades(id),
    fecha         TEXT    NOT NULL,
    importe       INTEGER NOT NULL CHECK (importe > 0),   -- centavos
    modalidad     TEXT    NOT NULL DEFAULT 'efectivo',
    pago_quien    TEXT    NOT NULL DEFAULT '',
    nota          TEXT    NOT NULL DEFAULT '',
    recibo_numero INTEGER NOT NULL,                       -- correlativo por consorcio
    anulado       INTEGER NOT NULL DEFAULT 0,
    registrado_por TEXT   NOT NULL DEFAULT '',
    registrado_en  TEXT   NOT NULL DEFAULT ''
);
-- Datos de la administración (una sola fila): salen en el encabezado de las expensas
CREATE TABLE IF NOT EXISTS administracion (
    id               INTEGER PRIMARY KEY CHECK (id = 1),
    nombre           TEXT NOT NULL DEFAULT '',
    domicilio        TEXT NOT NULL DEFAULT '',
    horarios         TEXT NOT NULL DEFAULT '',
    cuit             TEXT NOT NULL DEFAULT '',
    telefono         TEXT NOT NULL DEFAULT '',
    email            TEXT NOT NULL DEFAULT '',
    inscripcion_rpa  TEXT NOT NULL DEFAULT '',   -- Registro Público de Administradores (CABA)
    situacion_fiscal TEXT NOT NULL DEFAULT ''
);
-- Rubros de gastos (numerados como pide la Ley 941): agrupan los gastos en la liquidación impresa
CREATE TABLE IF NOT EXISTS rubros (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    numero  INTEGER NOT NULL UNIQUE,
    nombre  TEXT    NOT NULL,
    activo  INTEGER NOT NULL DEFAULT 1
);
-- Gastos que se cobran a UNA sola unidad (no se reparten): ej. un arreglo en su departamento
CREATE TABLE IF NOT EXISTS gastos_particulares (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    liquidacion_id  INTEGER NOT NULL REFERENCES liquidaciones(id),
    unidad_id       INTEGER NOT NULL REFERENCES unidades(id),
    descripcion     TEXT    NOT NULL,
    importe         INTEGER NOT NULL CHECK (importe > 0)
);
-- Personal del consorcio (encargado, ayudante...)
CREATE TABLE IF NOT EXISTS encargados (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    consorcio_id  INTEGER NOT NULL REFERENCES consorcios(id),
    nombre        TEXT    NOT NULL,
    apellido      TEXT    NOT NULL,
    dni           TEXT    NOT NULL DEFAULT '',
    cuil          TEXT    NOT NULL DEFAULT '',
    telefono      TEXT    NOT NULL DEFAULT '',
    cargo         TEXT    NOT NULL DEFAULT '',
    categoria     TEXT    NOT NULL DEFAULT '',    -- categoría del encargado (convenio)
    fecha_ingreso TEXT,
    letra         TEXT    NOT NULL DEFAULT 'A',   -- grupo de gastos donde va su sueldo
    activo        INTEGER NOT NULL DEFAULT 1
);
-- Conceptos del sueldo de un mes: remuneración (suma), descuento (resta), aporte o contribución (suma)
CREATE TABLE IF NOT EXISTS sueldos (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    liquidacion_id  INTEGER NOT NULL REFERENCES liquidaciones(id),
    encargado_id    INTEGER NOT NULL REFERENCES encargados(id),
    tipo            TEXT    NOT NULL CHECK (tipo IN ('remuneracion','descuento','aporte')),
    concepto        TEXT    NOT NULL,
    importe         INTEGER NOT NULL CHECK (importe > 0)
);
-- Conceptos de sueldo que se repiten cada mes: se copian al abrir una liquidación
CREATE TABLE IF NOT EXISTS sueldos_fijos (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    encargado_id  INTEGER NOT NULL REFERENCES encargados(id),
    tipo          TEXT    NOT NULL CHECK (tipo IN ('remuneracion','descuento','aporte')),
    concepto      TEXT    NOT NULL,
    importe       INTEGER NOT NULL CHECK (importe > 0),
    activo        INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS juicios (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    consorcio_id     INTEGER NOT NULL REFERENCES consorcios(id),
    juzgado          TEXT    NOT NULL,
    expediente       TEXT    NOT NULL DEFAULT '',
    caratula         TEXT    NOT NULL,
    monto_reclamado  INTEGER,                    -- centavos
    objeto           TEXT    NOT NULL DEFAULT '',
    estado           TEXT    NOT NULL,
    visible          INTEGER NOT NULL DEFAULT 1  -- si sale en las expensas impresas
);
"""

RUBROS_INICIALES = (
    (1, "Remuneraciones al personal y cargas sociales"), (2, "Servicios públicos"), (3, "Abonos de servicios"),
    (4, "Mantenimiento de partes comunes"), (5, "Trabajos de reparaciones en unidades"), (6, "Gastos bancarios"),
    (7, "Gastos de limpieza"), (8, "Gastos de administración"), (9, "Pagos del período por seguros"), (10, "Otros"))


# Columnas que se sumaron después de crear la tabla: CREATE TABLE IF NOT EXISTS no las agrega a una base existente.
_COLUMNAS_NUEVAS = (
    ("consorcios", "clave_suterh", "TEXT NOT NULL DEFAULT ''"),           # clave del sindicato de encargados
    ("consorcios", "categoria", "TEXT NOT NULL DEFAULT ''"),              # categoría 1 a 4 (escala de sueldos del encargado)
    ("consorcios", "anio_construccion", "INTEGER"),
    ("consorcios", "superficies", "TEXT NOT NULL DEFAULT 'porcentual'"),  # porcentual: % por unidad; absoluta: m² por unidad
    ("consorcios", "tipo_interes", "TEXT NOT NULL DEFAULT 'simple'"),     # simple: no cobra interés sobre interés; compuesto: sí
    ("consorcios", "mostrar_inquilino", "INTEGER NOT NULL DEFAULT 0"),    # mostrar el inquilino en el reparto impreso
    ("consorcios", "envia_comprobantes", "INTEGER NOT NULL DEFAULT 0"),   # mandar comprobantes de gastos (cuando haya envío por email)
    ("consorcios", "imputa_a_deuda", "INTEGER NOT NULL DEFAULT 1"),       # el pago cancela primero la deuda más vieja
    ("consorcios", "liquida_mes_vencido", "INTEGER NOT NULL DEFAULT 1"),  # se liquidan los gastos del mes que ya pasó
    ("consorcios", "caja_inicial", "INTEGER NOT NULL DEFAULT 0"),         # centavos: plata en caja/banco al empezar a usar la app
    ("consorcios", "banco_titular", "TEXT NOT NULL DEFAULT ''"),          # datos para "Formas de pago"
    ("consorcios", "banco_nombre", "TEXT NOT NULL DEFAULT ''"),
    ("consorcios", "banco_sucursal", "TEXT NOT NULL DEFAULT ''"),
    ("consorcios", "banco_cuenta", "TEXT NOT NULL DEFAULT ''"),
    ("consorcios", "banco_cbu", "TEXT NOT NULL DEFAULT ''"),
    ("consorcios", "banco_alias", "TEXT NOT NULL DEFAULT ''"),
    ("consorcios", "codigo_pago", "TEXT NOT NULL DEFAULT ''"),            # código de pago electrónico
    ("gastos", "rubro_id", "INTEGER REFERENCES rubros(id)"),
    ("gastos", "periodo", "TEXT NOT NULL DEFAULT ''"),                    # a qué período corresponde la factura (texto libre)
    ("gastos_fijos", "rubro_id", "INTEGER REFERENCES rubros(id)"),
    ("liquidacion_unidad", "saldo_deudor", "INTEGER NOT NULL DEFAULT 0"), # total de la liquidación anterior
    ("liquidacion_unidad", "pagos", "INTEGER NOT NULL DEFAULT 0"),        # lo que pagó desde la liquidación anterior
    ("liquidacion_unidad", "particulares", "INTEGER NOT NULL DEFAULT 0"), # gastos cobrados solo a esa unidad
    ("liquidacion_unidad", "redondeo", "INTEGER NOT NULL DEFAULT 0"),     # para que el total quede en pesos enteros
    ("liquidaciones", "caja_anterior", "INTEGER"),                        # caja al cierre (centavos)
    ("liquidaciones", "caja_ingresos", "INTEGER"),
    ("liquidaciones", "caja_egresos", "INTEGER"),
    ("pagos", "liquidacion_id", "INTEGER REFERENCES liquidaciones(id)"),  # en qué liquidación se informó el pago
)


def _agregar_columnas(c: sqlite3.Connection) -> None:
    for tabla, columna, tipo in _COLUMNAS_NUEVAS:
        if columna not in {r[1] for r in c.execute(f"PRAGMA table_info({tabla})")}:
            c.execute(f"ALTER TABLE {tabla} ADD COLUMN {columna} {tipo}")
    # unidad_grupo tenía un tope de 100 que no sirve para superficies en m²: se rehace la tabla sin el tope
    sql = c.execute("SELECT sql FROM sqlite_master WHERE name='unidad_grupo'").fetchone()[0]
    if "porcentaje <= 100" in sql:
        c.execute("ALTER TABLE unidad_grupo RENAME TO unidad_grupo_vieja")
        c.executescript(ESQUEMA)
        c.execute("INSERT INTO unidad_grupo SELECT * FROM unidad_grupo_vieja")
        c.execute("DROP TABLE unidad_grupo_vieja")


def conectar() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


@contextmanager
def transaccion():
    """Una transacción por caso de uso: commit si termina bien, rollback si algo lanza."""
    conn = conectar()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def inicializar(con_ejemplos: bool = True) -> None:
    with transaccion() as c:
        c.executescript(ESQUEMA)
        _agregar_columnas(c)
        c.execute("INSERT OR IGNORE INTO administracion (id) VALUES (1)")
        if not c.execute("SELECT 1 FROM rubros").fetchone():
            c.executemany("INSERT INTO rubros (numero, nombre) VALUES (?,?)", RUBROS_INICIALES)
        if not c.execute("SELECT 1 FROM usuarios").fetchone():
            from .auth import hash_password
            salt, h = hash_password("admin")
            c.execute("INSERT INTO usuarios (usuario, nombre, password_hash, salt, es_admin, debe_cambiar) "
                      "VALUES ('admin', 'Administrador', ?, ?, 1, 1)", (h, salt))
    if con_ejemplos:
        from .ejemplos import cargar_si_vacia
        cargar_si_vacia()
