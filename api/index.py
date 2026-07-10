"""
Entrypoint de Vercel para el dashboard Flask.

Vercel invoca este archivo como una función serverless. Reexporta el
`app` WSGI de dashboard/app.py — no hace falta gunicorn, la runtime
Python de Vercel lo detecta automáticamente.

Todas las rutas del proyecto (login, /, /detalle/<id>, /editar/<id>,
/reiniciar, /eliminar, /ejecutar, /api/*, static, logout) siguen
funcionando exactamente igual porque no se toca el Flask.
"""
import os
import sys
from pathlib import Path

# Asegurar que el root del proyecto esté en el path para que
# `from dashboard.app import app` resuelva `modules/` y `config/`.
_PROYECTO_ROOT = Path(__file__).resolve().parent.parent
if str(_PROYECTO_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROYECTO_ROOT))

# Vercel Python runtime expone `app` (WSGI) como handler.
from dashboard.app import app  # noqa: E402
