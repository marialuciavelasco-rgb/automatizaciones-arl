"""
Módulo: firebase_client.py
Todas las operaciones con Firebase Firestore.
"""
import json
from datetime import datetime, timezone
from pathlib import Path
from loguru import logger

import firebase_admin
from firebase_admin import credentials, firestore

from config.settings import FIREBASE_KEY_PATH, FIREBASE_PROJECT_ID

COLECCION = "afiliaciones"
_db = None


def _init_firebase():
    """
    Inicializa Firebase (solo una vez).
    Prioridad:
      1. Variable de entorno FIREBASE_KEY_JSON (JSON como string) → para Render/Cloud
      2. Archivo config/firebase_key.json → para uso local
      3. Application Default Credentials → para GCP
    """
    global _db
    if _db is not None:
        return _db

    if not firebase_admin._apps:
        import os
        firebase_key_json = os.getenv("FIREBASE_KEY_JSON", "")
        if firebase_key_json:
            # Cloud: credenciales como variable de entorno (JSON string)
            cred_dict = json.loads(firebase_key_json)
            cred = credentials.Certificate(cred_dict)
            firebase_admin.initialize_app(cred)
            logger.info("Firebase inicializado desde variable de entorno ✓")
        elif FIREBASE_KEY_PATH.exists():
            cred = credentials.Certificate(str(FIREBASE_KEY_PATH))
            firebase_admin.initialize_app(cred)
            logger.info("Firebase inicializado con archivo de credenciales ✓")
        elif FIREBASE_PROJECT_ID:
            cred = credentials.ApplicationDefault()
            firebase_admin.initialize_app(cred, {"projectId": FIREBASE_PROJECT_ID})
            logger.info("Firebase inicializado con credenciales de entorno ✓")
        else:
            raise RuntimeError(
                "Firebase no configurado. "
                "Coloca firebase_key.json en config/ o configura FIREBASE_KEY_JSON en variables de entorno."
            )

    _db = firestore.client()
    return _db


def ahora() -> datetime:
    return datetime.now(timezone.utc)


# ─────────────────────────────────────────────────────────────────────
# CREAR
# ─────────────────────────────────────────────────────────────────────

def crear_afiliacion(datos_originales: dict, datos_transformados: dict,
                     campos_faltantes: list, advertencias: list) -> str:
    """
    Crea un nuevo documento de afiliación en Firestore.
    Retorna el ID del documento creado.
    """
    db = _init_firebase()

    # Verificar si ya existe por número de documento — NUNCA crear duplicados
    numero_doc = str(datos_originales.get("numero_doc", ""))
    if numero_doc:
        existente = buscar_por_documento(numero_doc)
        if existente:
            estado_actual = existente.get("estado", "")
            if estado_actual == "completado":
                logger.info(f"Doc {numero_doc} ya está completado, omitiendo")
                return existente["id"]
            elif estado_actual in ("pendiente", "en_proceso"):
                logger.info(f"Doc {numero_doc} ya existe ({estado_actual}), reutilizando")
                return existente["id"]
            elif estado_actual in ("requiere_intervencion", "error"):
                # Reiniciar el registro existente para reintento limpio
                logger.info(f"Doc {numero_doc} en estado '{estado_actual}', reiniciando para reintento")
                doc_ref = db.collection(COLECCION).document(existente["id"])
                doc_ref.update({
                    "estado":              "pendiente",
                    "datos_transformados": datos_transformados,
                    "campos_faltantes":    campos_faltantes,
                    "advertencias":        advertencias,
                    "error_detalle":       None,
                    "fecha_actualizacion": ahora(),
                })
                return existente["id"]

    doc_ref = db.collection(COLECCION).document()

    documento = {
        "id":                  doc_ref.id,
        "estado":              "pendiente",
        "empresa":             datos_originales.get("compania", ""),
        "documento_empleado":  numero_doc,
        "nombre_empleado":     datos_originales.get("colaborador", ""),
        "datos_originales":    datos_originales,
        "datos_transformados": datos_transformados,
        "campos_faltantes":    campos_faltantes,
        "campos_manuales":     {},
        "advertencias":        advertencias,
        "logs": [{
            "timestamp": ahora().isoformat(),
            "mensaje":   "Registro creado desde Excel",
            "nivel":     "INFO",
            "paso":      "ingesta"
        }],
        "intentos":            0,
        "fecha_creacion":      ahora(),
        "fecha_actualizacion": ahora(),
        "resultado":           None,
        "error_detalle":       None,
    }

    doc_ref.set(documento)
    logger.info(f"Afiliación creada: {doc_ref.id} | {datos_originales.get('colaborador')}")
    return doc_ref.id


