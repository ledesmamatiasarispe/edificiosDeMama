# CLAUDE.md — Edificios de Mamá

Memoria del proyecto para agentes de IA. Leela entera antes de tocar nada.
Si una decisión cambia algo de lo que dice acá, actualizá este archivo en el mismo cambio.

---

## 1. Sobre el usuario

- **No lee código**. Todo lo técnico (escribir, probar, compilar, subir) lo hacen agentes de IA.
- Hablale en **español simple**, rioplatense, **frases cortas y sin jerga**. Si hace falta un término técnico, explicalo en una línea.
- Respuestas breves: qué se hizo, si funcionó, y qué decisión necesita de él (si hay alguna). Nada de bloques de código en la respuesta.
- No le pidas que revise código. Las pruebas las hace el agente y le cuenta el resultado.
- Antes de algo irreversible (borrar datos, subir a GitHub, migrar la base real) preguntale y explicá el efecto en criollo.

## 2. Objetivo del proyecto

Una versión propia de un sistema web de **administración de consorcios**, inspirada en el sistema PHP "**sistema ACON**".
Se usa como referencia de pantallas y flujos, no se copia su código ni sus datos.

Conceptos del dominio (glosario):

| Concepto | Qué es |
|---|---|
| Consorcio / Edificio | El edificio administrado. Tiene sus unidades, gastos y liquidaciones. |
| Unidad funcional (UF) | Departamento, local o cochera. Tiene un **porcentaje / coeficiente** de participación en los gastos. |
| Propietario | Dueño de una o más UF. Es quien en principio debe las expensas. |
| Inquilino | Ocupa la UF; puede pagar expensas en nombre del propietario. |
| Gastos | Lo que gasta el consorcio en el mes (sueldos, servicios, mantenimiento, etc.), por rubro. |
| Expensas / Liquidación | Reparto mensual de los gastos entre las UF según su coeficiente; genera lo que debe cada UF. |
| Pagos | Lo que paga cada UF. Se imputan contra su deuda. |
| Cuenta corriente | Historial por UF: liquidaciones (debe), pagos (haber), intereses, saldo. |
| Morosos | UF con saldo vencido; puede haber intereses por mora. |
| Recibos | Comprobante de cada pago (imprimible / PDF). |

## 3. Base técnica: super-duper-lamp

El proyecto arranca a partir de **super-duper-lamp** (app "UltraMantenimiento", del mismo usuario):
una app web de mantenimiento preventivo de una planta industrial. Copia local: `/home/matias/Escritorio/super-duper-lamp`
(no subir nada a ese repo). Su memoria detallada está en `CLAUDEREADME.txt` de ese repo: leerla para los detalles.

### Stack
- **Backend:** Python 3.11+ (en esta PC hay 3.14), **FastAPI** + **uvicorn**, `python-multipart`.
- **Base de datos:** **SQLite** con `sqlite3` directo (sin ORM), `PRAGMA foreign_keys = ON`, esquema en un solo texto.
- **Frontend:** SPA en **JavaScript puro**, sin frameworks ni compilación (`index.html` + `app.js` + `styles.css`).
- **Tests:** pytest + httpx (`TestClient` de FastAPI, base nueva por test).
- **Empaquetado (opcional):** PyInstaller para un .exe de Windows + GitHub Actions que publica releases.

### Estructura de la base (a replicar)
```
app/
  __main__.py   arranque (uvicorn)
  main.py       rutas HTTP DELGADAS: pasan el body al servicio, sin lógica
  servicios.py  ÚNICA puerta a datos y reglas; cada caso de uso = una transacción (`with transaccion()`)
                ErrorDeNegocio -> 400, NoEncontrado -> 404
  db.py         esquema (CREATE TABLE IF NOT EXISTS), migraciones livianas, datos de ejemplo
  auth.py       login con token Bearer, sesiones en la base, contraseñas con PBKDF2, rol admin
  usuarios.py   alta/baja de usuarios (siempre queda un admin)
frontend/       index.html, app.js (VISTAS.<pantalla>), styles.css, ayuda.js (tour guiado)
tests/          pytest
herramientas/   scripts sueltos (compilar, cargar datos)
```

