"""
Módulo: excel_reader.py
Lee y valida el Excel de Notificaciones Nómina Buk.
NUNCA modifica el archivo original.
"""
import re
import pandas as pd
from pathlib import Path
from datetime import datetime
from loguru import logger
from config.mappings import EXCEL_COLUMNS


def encontrar_columna(df_cols: list, nombre_buscado: str) -> object:
    """Busca una columna ignorando mayúsculas y espacios extra."""
    nombre_clean = nombre_buscado.strip().lower()
    for col in df_cols:
        if str(col).strip().lower() == nombre_clean:
            return col
    return None


def encontrar_hoja_mas_reciente(path: Path) -> str:
    """Detecta la hoja más reciente con datos de nómina."""
    xl = pd.ExcelFile(path)
    excluidas = ['NVScriptsProperties', 'DO NOT DELETE - AutoCrat Job Se']

    hojas_validas = [h for h in xl.sheet_names if h not in excluidas]

    # La última hoja suele ser la más reciente
    # Intentar parsear la fecha del nombre de la hoja
    meses = {
        'enero': 1, 'febrero': 2, 'marzo': 3, 'abril': 4,
        'mayo': 5, 'junio': 6, 'julio': 7, 'agosto': 8,
        'septiembre': 9, 'octubre': 10, 'noviembre': 11, 'diciembre': 12
    }

    hojas_con_fecha = []
    for hoja in hojas_validas:
        partes = hoja.strip().lower().split()
        anio = None
        mes = None
        for p in partes:
            if p.isdigit() and len(p) == 4:
                anio = int(p)
            if p in meses:
                mes = meses[p]
        if anio and mes:
            hojas_con_fecha.append((datetime(anio, mes, 1), hoja))

    if hojas_con_fecha:
        hojas_con_fecha.sort(key=lambda x: x[0])
        return hojas_con_fecha[-1][1]

    return hojas_validas[-1]


