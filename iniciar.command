#!/usr/bin/env bash
# Mac: doble clic para arrancar Edificios de Mamá (todo el trabajo lo hace iniciar.py). Cerrar la ventana apaga la app.
cd "$(dirname "$0")" || exit 1
if ! command -v python3 >/dev/null 2>&1; then
  echo "Hace falta Python 3. Se baja gratis de https://www.python.org/downloads/"
  read -r -p "Apretá Enter para cerrar."
  exit 1
fi
exec python3 iniciar.py "$@"
