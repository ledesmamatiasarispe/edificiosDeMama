#!/usr/bin/env bash
# Linux: arranca Edificios de Mamá (todo el trabajo lo hace iniciar.py). Cerrar esta ventana apaga la app.
cd "$(dirname "$0")" || exit 1
if ! command -v python3 >/dev/null 2>&1; then
  echo "Hace falta Python 3. Instalalo con el gestor de programas de tu sistema (paquete python3)."
  read -r -p "Apretá Enter para cerrar."
  exit 1
fi
exec python3 iniciar.py "$@"
