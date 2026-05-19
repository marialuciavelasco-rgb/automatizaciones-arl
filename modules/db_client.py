"""
Módulo: db_client.py
Todas las operaciones de persistencia (SQLite).
"""
import json
import sqlite3
import uuid
from datetime import datetime, timezone
from loguru import logger

from config.settings import SQLITE_DB_PATH

TABLA = "afiliaciones"
_conn: sqlite3.Connection | None = None

JSON_FIELDS = (
    "datos_originales", "datos_transformados", "campos_faltantes",
    "campos_manuales", "advertencias", "logs", "resultado",
)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS afiliaciones (
    id                  TEXT PRIMARY KEY,
    estado              TEXT NOT NULL,
    empresa             TEXT,
    documento_empleado  TEXT,
    nombre_empleado     TEXT,
    datos_originales    TEXT,
    datos_transformados TEXT,
    campos_faltantes    TEXT,
    campos_manuales     TEXT,
    advertencias        TEXT,
    logs                TEXT,
    intentos            INTEGER NOT NULL DEFAULT 0,
    fecha_creacion      TEXT NOT NULL,
    fecha_actualizacion TEXT NOT NULL,
    resultado           TEXT,
    error_detalle       TEXT
);
CREATE INDEX IF NOT EXISTS idx_afiliaciones_estado    ON afiliaciones(estado);
CREATE INDEX IF NOT EXISTS idx_afiliaciones_documento ON afiliaciones(documento_empleado);
"""


def _get_conn() -> sqlite3.Connection:
    """Abre (o reutiliza) la conexión a SQLite y asegura el esquema."""
    global _conn
    if _conn is not None:
        return _conn

    SQLITE_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    _conn = sqlite3.connect(str(SQLITE_DB_PATH), check_same_thread=False)
    _conn.row_factory = sqlite3.Row
    _conn.executescript(_SCHEMA)
    _conn.commit()
    logger.info(f"SQLite inicializado: {SQLITE_DB_PATH} ✓")
    return _conn


def ahora() -> str:
    """Timestamp ISO-8601 UTC."""
    return datetime.now(timezone.utc).isoformat()


def _dump(v):
    return None if v is None else json.dumps(v, ensure_ascii=False, default=str)


def _load(v):
    return None if v is None else json.loads(v)


def _row_to_dict(row: sqlite3.Row | None) -> dict | None:
    if row is None:
        return None
    d = dict(row)
    for f in JSON_FIELDS:
        d[f] = _load(d.get(f))
    return d


def _update(doc_id: str, campos: dict):
    """UPDATE con los campos dados + fecha_actualizacion automática."""
    campos = {**campos, "fecha_actualizacion": ahora()}
    serializados = {
        k: (_dump(v) if k in JSON_FIELDS else v) for k, v in campos.items()
    }
    sets = ", ".join(f"{k} = ?" for k in serializados)
    valores = list(serializados.values()) + [doc_id]
    conn = _get_conn()
    conn.execute(f"UPDATE afiliaciones SET {sets} WHERE id = ?", valores)
    conn.commit()


# ─────────────────────────────────────────────────────────────────────
# CREAR
# ─────────────────────────────────────────────────────────────────────

def crear_afiliacion(datos_originales: dict, datos_transformados: dict,
                     campos_faltantes: list, advertencias: list) -> str:
    """
    Crea un nuevo registro de afiliación.
    Retorna el ID del registro creado.
    """
    conn = _get_conn()

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
                _update(existente["id"], {
                    "estado":              "pendiente",
                    "datos_transformados": datos_transformados,
                    "campos_faltantes":    campos_faltantes,
                    "advertencias":        advertencias,
                    "error_detalle":       None,
                })
                return existente["id"]

    doc_id = uuid.uuid4().hex
    ts = ahora()
    log_inicial = [{
        "timestamp": ts,
        "mensaje":   "Registro creado desde Excel",
        "nivel":     "INFO",
        "paso":      "ingesta",
    }]

    conn.execute(
        """
        INSERT INTO afiliaciones (
            id, estado, empresa, documento_empleado, nombre_empleado,
            datos_originales, datos_transformados, campos_faltantes,
            campos_manuales, advertencias, logs, intentos,
            fecha_creacion, fecha_actualizacion, resultado, error_detalle
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            doc_id, "pendiente",
            datos_originales.get("compania", ""),
            numero_doc,
            datos_originales.get("colaborador", ""),
            _dump(datos_originales), _dump(datos_transformados),
            _dump(campos_faltantes), _dump({}),
            _dump(advertencias),    _dump(log_inicial),
            0, ts, ts, None, None,
        ),
    )
    conn.commit()
    logger.info(f"Afiliación creada: {doc_id} | {datos_originales.get('colaborador')}")
    return doc_id


# ─────────────────────────────────────────────────────────────────────
# ACTUALIZAR
# ─────────────────────────────────────────────────────────────────────

def actualizar_estado(doc_id: str, estado: str, error_detalle: str = None):
    """Cambia el estado de una afiliación."""
    update = {"estado": estado}
    if error_detalle:
        update["error_detalle"] = error_detalle
    _update(doc_id, update)
    logger.debug(f"{doc_id} → estado: {estado}")


def incrementar_intento(doc_id: str):
    """Suma 1 al contador de intentos."""
    conn = _get_conn()
    conn.execute(
        "UPDATE afiliaciones SET intentos = intentos + 1, fecha_actualizacion = ? WHERE id = ?",
        (ahora(), doc_id),
    )
    conn.commit()


def agregar_log(doc_id: str, mensaje: str, nivel: str = "INFO", paso: str = ""):
    """Agrega una entrada al historial de logs del registro."""
    doc = obtener_por_id(doc_id)
    if doc is None:
        return
    logs = doc.get("logs") or []
    logs.append({
        "timestamp": ahora(),
        "mensaje":   mensaje,
        "nivel":     nivel,
        "paso":      paso,
    })
    _update(doc_id, {"logs": logs})