# ─────────────────────────────────────────────────────────────────────
# ACTUALIZAR
# ─────────────────────────────────────────────────────────────────────

def actualizar_estado(doc_id: str, estado: str, error_detalle: str = None):
    """Cambia el estado de una afiliación."""
    db = _init_firebase()
    update = {
        "estado":              estado,
        "fecha_actualizacion": ahora(),
    }
    if error_detalle:
        update["error_detalle"] = error_detalle

    db.collection(COLECCION).document(doc_id).update(update)
    logger.debug(f"{doc_id} → estado: {estado}")


def incrementar_intento(doc_id: str):
    """Suma 1 al contador de intentos."""
    db = _init_firebase()
    doc = db.collection(COLECCION).document(doc_id).get()
    intentos_actuales = doc.to_dict().get("intentos", 0)
    db.collection(COLECCION).document(doc_id).update({
        "intentos":            intentos_actuales + 1,
        "fecha_actualizacion": ahora(),
    })


def agregar_log(doc_id: str, mensaje: str, nivel: str = "INFO", paso: str = ""):
    """Agrega una entrada al historial de logs del documento."""
    db = _init_firebase()
    doc_ref = db.collection(COLECCION).document(doc_id)
    doc = doc_ref.get().to_dict()
    logs = doc.get("logs", [])
    logs.append({
        "timestamp": ahora().isoformat(),
        "mensaje":   mensaje,
        "nivel":     nivel,
        "paso":      paso,
    })
    doc_ref.update({
        "logs":                logs,
        "fecha_actualizacion": ahora(),
    })


def guardar_resultado(doc_id: str, numero_afiliacion: str = None, mensaje: str = ""):
    """Guarda el resultado final de la afiliación."""
    db = _init_firebase()
    db.collection(COLECCION).document(doc_id).update({
        "estado":              "completado",
        "resultado": {
            "numero_afiliacion": numero_afiliacion,
            "mensaje":           mensaje,
            "fecha":             ahora().isoformat(),
        },
        "fecha_actualizacion": ahora(),
    })


def marcar_campos_faltantes(doc_id: str, campos: list, advertencias: list = None):
    """Marca los campos que necesitan intervención humana."""
    db = _init_firebase()
    update = {
        "estado":              "requiere_intervencion",
        "campos_faltantes":    campos,
        "fecha_actualizacion": ahora(),
    }
    if advertencias:
        update["advertencias"] = advertencias
    db.collection(COLECCION).document(doc_id).update(update)


def guardar_campo_manual(doc_id: str, campo: str, valor: str):
    """
    Guarda un valor ingresado manualmente por el humano.
    También remueve ese campo de campos_faltantes si ya fue llenado.
    """
    db = _init_firebase()
    doc_ref = db.collection(COLECCION).document(doc_id)
    doc = doc_ref.get().to_dict()

    campos_manuales = doc.get("campos_manuales", {})
    campos_manuales[campo] = valor

    campos_faltantes = doc.get("campos_faltantes", [])
    if campo in campos_faltantes:
        campos_faltantes.remove(campo)

    doc_ref.update({
        "campos_manuales":     campos_manuales,
        "campos_faltantes":    campos_faltantes,
        "fecha_actualizacion": ahora(),
    })

    logger.info(f"{doc_id} → campo manual guardado: {campo} = {valor}")