### Comandos (Linux, esta PC)
- Instalar: `python3 -m venv .venv && .venv/bin/pip install -r requirements.txt -r requirements-dev.txt`
- Correr: `./iniciar.sh` o `.venv/bin/python -m app` -> http://localhost:8095 (variable de puerto y de base: ver "Configuración")
- Tests: `.venv/bin/python -m pytest -q` (todos tienen que pasar antes de dar algo por terminado)
- Build: no hay (el frontend se sirve tal cual). El .exe de Windows es opcional y se decide más adelante.

### Configuración (variables de entorno, solo nombres)
- `EDIF_PUERTO`: puerto de la app (por defecto 8095).
- `EDIF_DB`: archivo de la base (por defecto `data/edificios.db`). Para pruebas, apuntarlo a otro archivo.
Nunca escribir valores secretos en el código ni en este archivo.

### Qué se reusa, qué se adapta, qué se descarta
- **Reusar tal cual (o casi):** `auth.py` (sesiones + PBKDF2 + admin), `usuarios.py`, `db.py` (conexión,
  `transaccion()`, patrón de migraciones con `_agregar_columnas`), el patrón rutas-delgadas/servicios,
  helpers del frontend (`api()`, `$()`, `esc()`, `abrirModal()`, `enviar()`, `avisar()`, navegación `irA()`),
  `styles.css` como punto de partida, la estructura de tests (fixture con admin logueado).
- **Adaptar:** el login es por **legajo** (número de empleado) -> pasar a usuario/email; textos, logo y nombre de la app;
  `ayuda.js` (tour guiado) con pasos nuevos; la regla "dar de baja ≠ eliminar" sirve igual para UF, propietarios, etc.
- **Descartar:** todo el dominio de mantenimiento (equipos, instructivos, secciones, plan/tareas, cronograma,
  horómetros, correctivos, `calendario.py`, `herramientas/cargar_fichas.py`, `instructivo_ejemplo.py`).
  El actualizador desde GitHub Releases (`actualizador.py`) y la compilación a .exe: dejar afuera hasta decidir
  cómo se va a instalar/hostear la app.

