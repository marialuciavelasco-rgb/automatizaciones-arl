"""
Módulo: sheets_reader.py
Lee el Google Sheet de Notificaciones Nómina Buk.

⚠️  SOLO LECTURA — este módulo NUNCA escribe en el Sheet.
    Todo el estado se gestiona en Firebase.
"""
import re
import pandas as pd
from datetime import datetime
from loguru import logger

import gspread
from google.oauth2.service_account import Credentials

from config.settings import GOOGLE_SHEETS_ID, GOOGLE_SHEETS_CREDENTIALS_PATH


# Solo lectura — nunca escritura
_SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets.readonly",
    "https://www.googleapis.com/auth/drive.readonly",
]

_HOJAS_EXCLUIDAS = {
    "NVScriptsProperties",
    "DO NOT DELETE - AutoCrat Job Se",
}

_MESES = {
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4,
    "mayo": 5, "junio": 6, "julio": 7, "agosto": 8,
    "septiembre": 9, "octubre": 10, "noviembre": 11, "diciembre": 12,
}


# ─────────────────────────────────────────────────────────────────────
# CLIENTE
# ─────────────────────────────────────────────────────────────────────

def _get_client() -> gspread.Client:
    """Crea un cliente gspread autenticado con service account (solo lectura)."""
    import os, json
    sheets_key_json = os.getenv("SHEETS_KEY_JSON", "")
    if sheets_key_json:
        cred_dict = json.loads(sheets_key_json)
        creds = Credentials.from_service_account_info(cred_dict, scopes=_SCOPES)
    else:
        creds = Credentials.from_service_account_file(
            str(GOOGLE_SHEETS_CREDENTIALS_PATH), scopes=_SCOPES
        )
    return gspread.authorize(creds)


# ─────────────────────────────────────────────────────────────────────
# DETECCIÓN DE HOJA MÁS RECIENTE
# ─────────────────────────────────────────────────────────────────────

def _encontrar_hoja_mas_reciente(hojas: list) -> str:
    """
    Entre las hojas válidas, detecta la más reciente buscando
    nombres del tipo 'Abril 2026', 'Marzo 2025', etc.
    Mismo algoritmo que excel_reader.encontrar_hoja_mas_reciente().
    """
    hojas_validas = [h for h in hojas if h not in _HOJAS_EXCLUIDAS]
    if not hojas_validas:
        raise RuntimeError("No se encontraron hojas válidas en el spreadsheet")

    hojas_con_fecha = []
    for hoja in hojas_validas:
        partes = hoja.strip().lower().split()
        anio = None
        mes = None
        for p in partes:
            if p.isdigit() and len(p) == 4:
                anio = int(p)
            if p in _MESES:
                mes = _MESES[p]
        if anio and mes:
            hojas_con_fecha.append((datetime(anio, mes, 1), hoja))

    if hojas_con_fecha:
        hojas_con_fecha.sort(key=lambda x: x[0])
        return hojas_con_fecha[-1][1]

    # Fallback: última hoja en el orden del spreadsheet
    return hojas_validas[-1]


# ─────────────────────────────────────────────────────────────────────
# UTILIDADES PÚBLICAS
# ─────────────────────────────────────────────────────────────────────

def sheets_disponible() -> bool:
    """
    Verifica si Google Sheets está configurado (sin hacer llamadas de red).
    Acepta credenciales como variable de entorno SHEETS_KEY_JSON o como archivo en disco.
    """
    import os
    if not GOOGLE_SHEETS_ID:
        return False
    if os.getenv("SHEETS_KEY_JSON"):
        return True
    if not GOOGLE_SHEETS_CREDENTIALS_PATH:
        return False
    if not GOOGLE_SHEETS_CREDENTIALS_PATH.exists():
        return False
    return True


def listar_hojas() -> list:
    """Lista todas las hojas válidas del spreadsheet (sin las internas de Buk)."""
    client = _get_client()
    sh = client.open_by_key(GOOGLE_SHEETS_ID)
    return [ws.title for ws in sh.worksheets() if ws.title not in _HOJAS_EXCLUIDAS]


# ─────────────────────────────────────────────────────────────────────
# LECTURA PRINCIPAL
# ─────────────────────────────────────────────────────────────────────

