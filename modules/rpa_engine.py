"""
Módulo: rpa_engine.py
Orquesta el proceso completo de afiliación para un empleado.
"""
import asyncio
import json
from pathlib import Path
from loguru import logger
from playwright.async_api import async_playwright, Browser, BrowserContext, Page

from config.settings import (
    ARL_USUARIO, ARL_PASSWORD, HEADLESS, TIMEOUT_MS,
    PORTAL_OPTIONS_DIR, MAX_INTENTOS
)
import modules.firebase_client as fb
from modules.form_filler import (
    hacer_login, navegar_a_afiliacion, _volver_al_home,
    llenar_formulario_inicial, llenar_datos_personales,
    llenar_datos_laborales, confirmar_afiliacion,
    obtener_opciones_dropdown, esperar_angular, screenshot,
    YaAfiliadoError
)


# ═══════════════════════════════════════════════════════════════════
# DESCUBRIMIENTO DE OPCIONES DEL PORTAL
# ═══════════════════════════════════════════════════════════════════

async def descubrir_opciones_portal(page: Page):
    """
    Navega al formulario de afiliación y extrae todas las opciones
    de los dropdowns importantes. Guarda los resultados en JSON.
    """
    logger.info("Iniciando descubrimiento de opciones del portal...")
    PORTAL_OPTIONS_DIR.mkdir(exist_ok=True)

    if not await navegar_a_afiliacion(page):
        logger.error("No se pudo navegar a afiliación para descubrimiento")
        return

    await esperar_angular(page)

    # Mapeo: nombre del archivo → formcontrolname del dropdown
    dropdowns_a_descubrir = {
        "empresas":           "empresa",
        "tipos_cotizante":    "tipoCotizante",
        "tipos_documento":    "tipoDocumento",
    }

    resultados = {}
    for nombre, formcontrol in dropdowns_a_descubrir.items():
        opciones = await obtener_opciones_dropdown(
            page, f"p-dropdown[formcontrolname='{formcontrol}']"
        )
        if opciones:
            resultados[nombre] = opciones
            archivo = PORTAL_OPTIONS_DIR / f"{nombre}.json"
            with open(archivo, "w", encoding="utf-8") as f:
                json.dump(opciones, f, ensure_ascii=False, indent=2)
            logger.info(f"  {nombre}: {len(opciones)} opciones guardadas")
        else:
            logger.warning(f"  {nombre}: sin opciones")

    # Para los dropdowns del paso 2 (datos personales), necesitamos avanzar
    # Usar datos de prueba para llegar al paso 2
    logger.info("Avanzando a datos personales para capturar más dropdowns...")

    # Se registra que el descubrimiento se hizo hasta este punto
    descubrimiento_status = PORTAL_OPTIONS_DIR / "descubrimiento_status.json"
    with open(descubrimiento_status, "w") as f:
        json.dump({
            "completado": True,
            "dropdowns_descubiertos": list(resultados.keys()),
            "total_opciones": {k: len(v) for k, v in resultados.items()}
        }, f, indent=2)

    logger.info("Descubrimiento completado ✓")
    return resultados


# ═══════════════════════════════════════════════════════════════════
# PROCESO DE AFILIACIÓN INDIVIDUAL
# ═══════════════════════════════════════════════════════════════════

