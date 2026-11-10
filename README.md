# Edificios de Mamá

Sistema propio de administración de consorcios, en desarrollo.

## Cómo arrancarlo (Linux)

```
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt -r requirements-dev.txt
.venv/bin/python -m app
```

Después abrir http://localhost:8095 en el navegador. La primera vez entra con usuario `admin` y contraseña `admin`
(pide cambiarla) y trae datos de ejemplo inventados.

Pruebas automáticas: `.venv/bin/python -m pytest -q`