def guardar_resultado(doc_id: str, numero_afiliacion: str = None, mensaje: str = ""):
    """Guarda el resultado final de la afiliación."""
    _update(doc_id, {
        "estado": "completado",
        "resultado": {
            "numero_afiliacion": numero_afiliacion,
            "mensaje":           mensaje,
            "fecha":             ahora(),
        },
    })


def marcar_campos_faltantes(doc_id: str, campos: list, advertencias: list = None):
    """Marca los campos que necesitan intervención humana."""
    update = {
        "estado":           "requiere_intervencion",
        "campos_faltantes": campos,
    }
    if advertencias:
        update["advertencias"] = advertencias
    _update(doc_id, update)


def guardar_campo_manual(doc_id: str, campo: str, valor: str):
    """
    Guarda un valor ingresado manualmente por el humano.
    También remueve ese campo de campos_faltantes si ya fue llenado.
    """
    doc = obtener_por_id(doc_id)
    if doc is None:
        return

    campos_manuales = doc.get("campos_manuales") or {}
    campos_manuales[campo] = valor

    campos_faltantes = doc.get("campos_faltantes") or []
    if campo in campos_faltantes:
        campos_faltantes.remove(campo)

    _update(doc_id, {
        "campos_manuales":  campos_manuales,
        "campos_faltantes": campos_faltantes,
    })
    logger.info(f"{doc_id} → campo manual guardado: {campo} = {valor}")


def guardar_campos_manuales_bulk(doc_id: str, campos: dict):
    """
    Guarda múltiples campos manuales a la vez.
    Cuando el humano completa datos, resetea el contador de intentos
    para que el próximo ciclo RPA no quede bloqueado por MAX_INTENTOS.
    """
    doc = obtener_por_id(doc_id)
    if doc is None:
        return

    campos_manuales = doc.get("campos_manuales") or {}
    campos_manuales.update(campos)

    campos_faltantes = doc.get("campos_faltantes") or []
    for campo in campos.keys():
        if campo in campos_faltantes:
            campos_faltantes.remove(campo)

    nuevo_estado = "pendiente" if not campos_faltantes else "requiere_intervencion"

    _update(doc_id, {
        "campos_manuales":  campos_manuales,
        "campos_faltantes": campos_faltantes,
        "estado":           nuevo_estado,
        "intentos":         0,
        "error_detalle":    None,
    })


def reiniciar_afiliacion(doc_id: str):
    """
    Reinicia completamente un registro para reintento manual.
    Útil cuando el registro quedó bloqueado en estado 'error'
    o tras demasiados intentos automáticos fallidos.
    """
    _update(doc_id, {
        "estado":           "pendiente",
        "intentos":         0,
        "error_detalle":    None,
        "campos_faltantes": [],
    })
    logger.info(f"{doc_id} → reiniciado para reintento")


def eliminar_afiliacion(doc_id: str):
    """
    Elimina permanentemente un registro.
    Usar solo cuando los datos son incorrectos y hay que volver
    a cargar el empleado desde el Excel/Sheets.
    """
    conn = _get_conn()
    conn.execute("DELETE FROM afiliaciones WHERE id = ?", (doc_id,))
    conn.commit()
    logger.info(f"{doc_id} → eliminado permanentemente")


# ─────────────────────────────────────────────────────────────────────
# CONSULTAR
# ─────────────────────────────────────────────────────────────────────

def obtener_todos(limit: int = 200) -> list:
    """Retorna todos los registros ordenados por fecha de creación (DESC)."""
    conn = _get_conn()
    rows = conn.execute(
        "SELECT * FROM afiliaciones ORDER BY fecha_creacion DESC LIMIT ?",
        (limit,),
    ).fetchall()
    return [_row_to_dict(r) for r in rows]


def obtener_pendientes() -> list:
    """Retorna afiliaciones listas para procesar (estado='pendiente')."""
    return obtener_por_estado("pendiente")


def obtener_para_reintento() -> list:
    """
    Retorna afiliaciones que requieren intervención
    y ya tienen todos sus campos_faltantes resueltos.
    """
    return [
        d for d in obtener_por_estado("requiere_intervencion")
        if not d.get("campos_faltantes")
    ]


def obtener_por_estado(estado: str) -> list:
    conn = _get_conn()
    rows = conn.execute(
        "SELECT * FROM afiliaciones WHERE estado = ? ORDER BY fecha_creacion DESC",
        (estado,),
    ).fetchall()
    return [_row_to_dict(r) for r in rows]


def obtener_por_id(doc_id: str) -> dict | None:
    conn = _get_conn()
    row = conn.execute(
        "SELECT * FROM afiliaciones WHERE id = ?", (doc_id,)
    ).fetchone()
    return _row_to_dict(row)


def buscar_por_documento(numero_doc: str) -> dict | None:
    """Busca por número de documento."""
    num = str(numero_doc).strip()
    conn = _get_conn()
    row = conn.execute(
        "SELECT * FROM afiliaciones WHERE TRIM(documento_empleado) = ? LIMIT 1",
        (num,),
    ).fetchone()
    return _row_to_dict(row)


def contar_por_estado() -> dict:
    """Retorna un resumen de conteos por estado."""
    estados = ["pendiente", "en_proceso", "requiere_intervencion", "completado", "error"]
    conn = _get_conn()
    rows = conn.execute(
        "SELECT estado, COUNT(*) AS n FROM afiliaciones GROUP BY estado"
    ).fetchall()
    counts = {r["estado"]: r["n"] for r in rows}
    return {e: counts.get(e, 0) for e in estados}
