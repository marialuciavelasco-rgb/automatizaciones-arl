import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# Rutas base
BASE_DIR = Path(__file__).parent.parent
DATA_DIR = BASE_DIR / "data"
EXCEL_INPUT_DIR = DATA_DIR / "excel_input"
PORTAL_OPTIONS_DIR = DATA_DIR / "portal_options"
FIREBASE_KEY_PATH = BASE_DIR / "config" / "firebase_key.json"

# En Lambda el filesystem es de solo lectura excepto /tmp
_IS_LAMBDA = bool(os.getenv("AWS_LAMBDA_FUNCTION_NAME"))
LOGS_DIR = Path("/tmp/logs") if _IS_LAMBDA else BASE_DIR / "logs"
SCREENSHOTS_DIR = Path("/tmp/screenshots") if _IS_LAMBDA else BASE_DIR / "screenshots"

# Portal ARL
ARL_URL = "https://arlonline.segurosbolivar.com/portal/arl/#/home"
ARL_USUARIO = os.getenv("ARL_USUARIO", "")
ARL_PASSWORD = os.getenv("ARL_PASSWORD", "")

# Firebase
FIREBASE_PROJECT_ID = os.getenv("FIREBASE_PROJECT_ID", "")

# Google Sheets (opcional — si no está configurado, se usa Excel local)
# GOOGLE_SHEETS_ID: el ID del spreadsheet, visible en la URL:
#   https://docs.google.com/spreadsheets/d/ESTE_ES_EL_ID/edit
GOOGLE_SHEETS_ID = os.getenv("GOOGLE_SHEETS_ID", "")

# GOOGLE_SHEETS_CREDENTIALS_PATH: ruta al JSON del service account.
# Por defecto busca config/sheets_key.json dentro del proyecto.
_sheets_creds_raw = os.getenv("GOOGLE_SHEETS_CREDENTIALS_PATH", "")
if _sheets_creds_raw:
    _p = Path(_sheets_creds_raw)
    GOOGLE_SHEETS_CREDENTIALS_PATH = _p if _p.is_absolute() else BASE_DIR / _p
else:
    GOOGLE_SHEETS_CREDENTIALS_PATH = BASE_DIR / "config" / "sheets_key.json"

# Playwright
HEADLESS = os.getenv("HEADLESS", "False").lower() == "true"
TYPING_DELAY_MS = int(os.getenv("TYPING_DELAY_MS", "120"))
TIMEOUT_MS = int(os.getenv("TIMEOUT_SECONDS", "30")) * 1000

# Fuzzy matching
CARGO_MATCH_AUTO = 90       # Score >= este: match automático
CARGO_MATCH_WARNING = 70    # Score >= este: acepta con advertencia
# Score < 70: requiere intervención humana

EPS_MATCH_MIN = 75
AFP_MATCH_MIN = 75
CIUDAD_MATCH_MIN = 80

# Reintentos
MAX_INTENTOS = 3