### Ojo al adaptar
- La base está pensada para **Windows** (`iniciar.bat`, rutas `.venv\Scripts\`, Edge headless). Acá se usa Linux.
- Dinero: no usar `float` para importes. Guardar en **centavos (entero)** o `Decimal`. Aceptar coma decimal al ingresar.
- La base guarda sus datos en `data/`. El `.gitignore` ya excluye `data/` y `*.db`.
- Validar siempre en `servicios.py`, nunca solo en la pantalla. Cada regla de negocio nueva lleva su test.

## 3b. Estado actual de la app (versión 0.1.0, 2026-11-10)

Funciona con **datos de ejemplo inventados** (se cargan solos si la base no tiene consorcios: `app/ejemplos.py`).
Entrar con usuario `admin` y contraseña `admin` (pide cambiarla la primera vez).

```
app/
  __main__.py   arranque (EDIF_PUERTO, por defecto 8095)
  main.py       rutas HTTP delgadas
  db.py         esquema SQLite + conexión (EDIF_DB, por defecto data/edificios.db) + crea el admin
  validar.py    ErrorDeNegocio/NoEncontrado y validaciones (pesos() convierte "12.500,50" a centavos)
  servicios.py  consorcios, grupos de gastos, unidades (% por grupo), personas, proveedores, gastos fijos
  expensas.py   liquidaciones, prorrateo, cierre/reapertura, pagos y recibos, cuenta corriente, saldos, morosos
  auth.py, usuarios.py   login por nombre de usuario, PBKDF2, contraseña provisoria, siempre un admin
  ejemplos.py   datos de ejemplo ficticios
frontend/       index.html, app.js (VISTAS.<pantalla>), styles.css, icono.svg
tests/          pytest (base temporal por test)
```

Reglas de cálculo (ver docstring de `expensas.py`):
- Al **cerrar** una liquidación se reparte cada grupo según los % de las unidades activas (tienen que sumar 100;
  si no, no deja cerrar). Los centavos del redondeo van a las de mayor fracción: la suma da exacta.
- Se guarda una "foto" por unidad: saldo anterior, interés (solo sobre la deuda **ya vencida**) y expensa del mes.
- La cuenta corriente no se guarda: sale de liquidaciones cerradas (debe) y pagos no anulados (haber).
- Un pago no se borra: se **anula**. Recibos con número correlativo por consorcio.
- Solo una liquidación abierta por consorcio; se reabre solo la última; al abrir se copian los gastos fijos.
- Imprimir/PDF: se abre una ventana con la hoja y el diálogo de impresión del navegador.
- Datos del consorcio (igual que la pantalla "Editar Consorcio" de ACON): nombre*, dirección*, localidad, CP, CUIT,
  email de envío/respuesta*, clave SUTERH, categoría 1–4, año de construcción, configuración de superficies*
  (porcentual = % por unidad que suma 100; absoluta = m² por unidad, se reparte proporcional), interés por mora* (% mensual;
  ACON lo pide como fracción, ej. 0.04 = 4%), tipo de interés* (simple: no cobra interés sobre intereses impagos,
  tomando que los pagos cancelan primero intereses; compuesto: sobre todo lo vencido), nota de expensas, mostrar
  inquilino en el reparto, envía comprobantes (guardado, sin uso hasta que haya email), imputa pago a deuda*
  (guardado; hoy el saldo es uno solo), liquida mes vencido* (guardado, solo informativo por ahora).
- Columnas nuevas de tablas existentes: agregarlas en `_COLUMNAS_NUEVAS` de `db.py` (se suman solas a bases viejas).
- Liquidación completa tipo Ley 941 (v0.2): `administracion` (1 fila, encabezado), `rubros` (1–10 iniciales; gastos y gastos
  fijos tienen rubro y período), `encargados` + `sueldos_fijos` (se copian al abrir) + `sueldos` del mes
  (remuneración suma, descuento resta, aporte suma; van al grupo del encargado), `gastos_particulares` (una sola unidad),
  `juicios` (visible = sale impreso). `liquidacion_unidad` guarda además saldo_deudor (total de la anterior), pagos
  (pagos informados en esa liquidación: `pagos.liquidacion_id` se marca al cerrar y se borra al reabrir), particulares
  y redondeo (total a pesos enteros). Ajustes = deuda − (saldo deudor − pagos): muestra anulaciones posteriores.
  Caja por liquidación: caja_anterior (de la anterior o `consorcios.caja_inicial`), ingresos = pagos informados,
  egresos = gastos + sueldos + particulares. Estado patrimonial = caja final + total a cobrar.
- Actualización automática (v1.0): `app/actualizador.py` consulta el último release de GitHub (`app/version.py`: VERSION
  y REPO; `EDIF_REPO` vacío la apaga, así corren los tests). Al admin se le pregunta al entrar; "Ahora no" = 7 días
  (tabla `config`). Instala: baja .zip + .sha256, copia la base (`data/edificios_antes_de_v<versión>.db`), reemplaza
  app/, frontend/, herramientas/ y archivos sueltos (PARTES) sin tocar data/ ni .venv/, instala dependencias si
  cambiaron y se reinicia con `os.execv` (mismo puerto). Si es un repo git con cambios sin commitear en app/ o
  frontend/, no instala. **Publicar una versión:** subir VERSION en `app/version.py`, escribir `NOVEDADES.md`,
  commitear, `git tag vX.Y.Z && git push origin vX.Y.Z`; el workflow `.github/workflows/release.yml` corre los tests,
  arma el paquete (`herramientas/empaquetar.py`) y publica el release.
- Arranque: `./iniciar.sh` (crea .venv la primera vez y abre el navegador).
- Impresión: `imprimirLiquidacion()` arma la hoja A4 apaisada (`@page apaisada`) con las secciones del PDF de ACON.

Pruebas de pantalla: no hay navegador en el sistema para esto; se usó Playwright + Chromium instalados en un
entorno aparte del scratchpad (no es dependencia del proyecto).

## 4. Reglas (no romper)

- **Nunca** subir a git: contraseñas, tokens, `.env`, bases de datos reales, copias de seguridad.
- **Nunca** usar ni copiar datos de `sistema_acon_copia`: tiene **datos privados de personas reales**
  (nombres, deudas, direcciones). No copiarlo, moverlo ni modificarlo; no ponerlo en el repo, en tests,
  en datos de ejemplo, en este archivo ni en mensajes de commit. Solo se **lee localmente** como referencia
  de qué pantallas y flujos tiene ACON.
- Datos de ejemplo y de prueba: **inventados** (nombres ficticios, montos redondos).
- Nunca probar contra la base real: para pruebas, otra base temporal y otro puerto.
- Antes de migrar una base con datos reales, hacer copia (`data/<base>_antes_de_<cambio>.db`).
- Commit/push solo cuando el usuario lo pida. Mensajes de commit en español.
- Editar archivos con las herramientas de edición (no heredocs con acentos: rompen la codificación).

## 5. Rutas

| Qué | Dónde |
|---|---|
| Este proyecto (repo local) | `/home/matias/Escritorio/edificiosDeMama` |
| Repo remoto | https://github.com/ledesmamatiasarispe/edificiosDeMama.git |
| App base | `/home/matias/Escritorio/super-duper-lamp` (memoria en `CLAUDEREADME.txt`) |
| Referencia ACON (PRIVADO) | `/home/matias/Escritorio/sistema_acon_copia` — páginas del sistema ACON guardadas como HTML; descarga parcial (~600 páginas), sin índice. Solo lectura local. |

## 6. Análisis de ACON (pantallas y flujos)

Relevado el 2026-11-10 sobre ~600 páginas guardadas (la descarga se cortó a propósito: el resto eran
repeticiones de la misma pantalla para cada unidad/persona). No hay `indice.json`. Solo nombres de campos.

**Menú de ACON:** Inicio (resumen: consorcios, expensas abiertas, cobros del día, recibos emitidos) ·
Configuración (consorcios, administrador, usuarios, mi cuenta) · Proveedores (listado, rubros) ·
Expensas (una entrada por consorcio) · Caja (cobro de expensas, boletas de pago, egresos/pagos mensuales,
recibos, cheques) · Agenda · Reportes (morosos, cuenta corriente por unidad, comprobantes de gastos,
últimos saldos por consorcio, balance, ingresos adicionales).

**Consorcio:** nombre*, dirección*, localidad, CP, CUIT, email de envío*, clave SUTERH, categoría,
año de construcción, configuración de superficies*, % interés por mora*, tipo de interés* (simple/compuesto),
nota para expensas, mostrar inquilino en prorrateo, envía comprobantes de gastos, imputa pago a deuda*
(el pago cancela primero la deuda vieja), liquida mes vencido*.
Sub-secciones por consorcio: UF, UC, encargados, propietarios, inquilinos, emails adicionales,
datos bancarios (titular, banco, sucursal, nº cuenta, CBU/CVU), caja inicial, juicios (juzgado*, expediente,
carátula*, monto reclamado, objeto, estado*, visible), activos y pasivos (nombre*, descripción, valor*, fecha).

**Unidad funcional (UF):** nombre UF* (ej. "UF 3"), piso/depto, nombre interno, nº catastro,
superficie/porcentaje*, tipo* (vivienda, local, cochera), propietario, inquilino, unidades complementarias.
**UC (unidad complementaria):** baulera, etc., asociada a una UF.

**Grupos de gastos (A, B, C, …, hasta 5):** cada grupo tiene su propio **porcentaje por UF** (y qué UF participan:
se eligen por tipo — todas las viviendas, todos los locales — o una por una). Así un gasto tipo B (ej. ascensor)
se reparte solo entre las UF que lo usan. El grupo A suele ser el general con el coeficiente principal.

**Propietario:** nombre*, apellido*, DNI, CUIT, nacimiento, estado civil, profesión, varios teléfonos y celulares,
email, dirección, localidad, CP, UF. **Inquilino:** igual, más corto. **Encargado:** nombre*, apellido*, DNI,
CUIL, contacto, fecha de ingreso, cargo, categoría, grupo de gasto*. Remuneraciones del encargado: concepto*,
descripción*, monto, repetición*, estado*.

**Gastos:** grupo*, proveedor, descripción*, monto, comprobante. Hay **gastos reiterativos** (se repiten cada mes:
grupo*, proveedor, descripción*, tipo*, monto, repetición*, estado*) y **previsiones** (fondos de reserva, mismo formato).

**Expensas (liquidación mensual):** lista por consorcio con fecha y estado (abierta / cerrada). Se abre una
nueva (nota opcional), se cargan los gastos del mes, se cierra y genera el PDF de expensas y las boletas.
Prorrateo por UF: deuda anterior, interés, gastos A, gastos B, gastos C, subtotal, redondeo, total, adeuda.

**Cobro de expensas:** se elige la UF (por número o nombre del propietario); se muestra el prorrateo; se cargan
uno o más pagos: modalidad (efectivo, transferencia, …), fecha de pago, monto, nota, "pagó" (quién), comprobante adjunto.
Genera **recibo** (fecha, expensa, UF, propietario, modo de pago, monto, nº de recibo, envío por email).
**Recibo particular:** comprobante que NO entra en la caja del consorcio.

**PDF de expensas de ACON (liquidación mensual, A4 apaisado, 4 páginas).** Ejemplo real guardado SOLO en
`sistema_acon_copia/archivos/` (privado). Estructura, en orden (sigue el art. 10 de la Ley 941 de CABA):
1. Encabezado "Liquidación de mes: <mes año>". Dos columnas: **Administración** (nombre, domicilio, horarios,
   CUIT, teléfono, inscripción R.P.A., situación fiscal) y **Consorcio** (nombre, domicilio, localidad, CUIT, clave SUTERH).
2. **Remuneraciones al personal** (inc. d): encargado (nombre, CUIL, cargo, período, categoría del edificio y del
   encargado), detalle de sueldo, descuentos, aportes y contribuciones (F.931, sindicato), con columnas Gastos A/B/C y total.
   Es el "rubro 1"; muestra el % que representa sobre el total.
3. **Pagos por suministros, servicios, abonos y seguros** (inc. e y f), agrupados por **rubro** numerado
   (servicios públicos, abonos de servicios, gastos bancarios, gastos de administración, seguros, otros…).
   Cada gasto: concepto/proveedor, período, pago, Gastos A, B, C, total. Cada rubro: total y % del total general.
   Fila TOTAL con 100% y totales por grupo.
4. **Estado de cuentas y prorrateo**: por unidad (UF y también UC): UF, Dpto, propietario, saldo deudor (lo que
   debía), pagos (lo que pagó), anulaciones y ajustes, deuda (lo que quedó), interés por mora, % A, gastos A,
   % B, gastos B, **G PART** (gastos particulares de esa unidad), total gastos, **RED.** (redondeo a pesos enteros),
   **TOTAL** (entero). Fila de totales. Debajo: "Tasa de interés punitorio aplicada".
5. **Detalle de egresos e ingresos** (inc. c, la caja): saldo anterior, ingresos por expensas en término, por
   expensas adeudadas, por intereses, adicionales; egresos por gastos A, B, C y particulares; saldo final.
6. **Estado patrimonial**: disponibilidades al cierre, expensas a cobrar, patrimonio neto.
7. **Datos de juicios** (inc. h). 8. **Notas** (qué es cada grupo: "A: todas las unidades", "B: extraordinarias").
9. **Detalle de gastos particulares por unidad** (ej. un gasto cobrado solo a una UF).
10. **Formas de pago**: depósito/transferencia con titular, banco, sucursal, CBU, alias, nº de cuenta.

Le falta a la app para imprimir igual: datos de la administración, rubros en los gastos, gastos particulares
por unidad, columna de pagos del mes en el prorrateo, redondeo a pesos enteros, caja (ingresos/egresos y saldo),
estado patrimonial, juicios, datos bancarios, sueldos del encargado.

**Reportes:** morosos (consorcio, tipo, unidad, propietarios, mora, último pago, nota), cuenta corriente por
unidad (desde una expensa), últimos saldos por consorcio, comprobantes de gastos, balance.

**Flujo principal:** configurar consorcio y UF (con porcentajes por grupo) -> cargar propietarios/inquilinos ->
abrir expensa del mes -> cargar gastos (más los reiterativos) -> cerrar y emitir (PDF + boletas) ->
registrar cobros -> recibos -> intereses por mora sobre deuda -> reportes.

**Para mejorar respecto de ACON:** listas con paginado de 10 filas (mostrar todo con búsqueda),
pantallas de edición duplicadas de las de lectura, demasiados campos de teléfono.

## 7. Modelo de datos (borrador validado contra ACON)

`consorcios` (datos + config: interés mora %, tipo de interés, imputa a deuda, liquida mes vencido) ·
`unidades` (consorcio, nombre, piso, depto, tipo, superficie, unidad_padre para UC, activa) ·
`grupos_gasto` (consorcio, letra A–E, nombre) · `unidad_grupo` (unidad, grupo, porcentaje — los % de un grupo suman 100) ·
`personas` · `unidad_personas` (rol propietario/inquilino, desde, hasta) · `encargados` · `proveedores` · `rubros` ·
`gastos` (liquidación, grupo, proveedor, rubro, descripción, importe_centavos, comprobante) ·
`gastos_reiterativos` · `liquidaciones` (consorcio, período, estado abierta/cerrada, vencimiento, nota) ·
`liquidacion_unidad` (deuda anterior, interés, importe por grupo, redondeo, total) · `pagos` (unidad, fecha,
modalidad, importe, quién pagó, nota) · `recibos` (pago, número) · `cuentas_bancarias` · `juicios` ·
`usuarios`, `sesiones`. Importes siempre en centavos (entero).

## 8. Plan de trabajo

Hecho en 0.1.0: login y usuarios, consorcios, grupos de gastos, unidades con %, propietarios/inquilinos,
proveedores, gastos fijos, liquidación (abrir, gastos, vista previa, cerrar, reabrir), cobros con recibo,
anular pago, cuenta corriente, saldos, morosos, impresión de expensas/recibo/cuenta corriente.

Hecho en 0.2: liquidación impresa como ACON (Ley 941): administración, rubros, sueldos del encargado, gastos
particulares, pagos del período, redondeo, caja, estado patrimonial, juicios y datos bancarios.

Pendiente (en orden propuesto): (1) que la mamá/usuario lo pruebe y decir qué falta o qué cambia;
(2) boleta/aviso de pago por unidad para repartir; (3) envío por email; (4) separar ingresos de caja en
"expensas en término / adeudadas / intereses" como ACON; (5) ingresos adicionales; (6) reportes de gastos y balance; (7) tour de ayuda;
(8) copias de seguridad automáticas de la base; (9) migrar los datos reales desde ACON (al final).

## 9. Bitácora / decisiones

Agregar una línea por decisión, la más nueva abajo: `AAAA-MM-DD — decisión — motivo`.

- 2026-11-10 — Se toma super-duper-lamp (FastAPI + SQLite + JS puro) como base técnica — es del usuario, simple, probado y sin build.
- 2026-11-10 — sistema_acon_copia es solo referencia local de pantallas/flujos; nunca se copia ni se sube su contenido — contiene datos privados.
- 2026-11-10 — La descarga de ACON se cortó en ~600 páginas — el resto era repetición con datos personales; alcanza para ver todas las pantallas.
- 2026-11-10 — Primero se construye la app con datos de ejemplo inventados; los datos reales se migran recién cuando funcione bien.
- 2026-11-10 — Versión 0.1.0 armada: login por nombre de usuario (no legajo), importes en centavos, cuenta corriente calculada (no guardada), interés solo sobre deuda vencida.
- 2026-11-10 — Consorcio con todos los campos de ACON (captura del usuario). Interés simple/compuesto y superficies porcentual/absoluta ya afectan el cálculo.
- 2026-11-10 — v0.2: impresión de expensas igual a la de ACON (dos tandas pedidas por el usuario: formato + encargado/juicios). Redondeo a pesos enteros siempre.
- 2026-11-10 — v1.0.0: actualización automática desde GitHub Releases (adaptada a Linux, desde código fuente, sin compilar). Probada de punta a punta con un release falso local.
