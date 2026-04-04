"""
Módulo: fuzzy_matcher.py
Matching inteligente para cargos, EPS, AFP y ciudades.
Soporta inglés → español y normalización de texto.
"""
import json
import re
from pathlib import Path
from unidecode import unidecode
from thefuzz import fuzz, process
from loguru import logger

from config.settings import (
    PORTAL_OPTIONS_DIR,
    CARGO_MATCH_AUTO, CARGO_MATCH_WARNING,
    EPS_MATCH_MIN, AFP_MATCH_MIN, CIUDAD_MATCH_MIN
)
from config.mappings import EPS_NORMALIZE, AFP_NORMALIZE, CIUDAD_NORMALIZE


# ─────────────────────────────────────────────
# Traducciones inglés → español para cargos
# ─────────────────────────────────────────────
CARGO_TRANSLATIONS = {
    "software engineer":        "INGENIERO DE SOFTWARE",
    "senior software engineer": "INGENIERO DE SOFTWARE SENIOR",
    "sr software engineer":     "INGENIERO DE SOFTWARE SENIOR",
    "backend developer":        "DESARROLLADOR BACKEND",
    "frontend developer":       "DESARROLLADOR FRONTEND",
    "full stack developer":     "DESARROLLADOR FULL STACK",
    "data engineer":            "INGENIERO DE DATOS",
    "data analyst":             "ANALISTA DE DATOS",
    "data scientist":           "CIENTÍFICO DE DATOS",
    "product manager":          "GERENTE DE PRODUCTO",
    "product designer":         "DISEÑADOR DE PRODUCTO",
    "qa":                       "QA",
    "qa analyst":               "ANALISTA QA",
    "qa lead":                  "LÍDER QA",
    "growth analyst":           "ANALISTA DE CRECIMIENTO",
    "business development representative": "REPRESENTANTE DE DESARROLLO DE NEGOCIOS",
    "customer success analyst": "ANALISTA DE ÉXITO DEL CLIENTE",
    "customer support specialist": "ESPECIALISTA DE SOPORTE AL CLIENTE",
    "billing & collection analyst": "ANALISTA DE FACTURACIÓN Y CARTERA",
    "billing & collections analyst": "ANALISTA DE FACTURACIÓN Y CARTERA",
    "financial analyst":        "ANALISTA FINANCIERO",
    "supply chain analyst":     "ANALISTA DE CADENA DE SUMINISTRO",
    "supply chain manager":     "GERENTE DE CADENA DE SUMINISTRO",
    "corporate attorney":       "ABOGADO CORPORATIVO",
    "chief operating officer":  "DIRECTOR DE OPERACIONES",
    "field operations planner": "PLANIFICADOR DE OPERACIONES DE CAMPO",
    "energy trading analyst":   "ANALISTA DE TRADING DE ENERGÍA",
    "energy concierge":         "CONCIERGE DE ENERGÍA",
    "key account manager":      "GERENTE DE CUENTAS CLAVE",
    "head of people":           "DIRECTOR DE PERSONAS",
    "head of treasury":         "DIRECTOR DE TESORERÍA",
    "head of sales":            "DIRECTOR DE VENTAS",
    "head of brand":            "DIRECTOR DE MARCA",
    "people partner":           "SOCIO DE PERSONAS",
    "automation analyst":       "ANALISTA DE AUTOMATIZACIÓN",
    "cgm analyst":              "ANALISTA CGM",
    "cgm manager":              "GERENTE CGM",
    "vp of activation":         "VICEPRESIDENTE DE ACTIVACIÓN",
    "hardware engineer":        "INGENIERO DE HARDWARE",
    "techops automation":       "AUTOMATIZACIÓN TECHOPS",
    "revenue operations analyst": "ANALISTA DE OPERACIONES DE INGRESOS",
    "accounting coordinator":   "COORDINADOR CONTABLE",
    "controlling analyst":      "ANALISTA DE CONTROL",
    "operation account executive": "EJECUTIVO DE CUENTA DE OPERACIONES",
    "operation manager":        "GERENTE DE OPERACIONES",
    "ops analyst":              "ANALISTA DE OPERACIONES",
}