def leer_excel(path, hoja: str = None) -> dict:
    """
    Lee el Excel y retorna un diccionario con:
    - registros: lista de dicts con datos limpios
    - errores: lista de errores por fila
    - hoja_usada: nombre de la hoja leída
    - total_filas: total de filas encontradas
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"No se encontró el archivo: {path}")

    logger.info(f"Leyendo Excel: {path.name}")

    if hoja is None:
        hoja = encontrar_hoja_mas_reciente(path)

    logger.info(f"Hoja seleccionada: '{hoja}'")

    df = pd.read_excel(path, sheet_name=hoja, header=0, dtype=str)

    # Limpiar nombres de columnas (espacios extra)
    df.columns = [str(c).strip() for c in df.columns]

    # Eliminar filas completamente vacías
    df = df.dropna(how='all')

    logger.info(f"Filas encontradas: {len(df)}")

    registros = []
    errores = []

    for idx, row in df.iterrows():
        fila_num = idx + 2  # +2 porque idx empieza en 0 y hay encabezado

        try:
            reg, errs = _procesar_fila(row, df.columns.tolist(), fila_num)
            if reg:
                registros.append(reg)
            if errs:
                errores.extend(errs)
        except Exception as e:
            errores.append({
                "fila": fila_num,
                "campo": "general",
                "error": str(e)
            })

    logger.info(f"Registros válidos: {len(registros)} | Con errores: {len(errores)}")

    return {
        "registros": registros,
        "errores": errores,
        "hoja_usada": hoja,
        "total_filas": len(df),
    }


def _procesar_fila(row: pd.Series, columnas: list, fila_num: int) -> tuple:
    """Procesa una fila del Excel. Retorna (registro, errores)."""
    errores = []

    def get(nombre_excel: str, requerido: bool = False) -> str:
        """Obtiene el valor de una columna con búsqueda flexible."""
        col = encontrar_columna(columnas, nombre_excel)
        if col is None:
            # Intentar con y sin espacio al final
            col = encontrar_columna(columnas, nombre_excel + " ")
        if col is None:
            if requerido:
                errores.append({"fila": fila_num, "campo": nombre_excel, "error": "Columna no encontrada"})
            return ""
        val = str(row.get(col, "")).strip()
        if val in ("nan", "None", "NaT"):
            val = ""
        return val

    # ── Colaborador ──────────────────────────────
    colaborador = get("Colaborador", requerido=True)
    if not colaborador:
        return None, [{"fila": fila_num, "campo": "Colaborador", "error": "Nombre vacío"}]

    # Filtrar filas que no son empleados reales
    colaborador_clean = colaborador.strip()
    if (colaborador_clean.isdigit() or
        len(colaborador_clean) < 5 or
        colaborador_clean.lower() in ("nan", "none", "total", "subtotal")):
        return None, []  # Silenciosamente ignorar

    # Limpiar anotaciones entre paréntesis
    colaborador_clean = re.sub(r'\(.*?\)', '', colaborador_clean).strip()
    colaborador_clean = colaborador_clean.upper()

    # ── Número de documento ──────────────────────
    numero_doc = get("Número de documento", requerido=True)
    numero_doc = re.sub(r'[^\d]', '', numero_doc)  # Solo dígitos
    if not numero_doc:
        errores.append({"fila": fila_num, "campo": "Número de documento", "error": "Documento vacío"})

    # ── Compañía ─────────────────────────────────
    compania = get("Compañía")
    if not compania:
        compania = get("Empresa")  # Fallback a columna alternativa

    # ── Género ────────────────────────────────────
    genero = get("Género")

    # ── Salario ───────────────────────────────────
    salario_str = get("Salario")
    salario = 0
    try:
        salario = int(float(salario_str.replace(",", "").replace(".", "")) if salario_str else 0)
    except ValueError:
        errores.append({"fila": fila_num, "campo": "Salario", "error": f"Valor no numérico: {salario_str}"})

    # ── Fecha de ingreso ──────────────────────────
    fecha_ingreso = get("Fecha de ingreso")
    # Ya viene como datetime o string, lo normalizamos después

    # ── Otros campos ──────────────────────────────
    cargo = get("Cargo")
    tipo_doc = get("Tipo de documento") or "CC"
    telefono = get("Teléfono")
    telefono = re.sub(r'[^\d]', '', telefono)  # Solo dígitos
    email = get("Email Personal")

    # Ciudad: puede tener espacio al final en el Excel
    ciudad = get("Ciudad de servicio ") or get("Ciudad de servicio")
    direccion = get("Dirección")
    eps = get("EPS")
    afp = get("Pensiones")
    aux_rod = get("Aux. Rodamiento")

    # ── ARL Status ────────────────────────────────
    # Verificamos si ya tiene ARL usando la columna "ARL" directamente
    # (valor NaN = sin afiliar, cualquier texto = ya afiliado)
    arl_ya_afiliado = False
    arl_col = encontrar_columna(columnas, "ARL")
    if arl_col:
        # Con columnas duplicadas, iloc es más seguro que row.get()
        try:
            col_idx = columnas.index(arl_col)
            arl_val = str(row.iloc[col_idx]).strip().lower()
            arl_ya_afiliado = arl_val not in ("", "nan", "none", "nat")
        except Exception:
            arl_ya_afiliado = False

    if arl_ya_afiliado:
        logger.debug(f"Fila {fila_num}: {colaborador_clean} - Ya tiene ARL registrado, omitiendo")
        return None, []

    registro = {
        "fila_excel":   fila_num,
        "colaborador":  colaborador_clean,
        "genero":       genero,
        "salario":      salario,
        "aux_rodamiento": aux_rod,
        "fecha_ingreso": fecha_ingreso,
        "cargo":        cargo,
        "tipo_doc":     tipo_doc.upper().strip() if tipo_doc else "CC",
        "numero_doc":   numero_doc,
        "telefono":     telefono,
        "email":        email.lower().strip() if email else "",
        "ciudad":       ciudad.upper().strip() if ciudad else "",
        "direccion":    direccion,
        "eps":          eps.strip() if eps else "",
        "afp":          afp.strip() if afp else "",
        "compania":     compania.upper().strip() if compania else "",
    }

    return registro, errores


def _encontrar_columna_arl_status(columnas: list, row: pd.Series) -> object:
    """
    Busca la columna de Status correspondiente a ARL.
    En el Excel hay múltiples columnas 'Status', la de ARL es la tercera.
    """
    # En el Excel, después de la columna "ARL" viene su "Status"
    status_cols = [c for c in columnas if 'status' in str(c).lower()]
    # La tercera columna Status (índice 2) corresponde a ARL según el diseño del Excel
    if len(status_cols) >= 3:
        return status_cols[2]
    return None


def listar_hojas(path) -> list:
    """Lista todas las hojas disponibles en el Excel."""
    path = Path(path)
    excluidas = ['NVScriptsProperties', 'DO NOT DELETE - AutoCrat Job Se']
    xl = pd.ExcelFile(path)
    return [h for h in xl.sheet_names if h not in excluidas]