def guardar_campos_manuales_bulk(doc_id: str, campos: dict):
    """
    Guarda múltiples campos manuales a la vez.
    Cuando el humano completa datos, resetea el contador de intentos
    para que el próximo ciclo RPA no quede bloqueado por MAX_INTENTOS.
    """
    db = _init_firebase()
    doc_ref = db.collection(COLECCION).document(doc_id)
    doc = doc_ref.get().to_dict()

    campos_manuales = doc.get("campos_manuales", {})
    campos_manuales.update(campos)

    campos_faltantes = doc.get("campos_faltantes", [])
    for campo in campos.keys():
        if campo in campos_faltantes:
            campos_faltantes.remove(campo)

    nuevo_estado = "pendiente" if not campos_faltantes else "requiere_intervencion"

    doc_ref.update({
        "campos_manuales":     campos_manuales,
        "campos_faltantes":    campos_faltantes,
        "estado":              nuevo_estado,
        # Resetear intentos: el humano intervino, se le da una nueva oportunidad limpia
        "intentos":            0,
        "error_detalle":       None,
        "fecha_actualizacion": ahora(),
    })


def reiniciar_afiliacion(doc_id: str):
    """
    Reinicia completamente un registro para reintento manual.
    Útil cuando el registro quedó bloqueado en estado 'error'
    o tras demasiados intentos automáticos fallidos.
    Resetea: estado → pendiente, intentos → 0, error_detalle → None.
    """
    db = _init_firebase()
    db.collection(COLECCION).document(doc_id).update({
        "estado":              "pendiente",
        "intentos":            0,
        "error_detalle":       None,
        "campos_faltantes":    [],
        "fecha_actualizacion": ahora(),
    })
    logger.info(f"{doc_id} → reiniciado para reintento")


def eliminar_afiliacion(doc_id: str):
    """
    Elimina permanentemente un registro de Firebase.
    Usar solo cuando los datos son incorrectos y hay que volver
    a cargar el empleado desde el Excel/Sheets.
    """
    db = _init_firebase()
    db.collection(COLECCION).document(doc_id).delete()
    logger.info(f"{doc_id} → eliminado permanentemente")


# ─────────────────────────────────────────────────────────────────────
# CONSULTAR
# ─────────────────────────────────────────────────────────────────────

def obtener_todos(limit: int = 200) -> list:
    """Retorna todos los documentos ordenados por fecha de creación."""
    db = _init_firebase()
    docs = (
        db.collection(COLECCION)
        .order_by("fecha_creacion", direction=firestore.Query.DESCENDING)
        .limit(limit)
        .stream()
    )
    return [d.to_dict() for d in docs]


def _obtener_todos_raw() -> list:
    """Obtiene todos los documentos sin filtro (para evitar issues con Firestore WHERE)."""
    db = _init_firebase()
    docs = db.collection(COLECCION).stream()
    return [d.to_dict() for d in docs]


def obtener_pendientes() -> list:
    """Retorna afiliaciones listas para procesar (estado='pendiente')."""
    return [d for d in _obtener_todos_raw() if d.get("estado") == "pendiente"]


def obtener_para_reintento() -> list:
    """
    Retorna afiliaciones que requieren intervención
    y ya tienen todos sus campos_faltantes resueltos.
    """
    resultado = []
    for d in _obtener_todos_raw():
        if d.get("estado") == "requiere_intervencion" and not d.get("campos_faltantes"):
            resultado.append(d)
    return resultado


def obtener_por_estado(estado: str) -> list:
    return [d for d in _obtener_todos_raw() if d.get("estado") == estado]


def obtener_por_id(doc_id: str) -> object:
    db = _init_firebase()
    doc = db.collection(COLECCION).document(doc_id).get()
    return doc.to_dict() if doc.exists else None


def buscar_por_documento(numero_doc: str) -> object:
    """Busca por número de documento filtrando en Python (Firestore WHERE falla con esta versión)."""
    num = str(numero_doc).strip()
    for data in _obtener_todos_raw():
        if str(data.get("documento_empleado", "")).strip() == num:
            return data
    return None


def contar_por_estado() -> dict:
    """Retorna un resumen de conteos por estado."""
    db = _init_firebase()
    estados = ["pendiente", "en_proceso", "requiere_intervencion", "completado", "error"]
    conteos = {}
    for estado in estados:
        docs = list(db.collection(COLECCION).where("estado", "==", estado).stream())
        conteos[estado] = len(docs)
    return conteos
