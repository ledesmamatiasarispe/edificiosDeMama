#!/usr/bin/env bash
# Arranca Edificios de Mamá: la primera vez prepara el entorno de Python, después abre el navegador en la app.
# Cerrar esta ventana (o Ctrl+C) apaga la app. Los datos quedan en data/.
cd "$(dirname "$0")" || exit 1
if [ ! -x .venv/bin/python ]; then
  echo "Preparando la app por primera vez (puede tardar un par de minutos)..."
  python3 -m venv .venv && .venv/bin/pip install -q -r requirements.txt || { echo "No se pudo preparar la app."; exit 1; }
fi
PUERTO="${EDIF_PUERTO:-8095}"
( sleep 3; xdg-open "http://localhost:$PUERTO" >/dev/null 2>&1 ) &
exec .venv/bin/python -m app