def normalizar_texto(texto: str) -> str:
    """Normaliza texto: minúsculas, sin tildes, sin caracteres especiales."""
    if not texto:
        return ""
    texto = str(texto).strip().lower()
    texto = unidecode(texto)
    texto = re.sub(r'[^\w\s]', ' ', texto)
    texto = re.sub(r'\s+', ' ', texto).strip()
    return texto


def _cargar_opciones_portal(tipo: str) -> list:
    """Carga las opciones del portal guardadas en disco."""
    archivo = PORTAL_OPTIONS_DIR / f"{tipo}.json"
    if archivo.exists():
        with open(archivo, "r", encoding="utf-8") as f:
            return json.load(f)
    return []


def match_cargo(cargo_excel: str, opciones_portal: list = None) -> dict:
    """
    Busca el cargo del Excel en las opciones del portal ARL.
    Retorna: {cargo_sugerido, score, necesita_revision, mensaje}
    """
    if not cargo_excel:
        return {"cargo_sugerido": None, "score": 0, "necesita_revision": True,
                "mensaje": "Cargo vacío"}

    cargo_upper = cargo_excel.strip().upper()
    cargo_norm = normalizar_texto(cargo_excel)

    # 1. Intentar traducción inglés → español
    cargo_traducido = CARGO_TRANSLATIONS.get(cargo_norm)
    if cargo_traducido:
        logger.debug(f"Cargo traducido: '{cargo_excel}' → '{cargo_traducido}'")
        cargo_upper = cargo_traducido

    # Si no hay opciones del portal, devolver el cargo normalizado
    if not opciones_portal:
        opciones_portal = _cargar_opciones_portal("cargos")

    if not opciones_portal:
        return {
            "cargo_sugerido": cargo_upper,
            "score": 0,
            "necesita_revision": True,
            "mensaje": "Sin opciones del portal disponibles. Ejecutar descubrimiento primero."
        }

    # 2. Fuzzy matching contra opciones del portal
    opciones_norm = {normalizar_texto(op): op for op in opciones_portal}
    query_norm = normalizar_texto(cargo_upper)

    mejor = process.extractOne(
        query_norm,
        list(opciones_norm.keys()),
        scorer=fuzz.token_sort_ratio
    )

    if not mejor:
        return {"cargo_sugerido": cargo_upper, "score": 0, "necesita_revision": True,
                "mensaje": "Sin coincidencias"}

    score = mejor[1]
    cargo_portal = opciones_norm[mejor[0]]

    if score >= CARGO_MATCH_AUTO:
        return {
            "cargo_sugerido": cargo_portal,
            "score": score,
            "necesita_revision": False,
            "mensaje": f"Match automático ({score}%)"
        }
    elif score >= CARGO_MATCH_WARNING:
        return {
            "cargo_sugerido": cargo_portal,
            "score": score,
            "necesita_revision": False,
            "mensaje": f"Match con advertencia ({score}%) - Verificar: '{cargo_excel}' → '{cargo_portal}'"
        }
    else:
        # Obtener top 5 opciones
        top5 = process.extract(query_norm, list(opciones_norm.keys()),
                               scorer=fuzz.token_sort_ratio, limit=5)
        sugerencias = [opciones_norm[t[0]] for t in top5]
        return {
            "cargo_sugerido": cargo_portal,
            "score": score,
            "necesita_revision": True,
            "sugerencias": sugerencias,
            "mensaje": f"Score bajo ({score}%) - Revisión manual requerida"
        }


