"""
Módulo: transformer.py
Transforma datos crudos del Excel al formato exacto del portal ARL.
"""
import re
from datetime import datetime
from loguru import logger

from config.mappings import (
    EMPRESA_MAP, TIPO_DOC_MAP, GENERO_MAP, VALORES_FIJOS
)
from modules.fuzzy_matcher import match_cargo, match_eps, match_afp, match_ciudad


def separar_nombre(nombre_completo: str) -> tuple:
    """
    Separa nombre completo en (nombres, apellidos).

    Regla colombiana estándar:
    - 4+ palabras: primeras (n-2) = nombres, últimas 2 = apellidos
    - 3 palabras:  primera 1 = nombre, últimas 2 = apellidos
    - 2 palabras:  primera = nombre, segunda = apellido
    - 1 palabra:   solo nombre, sin apellido
    """
    if not nombre_completo:
        return "", ""

    # Limpiar anotaciones
    nombre = re.sub(r'\(.*?\)', '', nombre_completo).strip()
    nombre = re.sub(r'\s+', ' ', nombre)  # Espacios múltiples
    palabras = nombre.split()

    if len(palabras) == 0:
        return "", ""
    elif len(palabras) == 1:
        return palabras[0], ""
    elif len(palabras) == 2:
        return palabras[0], palabras[1]
    elif len(palabras) == 3:
        return palabras[0], " ".join(palabras[1:])
    else:
        # 4+ palabras: últimas 2 son apellidos
        nombres = " ".join(palabras[:-2])
        apellidos = " ".join(palabras[-2:])
        return nombres, apellidos


def normalizar_fecha(fecha_raw) -> object:
    """
    Convierte fecha a formato dd/mm/yyyy que espera el portal ARL.
    """
    if not fecha_raw or str(fecha_raw).strip() in ("", "nan", "NaT", "None"):
        return None

    fecha_str = str(fecha_raw).strip()

    formatos = [
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d",
        "%d/%m/%Y",
        "%d-%m-%Y",
        "%m/%d/%Y",
        "%Y/%m/%d",
    ]

    for fmt in formatos:
        try:
            dt = datetime.strptime(fecha_str[:10], fmt[:len(fmt)])
            return dt.strftime("%d/%m/%Y")
        except ValueError:
            continue

    logger.warning(f"No se pudo parsear fecha: '{fecha_raw}'")
    return None


def normalizar_empresa(compania: str) -> object:
    """Mapea el nombre de compañía al código ARL exacto."""
    if not compania:
        return None

    compania_upper = compania.strip().upper()

    # Búsqueda directa
    for key, value in EMPRESA_MAP.items():
        if key.upper() in compania_upper or compania_upper in key.upper():
            return value

    logger.warning(f"Empresa no reconocida: '{compania}'")
    return None


def normalizar_genero(genero: str) -> object:
    """Normaliza el género al formato del portal."""
    if not genero:
        return None
    g = genero.strip().upper()
    return GENERO_MAP.get(g, GENERO_MAP.get(g[0] if g else "", None))


def normalizar_salario(salario, aux_rodamiento: str = "") -> int:
    """
    Normaliza el salario. Si hay aux_rodamiento no salarial,
    el salario base es el reportado en la columna Salario.
    """
    try:
        return int(float(str(salario).replace(",", "").replace(".", "") if salario else 0))
    except (ValueError, TypeError):
        return 0


