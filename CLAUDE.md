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
- Correr: `.venv/bin/python -m app` -> http://localhost:8095 (variable de puerto y de base: ver "Configuración")
- Tests: `.venv/bin/python -m pytest -q` (todos tienen que pasar antes de dar algo por terminado)
- Build: no hay (el frontend se sirve tal cual). El .exe de Windows es opcional y se decide más adelante.

### Configuración (variables de entorno, solo nombres)
En la base se llaman `MANT_PUERTO`, `MANT_DB`, `MANT_NAVEGADOR`, `MANT_REPO`, `MANT_API_ACTUALIZACION`.
Al adaptar, renombrarlas con prefijo propio (propuesta: `EDIF_PUERTO`, `EDIF_DB`, …) y documentarlas acá.
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
- La base guarda sus datos en `data/` (base `.db`, adjuntos). El `.gitignore` actual de este repo **no** ignora
  `data/` ni `*.db`: hay que agregarlos antes del primer commit con código (avisarle al usuario y pedir permiso).
- Validar siempre en `servicios.py`, nunca solo en la pantalla. Cada regla de negocio nueva lleva su test.

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
| Referencia ACON (PRIVADO) | `/home/matias/Escritorio/sistema_acon_copia` — páginas del sistema ACON guardadas como HTML; al terminar la descarga queda un `indice.json` que lista las páginas guardadas. Solo lectura local. |

## 6. Pendiente: análisis detallado de ACON (pantallas y flujos)

_Pendiente._ Recorrer `sistema_acon_copia` (empezar por `indice.json`) y anotar acá, **sin datos personales**:
menú y lista de pantallas, qué hace cada una, flujos principales (cargar gastos -> liquidar -> emitir expensas ->
registrar pagos -> recibos -> morosos), reportes e impresiones, y cosas que conviene mejorar.

## 7. Pendiente: modelo de datos definitivo

_Pendiente._ Borrador inicial de tablas a validar contra ACON:
`consorcios`, `unidades` (coeficiente), `personas`, `unidad_personas` (propietario/inquilino, desde-hasta),
`rubros`, `gastos`, `liquidaciones`, `liquidacion_items`, `pagos`, `recibos`, `movimientos` (cuenta corriente),
`config` (tasa de interés, vencimientos), `usuarios`, `sesiones`.

## 8. Pendiente: plan de trabajo

_Pendiente._ Propuesta de orden: (1) esqueleto copiado de la base con login y usuarios, dominio de mantenimiento
borrado y tests pasando; (2) consorcios y unidades; (3) propietarios/inquilinos; (4) gastos; (5) liquidación de
expensas; (6) pagos y cuenta corriente; (7) recibos; (8) morosos e intereses; (9) reportes/impresión.

## 9. Bitácora / decisiones

Agregar una línea por decisión, la más nueva abajo: `AAAA-MM-DD — decisión — motivo`.

- 2026-11-10 — Se toma super-duper-lamp (FastAPI + SQLite + JS puro) como base técnica — es del usuario, simple, probado y sin build.
- 2026-11-10 — sistema_acon_copia es solo referencia local de pantallas/flujos; nunca se copia ni se sube su contenido — contiene datos privados.