async def procesar_afiliacion(page: Page, doc_id: str) -> dict:
    """
    Ejecuta el proceso completo de afiliación para un documento Firebase.
    Retorna: {exito: bool, mensaje: str}
    """
    # Cargar datos desde Firebase
    afiliacion = fb.obtener_por_id(doc_id)
    if not afiliacion:
        return {"exito": False, "mensaje": f"Documento {doc_id} no encontrado en Firebase"}

    nombre = afiliacion.get("nombre_empleado", "Desconocido")
    logger.info(f"━━━ Procesando: {nombre} ━━━")

    # Actualizar estado
    fb.actualizar_estado(doc_id, "en_proceso")
    fb.incrementar_intento(doc_id)

    # Obtener datos transformados + campos manuales
    datos = afiliacion.get("datos_transformados", {}).copy()
    campos_manuales = afiliacion.get("campos_manuales", {})
    datos.update(campos_manuales)  # Campos manuales sobreescriben los vacíos
    datos["nombre_empleado"] = nombre

    # Verificar que no quedan campos críticos vacíos
    campos_criticos_sin_fallback = [
        "empresa_arl", "numero_documento", "nombres", "apellidos",
        "fecha_nacimiento", "modalidad"
    ]
    campos_faltantes_criticos = [
        c for c in campos_criticos_sin_fallback
        if not datos.get(c)
    ]
    if campos_faltantes_criticos:
        msg = f"Campos críticos faltantes: {', '.join(campos_faltantes_criticos)}"
        logger.warning(f"{nombre}: {msg}")
        fb.marcar_campos_faltantes(doc_id, campos_faltantes_criticos)
        fb.agregar_log(doc_id, msg, "WARNING", "validacion_previa")
        return {"exito": False, "mensaje": msg, "requiere_intervencion": True}

    intentos = afiliacion.get("intentos", 0)
    tiene_datos_manuales = bool(afiliacion.get("campos_manuales"))
    # Solo bloquear si supera el límite Y el humano nunca intervino.
    # Si el humano ya guardó datos manuales, guardar_campos_manuales_bulk
    # resetea intentos=0, así que este check no debería dispararse.
    # Esta guarda extra es por si acaso se llama reiniciar_afiliacion
    # directamente sin pasar por el dashboard.
    if intentos >= MAX_INTENTOS and not tiene_datos_manuales:
        fb.actualizar_estado(doc_id, "error",
                             f"Máximo de intentos automáticos alcanzado ({MAX_INTENTOS}). "
                             "Abre el dashboard para corregir los datos y reiniciar.")
        return {
            "exito": False,
            "mensaje": f"Máximo de intentos automáticos alcanzado ({MAX_INTENTOS})",
            "requiere_intervencion": True,
        }

    try:
        # ── PASO 3: Formulario inicial ─────────────────────────────
        fb.agregar_log(doc_id, "Iniciando formulario inicial", "INFO", "paso_1")
        ok = await llenar_formulario_inicial(page, datos)
        if not ok:
            raise RuntimeError("Error en formulario inicial")

        # ── PASO 4: Datos personales ───────────────────────────────
        fb.agregar_log(doc_id, "Llenando datos personales", "INFO", "paso_2")
        ok = await llenar_datos_personales(page, datos)
        if not ok:
            raise RuntimeError("Error en datos personales")

        # ── PASO 5: Datos laborales ────────────────────────────────
        fb.agregar_log(doc_id, "Llenando datos laborales", "INFO", "paso_3")
        resultado_laboral = await llenar_datos_laborales(page, datos)
        if not resultado_laboral["exito"]:
            campos_fallidos = resultado_laboral["campos_fallidos"]
            msg = f"Campos no llenados automáticamente: {', '.join(campos_fallidos)}"
            logger.warning(f"{nombre}: {msg}")
            fb.marcar_campos_faltantes(doc_id, campos_fallidos)
            fb.agregar_log(doc_id, msg, "WARNING", "paso_3")
            return {"exito": False, "mensaje": msg, "requiere_intervencion": True}

        # ── PASO 6: Confirmar afiliación ───────────────────────────
        fb.agregar_log(doc_id, "Confirmando afiliación", "INFO", "paso_4")
        resultado = await confirmar_afiliacion(page)

        if resultado["exito"]:
            fb.guardar_resultado(
                doc_id,
                numero_afiliacion=resultado.get("numero_afiliacion"),
                mensaje=resultado.get("mensaje", "")
            )
            fb.agregar_log(
                doc_id,
                f"Afiliación exitosa ✓ N°: {resultado.get('numero_afiliacion', 'N/D')}",
                "INFO", "completado"
            )
            logger.info(f"{nombre} → AFILIADO ✓")
            return {"exito": True, "mensaje": resultado["mensaje"]}
        else:
            raise RuntimeError(resultado.get("mensaje", "Error desconocido en afiliación"))

    except YaAfiliadoError as e:
        msg = str(e)
        logger.info(f"{nombre} → YA AFILIADO (marcando como completado)")
        fb.guardar_resultado(
            doc_id,
            numero_afiliacion=None,
            mensaje=msg
        )
        fb.agregar_log(doc_id, msg, "INFO", "completado")
        return {"exito": True, "mensaje": msg, "ya_afiliado": True}

    except Exception as e:
        error_msg = str(e)
        logger.error(f"{nombre} → ERROR: {error_msg}")
        fb.agregar_log(doc_id, f"Error: {error_msg}", "ERROR", "error")
        fb.actualizar_estado(doc_id, "error", error_msg)
        return {"exito": False, "mensaje": error_msg}


# ═══════════════════════════════════════════════════════════════════
# ORQUESTADOR PRINCIPAL
# ═══════════════════════════════════════════════════════════════════