def leer_sheets(nombre_hoja: str = None) -> dict:
    """
    Lee el Google Sheet y retorna el mismo formato que excel_reader.leer_excel():

        {
            "registros":   [...],   # lista de dicts con datos limpios
            "errores":     [...],   # errores por fila
            "hoja_usada":  "...",   # nombre de la pestaña leída
            "total_filas": N,       # total filas con datos (sin encabezado)
        }

    ⚠️  NUNCA escribe en el Sheet — todo el estado va a Firebase.
    Las filas con columna ARL ya rellena se omiten automáticamente
    (misma lógica que excel_reader._procesar_fila).
    """
    if not sheets_disponible():
        raise RuntimeError(
            "Google Sheets no configurado. "
            "Verifica GOOGLE_SHEETS_ID y GOOGLE_SHEETS_CREDENTIALS_PATH en .env"
        )

    logger.info(f"Conectando a Google Sheets ID: {GOOGLE_SHEETS_ID}")
    client = _get_client()
    sh = client.open_by_key(GOOGLE_SHEETS_ID)

    # Seleccionar hoja
    todas_las_hojas = [ws.title for ws in sh.worksheets()]
    hojas_validas = [h for h in todas_las_hojas if h not in _HOJAS_EXCLUIDAS]

    if nombre_hoja is None:
        nombre_hoja = _encontrar_hoja_mas_reciente(hojas_validas)

    logger.info(f"Hoja seleccionada: '{nombre_hoja}'")
    ws = sh.worksheet(nombre_hoja)

    # get_all_values() — solo lectura, garantizado por los SCOPES
    todos_los_valores = ws.get_all_values()

    if not todos_los_valores or len(todos_los_valores) < 2:
        logger.warning("El Sheet está vacío o solo tiene encabezados")
        return {
            "registros":   [],
            "errores":     [],
            "hoja_usada":  nombre_hoja,
            "total_filas": 0,
        }

    # Primera fila = encabezados; resto = datos
    headers = [str(h).strip() for h in todos_los_valores[0]]
    filas = todos_los_valores[1:]

    # Construir DataFrame para reutilizar _procesar_fila de excel_reader
    df = pd.DataFrame(filas, columns=headers, dtype=str)
    df = df.replace("", pd.NA).dropna(how="all").fillna("")

    logger.info(f"Filas con datos: {len(df)}")

    registros = []
    errores = []
    columnas = df.columns.tolist()

    for idx, row in df.iterrows():
        fila_num = idx + 2  # +2: índice 0-based + fila de encabezado
        try:
            reg, errs = _procesar_fila(row, columnas, fila_num)
            if reg:
                registros.append(reg)
            if errs:
                errores.extend(errs)
        except Exception as e:
            errores.append({
                "fila":  fila_num,
                "campo": "general",
                "error": str(e),
            })

    logger.info(
        f"Lectura completada — "
        f"Registros válidos: {len(registros)} | Con errores: {len(errores)}"
    )

    return {
        "registros":   registros,
        "errores":     errores,
        "hoja_usada":  nombre_hoja,
        "total_filas": len(df),
    }


# ─────────────────────────────────────────────────────────────────────
# PROCESAMIENTO DE FILAS (antes en excel_reader.py)
# ─────────────────────────────────────────────────────────────────────

def encontrar_columna(df_cols: list, nombre_buscado: str):
    """Busca una columna ignorando mayúsculas y espacios extra."""
    nombre_clean = nombre_buscado.strip().lower()
    for col in df_cols:
        if str(col).strip().lower() == nombre_clean:
            return col
    return None


def _procesar_fila(row: pd.Series, columnas: list, fila_num: int) -> tuple:
    """Procesa una fila del Sheet. Retorna (registro, errores)."""
    errores = []

    def get(nombre_excel: str, requerido: bool = False) -> str:
        col = encontrar_columna(columnas, nombre_excel)
        if col is None:
            col = encontrar_columna(columnas, nombre_excel + " ")
        if col is None:
            if requerido:
                errores.append({"fila": fila_num, "campo": nombre_excel, "error": "Columna no encontrada"})
            return ""
        val = str(row.get(col, "")).strip()
        if val in ("nan", "None", "NaT"):
            val = ""
        return val

    colaborador = get("Colaborador", requerido=True)
    if not colaborador:
        return None, [{"fila": fila_num, "campo": "Colaborador", "error": "Nombre vacío"}]

    colaborador_clean = colaborador.strip()
    if (colaborador_clean.isdigit() or
            len(colaborador_clean) < 5 or
            colaborador_clean.lower() in ("nan", "none", "total", "subtotal")):
        return None, []

    colaborador_clean = re.sub(r'\(.*?\)', '', colaborador_clean).strip().upper()

    numero_doc = get("Número de documento", requerido=True)
    numero_doc = re.sub(r'[^\d]', '', numero_doc)
    if not numero_doc:
        errores.append({"fila": fila_num, "campo": "Número de documento", "error": "Documento vacío"})

    compania = get("Compañía") or get("Empresa")
    genero = get("Género")

    salario_str = get("Salario")
    salario = 0
    try:
        salario = int(float(salario_str.replace(",", "").replace(".", "")) if salario_str else 0)
    except ValueError:
        errores.append({"fila": fila_num, "campo": "Salario", "error": f"Valor no numérico: {salario_str}"})

    fecha_ingreso = get("Fecha de ingreso")
    cargo = get("Cargo")
    tipo_doc = get("Tipo de documento") or "CC"
    telefono = re.sub(r'[^\d]', '', get("Teléfono"))
    email = get("Email Personal")
    ciudad = get("Ciudad de servicio ") or get("Ciudad de servicio")
    direccion = get("Dirección")
    eps = get("EPS")
    afp = get("Pensiones")
    aux_rod = get("Aux. Rodamiento")

    arl_ya_afiliado = False
    arl_col = encontrar_columna(columnas, "ARL")
    if arl_col:
        try:
            col_idx = columnas.index(arl_col)
            arl_val = str(row.iloc[col_idx]).strip().lower()
            arl_ya_afiliado = arl_val not in ("", "nan", "none", "nat")
        except Exception:
            arl_ya_afiliado = False

    if arl_ya_afiliado:
        logger.debug(f"Fila {fila_num}: {colaborador_clean} — ya tiene ARL, omitiendo")
        return None, []

    registro = {
        "fila_excel":     fila_num,
        "colaborador":    colaborador_clean,
        "genero":         genero,
        "salario":        salario,
        "aux_rodamiento": aux_rod,
        "fecha_ingreso":  fecha_ingreso,
        "cargo":          cargo,
        "tipo_doc":       tipo_doc.upper().strip() if tipo_doc else "CC",
        "numero_doc":     numero_doc,
        "telefono":       telefono,
        "email":          email.lower().strip() if email else "",
        "ciudad":         ciudad.upper().strip() if ciudad else "",
        "direccion":      direccion,
        "eps":            eps.strip() if eps else "",
        "afp":            afp.strip() if afp else "",
        "compania":       compania.upper().strip() if compania else "",
    }

    return registro, errores
