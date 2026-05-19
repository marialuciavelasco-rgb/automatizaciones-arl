"""
handler.py — Entry point de AWS Lambda y GitHub Actions.

Flujo:
1. Lee empleados del Google Sheet (AutomatizacionesRRHH > pestaña Sync)
2. Guarda/actualiza en la base de datos los que están pendientes
3. Ejecuta el RPA headless para todos los pendientes
"""
import asyncio
import sys
from loguru import logger

# ── Configurar logger para CI (sin colores, con timestamps) ──────────
logger.remove()
logger.add(sys.stdout, format="{time:HH:mm:ss} | {level:<8} | {message}", level="INFO")


async def main():
    logger.info("=" * 60)
    logger.info("ARL AUTOMATION — Ejecución en la nube (GitHub Actions)")
    logger.info("=" * 60)

    # 1. Leer desde Google Sheets
    from modules.sheets_reader import leer_sheets, sheets_disponible
    if not sheets_disponible():
        logger.error("Google Sheets no configurado. Verifica GOOGLE_SHEETS_ID y credentials.")
        sys.exit(1)

    logger.info("Leyendo datos desde Google Sheets...")
    resultado = leer_sheets("AutomatizacionesRRHH")
    registros = resultado.get("registros", [])
    logger.info(f"Hoja: {resultado.get('hoja_usada')} | Registros: {len(registros)}")

    if not registros:
        logger.info("No hay registros para procesar. Finalizando.")
        return

    # 2. Transformar y guardar en la base de datos
    from modules.transformer import transformar_lote
    import modules.db_client as fb

    transformados = transformar_lote(registros)
    nuevos = actualizados = 0

    for resultado in transformados:
        datos_orig       = resultado["datos_originales"]
        datos_tx         = resultado["datos_transformados"]
        campos_faltantes = resultado["campos_faltantes"]
        advertencias     = resultado["advertencias"]

        num_doc = str(datos_orig.get("numero_doc", "")).strip()
        if not num_doc:
            continue

        existente = fb.buscar_por_documento(num_doc)
        if existente and existente.get("estado") == "completado":
            logger.debug(f"  {datos_orig.get('colaborador')} → ya completado, omitiendo")
            continue

        fb.crear_afiliacion(datos_orig, datos_tx, campos_faltantes, advertencias)
        if existente:
            actualizados += 1
        else:
            nuevos += 1

    logger.info(f"DB: {nuevos} nuevos | {actualizados} actualizados")

    # 3. Obtener pendientes y ejecutar RPA
    from modules.rpa_engine import ejecutar_proceso_completo
    pendientes = fb.obtener_pendientes()

    if not pendientes:
        logger.info("No hay afiliaciones pendientes. Finalizando.")
        return

    logger.info(f"Procesando {len(pendientes)} afiliación(es) pendiente(s)...")
    doc_ids = [d["id"] for d in pendientes]
    await ejecutar_proceso_completo(doc_ids=doc_ids)

    # 4. Resumen final
    conteos = fb.contar_por_estado()
    logger.info("=" * 60)
    logger.info("RESUMEN FINAL:")
    logger.info(f"  ✅ Completados:          {conteos.get('completado', 0)}")
    logger.info(f"  🔴 Requieren revisión:   {conteos.get('requiere_intervencion', 0)}")
    logger.info(f"  ❌ Errores:              {conteos.get('error', 0)}")
    logger.info(f"  ⏳ Pendientes:           {conteos.get('pendiente', 0)}")
    logger.info("=" * 60)


def lambda_handler(event=None, context=None):
    """AWS Lambda entry point."""
    asyncio.run(main())
    return {"statusCode": 200, "body": "Proceso completado"}


if __name__ == "__main__":
    asyncio.run(main())