async def ejecutar_proceso_completo(
    doc_ids: list = None,
    solo_reintentos: bool = False,
    descubrir: bool = False
) -> dict:
    """
    Ejecuta el proceso RPA completo.

    Args:
        doc_ids: IDs específicos a procesar. Si None, toma todos los pendientes.
        solo_reintentos: Si True, procesa solo casos que requieren intervención ya completados.
        descubrir: Si True, ejecuta el descubrimiento de opciones del portal primero.

    Retorna resumen del proceso.
    """
    resumen = {
        "exitosos": [],
        "fallidos": [],
        "requieren_intervencion": [],
        "total_procesados": 0
    }

    if not ARL_USUARIO or not ARL_PASSWORD:
        logger.error("Credenciales ARL no configuradas. Verifica el archivo .env")
        return resumen

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=HEADLESS,
            slow_mo=50 if not HEADLESS else 0,
            args=["--no-sandbox", "--disable-blink-features=AutomationControlled"]
        )
        context = await browser.new_context(
            viewport={"width": 1280, "height": 900},
            locale="es-CO",
        )
        page = await context.new_page()

        try:
            # ── Login ────────────────────────────────────────────────
            login_ok = await hacer_login(page, ARL_USUARIO, ARL_PASSWORD)
            if not login_ok:
                logger.error("Login fallido. Verifica credenciales en .env")
                return resumen

            # ── Descubrimiento (opcional) ────────────────────────────
            if descubrir:
                await descubrir_opciones_portal(page)

            # ── Obtener registros a procesar ─────────────────────────
            if doc_ids:
                pendientes = [
                    fb.obtener_por_id(did)
                    for did in doc_ids
                    if fb.obtener_por_id(did)
                ]
            elif solo_reintentos:
                pendientes = fb.obtener_para_reintento()
                logger.info(f"Reintentos disponibles: {len(pendientes)}")
            else:
                pendientes = fb.obtener_pendientes()
                logger.info(f"Pendientes a procesar: {len(pendientes)}")

            if not pendientes:
                logger.info("No hay registros para procesar")
                return resumen

            # ── Procesar cada registro ───────────────────────────────
            for afiliacion in pendientes:
                doc_id = afiliacion["id"]
                nombre = afiliacion.get("nombre_empleado", doc_id)

                try:
                    logger.info(f"─── Preparando: {nombre} ───")

                    # navegar_a_afiliacion ya hace _volver_al_home internamente
                    nav_ok = await navegar_a_afiliacion(page)
                    if not nav_ok:
                        logger.error(f"No se pudo navegar para {nombre}")
                        resumen["fallidos"].append({
                            "id": doc_id, "nombre": nombre,
                            "error": "No se pudo navegar al formulario de afiliación"
                        })
                        fb.actualizar_estado(
                            doc_id, "error",
                            "No se pudo navegar al formulario de afiliación"
                        )
                        continue

                    resultado = await procesar_afiliacion(page, doc_id)
                    resumen["total_procesados"] += 1

                    if resultado.get("exito"):
                        resumen["exitosos"].append({"id": doc_id, "nombre": nombre})
                    elif resultado.get("requiere_intervencion"):
                        resumen["requieren_intervencion"].append({
                            "id": doc_id, "nombre": nombre,
                            "mensaje": resultado["mensaje"]
                        })
                    else:
                        resumen["fallidos"].append({
                            "id": doc_id, "nombre": nombre,
                            "error": resultado.get("mensaje", "Error desconocido")
                        })

                except Exception as e_emp:
                    # Error catastrófico en un empleado → registrar y seguir con el siguiente
                    logger.error(f"Error crítico procesando {nombre}: {e_emp}")
                    resumen["fallidos"].append({
                        "id": doc_id, "nombre": nombre,
                        "error": f"Error crítico: {e_emp}"
                    })
                    resumen["total_procesados"] += 1
                    try:
                        fb.actualizar_estado(doc_id, "error", str(e_emp))
                        fb.agregar_log(doc_id, f"Error crítico: {e_emp}", "ERROR", "error_critico")
                    except Exception:
                        pass

                # Pausa entre empleados (siempre, independiente del resultado)
                await asyncio.sleep(2)

        except Exception as e:
            logger.error(f"Error crítico en proceso RPA: {e}")
        finally:
            await browser.close()

    # Resumen final
    logger.info("=" * 50)
    logger.info(f"RESUMEN: {resumen['total_procesados']} procesados")
    logger.info(f"  ✅ Exitosos:              {len(resumen['exitosos'])}")
    logger.info(f"  ⚠️  Requieren revisión:    {len(resumen['requieren_intervencion'])}")
    logger.info(f"  ❌ Fallidos:              {len(resumen['fallidos'])}")
    logger.info("=" * 50)

    return resumen
