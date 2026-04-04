"""
run_cloud.py — Ejecutor para GitHub Actions (sin menú interactivo).

Flujo:
1. Lee empleados del Google Sheet (AutomatizacionesRRHH > pestaña Sync)
2. Guarda/actualiza en Firebase los que están pendientes
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

    # 2. Transformar y guardar en Firebase
    from modules.transformer import transformar_registros
    import modules.firebase_client as fb

    transformados = transformar_registros(registros)
    nuevos = actualizados = 0

    for datos in transformados:
        num_doc = str(datos.get("numero_documento", "")).strip()
        if not num_doc:
            continue
        existe = fb.obtener_por_id(num_doc)
        if existe and existe.get("estado") == "completado":
            logger.debug(f"  {datos.get('nombre_empleado')} → ya completado, omitiendo")
            continue
        fb.crear_afiliacion(datos)
        if existe:
            actualizados += 1
        else:
            nuevos += 1

    logger.info(f"Firebase: {nuevos} nuevos | {actualizados} actualizados")

    # 3. Obtener pendientes y ejecutar RPA
    from modules.rpa_engine import ejecutar_proceso_completo
    pendientes = fb.obtener_pendientes()

    if not pendientes:
        logger.info("No hay afiliaciones pendientes. Finalizando.")
        return

    logger.info(f"Procesando {len(pendientes)} afiliación(es) pendiente(s)...")
    await ejecutar_proceso_completo(pendientes)

    # 4. Resumen final
    conteos = fb.contar_por_estado()
    logger.info("=" * 60)
    logger.info("RESUMEN FINAL:")
    logger.info(f"  ✅ Completados:          {conteos.get('completado', 0)}")
    logger.info(f"  🔴 Requieren revisión:   {conteos.get('requiere_intervencion', 0)}")
    logger.info(f"  ❌ Errores:              {conteos.get('error', 0)}")
    logger.info(f"  ⏳ Pendientes:           {conteos.get('pendiente', 0)}")
    logger.info("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