def transformar_registro(reg: dict) -> dict:
    """
    Transforma un registro del Excel al formato esperado por el portal ARL.
    Retorna:
    {
        datos_transformados: dict con todos los campos para el portal,
        campos_faltantes: list de campos que necesitan intervención humana,
        advertencias: list de mensajes de advertencia
    }
    """
    campos_faltantes = []
    advertencias = []
    datos = {}

    # ── Empresa ──────────────────────────────────────────────────
    empresa_arl = normalizar_empresa(reg.get("compania", ""))
    if not empresa_arl:
        campos_faltantes.append("empresa_arl")
        advertencias.append(f"Empresa no reconocida: '{reg.get('compania')}'")
    datos["empresa_arl"] = empresa_arl

    # ── Valores fijos ─────────────────────────────────────────────
    datos.update(VALORES_FIJOS)

    # ── Tipo y número de documento ────────────────────────────────
    tipo_doc = reg.get("tipo_doc", "CC").upper().strip()
    datos["tipo_documento"] = TIPO_DOC_MAP.get(tipo_doc, "CEDULA DE CIUDADANIA")

    numero_doc = str(reg.get("numero_doc", "")).strip()
    if not numero_doc:
        campos_faltantes.append("numero_documento")
    datos["numero_documento"] = numero_doc

    # ── Nombres y apellidos ───────────────────────────────────────
    nombres, apellidos = separar_nombre(reg.get("colaborador", ""))
    if not nombres:
        campos_faltantes.append("nombres")
    if not apellidos:
        campos_faltantes.append("apellidos")
    datos["nombres"] = nombres
    datos["apellidos"] = apellidos

    # ── Fecha nacimiento → NO existe en Excel, siempre faltante ──
    datos["fecha_nacimiento"] = None
    campos_faltantes.append("fecha_nacimiento")

    # ── Género ────────────────────────────────────────────────────
    genero = normalizar_genero(reg.get("genero", ""))
    if not genero:
        campos_faltantes.append("sexo")
        advertencias.append(f"Género no reconocido: '{reg.get('genero')}'")
    datos["sexo"] = genero

    # ── Email ─────────────────────────────────────────────────────
    email = str(reg.get("email", "")).strip().lower()
    if not email or "@" not in email:
        campos_faltantes.append("email")
    datos["email"] = email

    # ── Teléfono / Celular ────────────────────────────────────────
    telefono = str(reg.get("telefono", "")).strip()
    telefono = re.sub(r'[^\d]', '', telefono)
    datos["celular"] = telefono
    datos["telefono"] = telefono

    # ── Dirección ─────────────────────────────────────────────────
    direccion = str(reg.get("direccion", "")).strip()
    if not direccion:
        campos_faltantes.append("direccion")
    datos["direccion"] = direccion

    # ── Ciudad ───────────────────────────────────────────────────
    ciudad_match = match_ciudad(reg.get("ciudad", ""))
    if ciudad_match["necesita_revision"]:
        campos_faltantes.append("ciudad")
        advertencias.append(ciudad_match["mensaje"])
    datos["ciudad"] = ciudad_match["ciudad_sugerida"]
    datos["ciudad_score"] = ciudad_match["score"]

    # ── Cargo ─────────────────────────────────────────────────────
    cargo_match = match_cargo(reg.get("cargo", ""))
    if cargo_match["necesita_revision"]:
        campos_faltantes.append("cargo")
        advertencias.append(cargo_match["mensaje"])
    datos["cargo_original"] = reg.get("cargo", "")
    datos["cargo_arl"] = cargo_match["cargo_sugerido"]
    datos["cargo_score"] = cargo_match["score"]
    datos["cargo_sugerencias"] = cargo_match.get("sugerencias", [])

    # ── Salario ───────────────────────────────────────────────────
    salario = normalizar_salario(reg.get("salario", 0), reg.get("aux_rodamiento", ""))
    if salario <= 0:
        campos_faltantes.append("salario")
    datos["salario"] = salario

    # ── Fecha inicio cobertura ────────────────────────────────────
    fecha_inicio = normalizar_fecha(reg.get("fecha_ingreso"))
    if not fecha_inicio:
        campos_faltantes.append("fecha_inicio_cobertura")
    datos["fecha_inicio_cobertura"] = fecha_inicio

    # ── EPS ───────────────────────────────────────────────────────
    eps_match = match_eps(reg.get("eps", ""))
    if eps_match["necesita_revision"]:
        campos_faltantes.append("eps")
        advertencias.append(eps_match["mensaje"])
    datos["eps"] = eps_match["eps_sugerida"]
    datos["eps_score"] = eps_match["score"]
    datos["eps_sugerencias"] = eps_match.get("sugerencias", [])

    # ── AFP ───────────────────────────────────────────────────────
    afp_match = match_afp(reg.get("afp", ""))
    if afp_match["necesita_revision"]:
        campos_faltantes.append("afp")
        advertencias.append(afp_match["mensaje"])
    datos["afp"] = afp_match["afp_sugerida"]
    datos["afp_score"] = afp_match["score"]
    datos["afp_sugerencias"] = afp_match.get("sugerencias", [])

    # ── Modalidad → siempre faltante (no viene en Excel) ─────────
    datos["modalidad"] = None
    campos_faltantes.append("modalidad")

    # Log resumen
    if campos_faltantes:
        logger.warning(
            f"{reg.get('colaborador', 'Desconocido')} | "
            f"Campos faltantes: {', '.join(campos_faltantes)}"
        )
    else:
        logger.info(f"{reg.get('colaborador', 'Desconocido')} | Transformación completa ✓")

    return {
        "datos_transformados": datos,
        "campos_faltantes":    list(set(campos_faltantes)),
        "advertencias":        advertencias,
    }


def transformar_lote(registros: list) -> list:
    """Transforma una lista de registros del Excel."""
    resultados = []
    for reg in registros:
        resultado = transformar_registro(reg)
        resultado["datos_originales"] = reg
        resultado["colaborador"] = reg.get("colaborador", "")
        resultado["numero_doc"] = reg.get("numero_doc", "")
        resultados.append(resultado)
    return resultados