def match_eps(eps_excel: str, opciones_portal: list = None) -> dict:
    """Normaliza EPS y busca en opciones del portal."""
    if not eps_excel or eps_excel.upper() in ("N.A", "NO APLICA", "NA", ""):
        return {"eps_sugerida": None, "score": 0, "necesita_revision": False,
                "mensaje": "Sin EPS"}

    eps_upper = eps_excel.strip().upper()

    # 1. Mapeo directo
    canonico = EPS_NORMALIZE.get(eps_upper)
    if canonico is None and eps_upper in EPS_NORMALIZE:
        return {"eps_sugerida": None, "score": 100, "necesita_revision": False,
                "mensaje": "Sin EPS (N/A)"}

    if not opciones_portal:
        opciones_portal = _cargar_opciones_portal("eps")

    if not opciones_portal:
        # Usar valor normalizado como fallback
        return {"eps_sugerida": canonico or eps_upper, "score": 0,
                "necesita_revision": True, "mensaje": "Sin opciones del portal"}

    # 2. Fuzzy contra opciones reales del portal
    query = normalizar_texto(canonico or eps_upper)
    opciones_norm = {normalizar_texto(op): op for op in opciones_portal}

    mejor = process.extractOne(query, list(opciones_norm.keys()),
                                scorer=fuzz.token_sort_ratio)
    if mejor and mejor[1] >= EPS_MATCH_MIN:
        return {"eps_sugerida": opciones_norm[mejor[0]], "score": mejor[1],
                "necesita_revision": False, "mensaje": f"Match EPS ({mejor[1]}%)"}
    else:
        top3 = process.extract(query, list(opciones_norm.keys()), limit=3)
        return {"eps_sugerida": opciones_norm[mejor[0]] if mejor else None,
                "score": mejor[1] if mejor else 0,
                "necesita_revision": True,
                "sugerencias": [opciones_norm[t[0]] for t in top3],
                "mensaje": f"EPS no reconocida: '{eps_excel}'"}


def match_afp(afp_excel: str, opciones_portal: list = None) -> dict:
    """Normaliza AFP y busca en opciones del portal."""
    if not afp_excel or afp_excel.upper() in ("N.A", "NO APLICA", "NA", ""):
        return {"afp_sugerida": None, "score": 0, "necesita_revision": False,
                "mensaje": "Sin AFP"}

    afp_upper = afp_excel.strip().upper()

    canonico = AFP_NORMALIZE.get(afp_upper)

    if not opciones_portal:
        opciones_portal = _cargar_opciones_portal("afp")

    if not opciones_portal:
        return {"afp_sugerida": canonico or afp_upper, "score": 0,
                "necesita_revision": True, "mensaje": "Sin opciones del portal"}

    query = normalizar_texto(canonico or afp_upper)
    opciones_norm = {normalizar_texto(op): op for op in opciones_portal}

    mejor = process.extractOne(query, list(opciones_norm.keys()),
                                scorer=fuzz.token_sort_ratio)
    if mejor and mejor[1] >= AFP_MATCH_MIN:
        return {"afp_sugerida": opciones_norm[mejor[0]], "score": mejor[1],
                "necesita_revision": False, "mensaje": f"Match AFP ({mejor[1]}%)"}
    else:
        top3 = process.extract(query, list(opciones_norm.keys()), limit=3)
        return {"afp_sugerida": opciones_norm[mejor[0]] if mejor else None,
                "score": mejor[1] if mejor else 0,
                "necesita_revision": True,
                "sugerencias": [opciones_norm[t[0]] for t in top3],
                "mensaje": f"AFP no reconocida: '{afp_excel}'"}


def match_ciudad(ciudad_excel: str, opciones_portal: list = None) -> dict:
    """Normaliza ciudad y busca en opciones del portal."""
    if not ciudad_excel:
        return {"ciudad_sugerida": None, "score": 0, "necesita_revision": True,
                "mensaje": "Ciudad vacía"}

    ciudad_upper = ciudad_excel.strip().upper()

    # Mapeo directo
    canonico = CIUDAD_NORMALIZE.get(ciudad_upper)
    if canonico:
        ciudad_upper = canonico

    if not opciones_portal:
        opciones_portal = _cargar_opciones_portal("ciudades")

    if not opciones_portal:
        return {"ciudad_sugerida": ciudad_upper, "score": 0,
                "necesita_revision": True, "mensaje": "Sin opciones del portal"}

    query = normalizar_texto(ciudad_upper)
    opciones_norm = {normalizar_texto(op): op for op in opciones_portal}

    mejor = process.extractOne(query, list(opciones_norm.keys()),
                                scorer=fuzz.token_sort_ratio)
    if mejor and mejor[1] >= CIUDAD_MATCH_MIN:
        return {"ciudad_sugerida": opciones_norm[mejor[0]], "score": mejor[1],
                "necesita_revision": False, "mensaje": f"Match ciudad ({mejor[1]}%)"}
    else:
        return {"ciudad_sugerida": ciudad_upper, "score": mejor[1] if mejor else 0,
                "necesita_revision": True,
                "mensaje": f"Ciudad no reconocida: '{ciudad_excel}'"}
