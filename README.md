# Edificios de Mamá

Sistema propio de administración de consorcios: expensas, cobros, cuentas corrientes y morosos.
Funciona en Windows, Linux y Mac.

## Cómo arrancarlo

**Lo más fácil (sin instalar nada):** bajar de [Releases](https://github.com/ledesmamatiasarispe/edificiosDeMama/releases)
el .zip de tu sistema (`-windows`, `-linux` o `-macos`), descomprimirlo y abrir `EdificiosDeMama` (en Windows,
`EdificiosDeMama.exe`). En Mac, la primera vez: clic derecho > Abrir.

**Desde el código fuente (con Python):** bajar el .zip sin sistema en el nombre, descomprimirlo y:

- **Windows:** doble clic en `iniciar.bat`.
- **Mac:** doble clic en `iniciar.command` (la primera vez: clic derecho > Abrir, para que el Mac lo permita).
- **Linux:** doble clic en `iniciar.sh`, o `python3 iniciar.py`. Con `python3 iniciar.py --acceso-directo` queda un ícono
  en el menú de aplicaciones y en el escritorio.

La primera vez tarda un par de minutos (prepara lo que necesita). Después abre el navegador en http://localhost:8095.
Usuario `admin`, contraseña `admin` (pide cambiarla). Trae datos de ejemplo inventados. Cerrar la ventana apaga la app.
Los datos quedan en la carpeta `data/`. Las versiones nuevas se instalan solas desde la app (Administración).

## Desarrollo

Pruebas automáticas: `.venv/bin/python -m pip install -r requirements-dev.txt && .venv/bin/python -m pytest -q`
