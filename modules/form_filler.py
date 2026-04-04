"""
Módulo: form_filler.py
Contiene todas las interacciones con formularios del portal ARL.
Cada paso del formulario es una función independiente.
"""
import asyncio
import re
import difflib
from pathlib import Path
from datetime import datetime
from loguru import logger
from playwright.async_api import Page, expect

from config.settings import TYPING_DELAY_MS, TIMEOUT_MS, SCREENSHOTS_DIR


# ───────────────────────────────────────────────────────────────────
# EXCEPCIÓN ESPECIAL: TRABAJADOR YA AFILIADO
# ───────────────────────────────────────────────────────────────────

class YaAfiliadoError(Exception):
    """
    Se lanza cuando el portal indica que el trabajador ya tiene
    afiliaciones vigentes ('El trabajador cuenta con afiliaciones vigentes').
    No es un error real — el registro debe marcarse como completado.
    """
    pass


async def detectar_ya_afiliado(page: Page) -> bool:
    """
    Detecta el modal 'El trabajador cuenta con afiliaciones vigentes'.
    Selectores basados en el HTML real del portal ARL Seguros Bolívar:
      - Título: h3.dialog__title
      - Botón Aceptar: div.buttons-row button.button-secondary
    Si aparece, hace click en Aceptar y retorna True.
    """
    try:
        # Selector exacto del título del modal según el HTML real del portal
        titulo = page.locator("h3.dialog__title:has-text('El trabajador cuenta con afiliaciones vigentes')")
        if await titulo.is_visible(timeout=3000):
            logger.info("Modal detectado: trabajador ya tiene afiliaciones vigentes.")
            # Botón Aceptar: button.button-secondary dentro de .buttons-row
            for sel in [
                "div.buttons-row button.button-secondary",
                "div.buttons-row button:has-text('Aceptar')",
                "div.dialog button.button-secondary",
                ".p-dynamic-dialog button.button-secondary",
            ]:
                try:
                    btn = page.locator(sel).first
                    if await btn.is_visible(timeout=1500):
                        await btn.click()
                        await asyncio.sleep(0.8)
                        logger.info("Modal 'ya afiliado' cerrado con Aceptar.")
                        break
                except Exception:
                    continue
            return True
    except Exception:
        pass
    return False


# ───────────────────────────────────────────────────────────────────
# UTILIDADES DE NORMALIZACIÓN PARA MATCHING DE ENTIDADES
# ───────────────────────────────────────────────────────────────────

# Siglas de tipo de entidad con puntos opcionales (aplicar ANTES de quitar puntuación)
_SIGLAS = re.compile(
    r"\bE\.?P\.?S\.?S?\.?\b|\bA\.?F\.?P\.?\b|\bS\.?A\.?S\.?\b|"
    r"\bS\.?A\.?\b|\bLTDA\.?\b|\bCIA\.?\b|\bCOMPANIA\b",
    re.IGNORECASE
)
# Palabras funcionales a eliminar (artículos, preposiciones)
_PALABRAS_FUNC = re.compile(
    r"\b(DE|DEL|LA|LAS|LOS|EL|Y|AND|&)\b", re.IGNORECASE
)
_PUNTUACION = re.compile(r"[.\-,;:()/]")
_ESPACIOS   = re.compile(r"\s+")

def _normalizar_entidad(texto: str) -> str:
    """
    Normaliza un nombre de EPS/AFP/entidad para comparación fuzzy.
    Elimina ruido: 'EPS', 'E.P.S', 'S.A.', 'S.A.S.', 'LTDA', puntuación.
    Ej: 'SALUD TOTAL E.P.S' → 'SALUD TOTAL'
        'EPS SURA S.A.'     → 'SURA'
    Orden: siglas con puntos → puntuación restante → palabras func → espacios
    """
    t = texto.upper().strip()
    t = _SIGLAS.sub(" ", t)           # Quita EPS, E.P.S, S.A., etc. (con sus puntos)
    t = _PUNTUACION.sub(" ", t)       # Quita puntuación restante
    t = _PALABRAS_FUNC.sub(" ", t)    # Quita artículos/preposiciones
    t = _ESPACIOS.sub(" ", t).strip()
    return t


def _mejor_match_fuzzy(valor: str, opciones: list, umbral: float = 0.65):
    """
    Busca la opción más parecida usando similitud de secuencias.
    Retorna (índice, texto_opcion, score) o None si nada supera el umbral.
    """
    valor_norm = _normalizar_entidad(valor)
    mejor_score = 0.0
    mejor_idx   = -1
    mejor_texto = ""

    for i, opcion in enumerate(opciones):
        opcion_norm = _normalizar_entidad(opcion)
        # SequenceMatcher compara las dos cadenas normalizadas
        score = difflib.SequenceMatcher(None, valor_norm, opcion_norm).ratio()
        if score > mejor_score:
            mejor_score = score
            mejor_idx   = i
            mejor_texto = opcion

    if mejor_score >= umbral:
        return mejor_idx, mejor_texto, mejor_score
    return None


async def screenshot(page: Page, nombre: str):
    """Toma y guarda screenshot para debugging."""
    SCREENSHOTS_DIR.mkdir(exist_ok=True)
    ts = datetime.now().strftime("%H%M%S")
    path = SCREENSHOTS_DIR / f"{ts}_{nombre}.png"
    await page.screenshot(path=str(path), full_page=False)
    logger.debug(f"Screenshot: {path.name}")


async def esperar_angular(page: Page, extra_ms: int = 500):
    """Espera a que Angular termine de renderizar."""
    try:
        await page.wait_for_load_state("networkidle", timeout=15000)
    except Exception:
        # networkidle puede fallar en SPAs que tienen conexiones abiertas permanentemente
        await asyncio.sleep(2)
    await asyncio.sleep(extra_ms / 1000)


async def digitar_humano(page: Page, selector: str, texto: str, limpiar: bool = True):
    """
    Digita texto simulando velocidad humana.
    Funciona incluso en inputs que bloquean copy/paste.
    """
    elemento = page.locator(selector).first
    await elemento.scroll_into_view_if_needed()
    await elemento.click()
    await asyncio.sleep(0.3)

    if limpiar:
        await elemento.fill("")
        await asyncio.sleep(0.1)

    for char in str(texto):
        await elemento.type(char, delay=TYPING_DELAY_MS)

    await asyncio.sleep(0.3)


async def seleccionar_dropdown_primeng(page: Page, formcontrolname: str, valor: str) -> bool:
    """
    Selecciona una opción en un p-dropdown de PrimeNG.
    Estrategia en cascada (3 niveles):
      1. Contiene exacto (mayúsculas)
      2. Contiene normalizado (sin 'EPS', 'S.A.', puntuación, etc.)
      3. Fuzzy matching ≥ 65 % de similitud
    Retorna True si tuvo éxito.
    """
    selector = f"p-dropdown[formcontrolname='{formcontrolname}']"

    try:
        dropdown = page.locator(selector).first
        await dropdown.scroll_into_view_if_needed()
        await dropdown.click()
        await asyncio.sleep(0.8)

        # Esperar panel de opciones
        panel = page.locator(".p-dropdown-panel").first
        await panel.wait_for(state="visible", timeout=5000)
        await asyncio.sleep(0.3)

        # Leer todas las opciones una sola vez
        items = page.locator(".p-dropdown-item")
        count = await items.count()
        textos = []
        for i in range(count):
            textos.append((await items.nth(i).inner_text()).strip())

        valor_up = valor.upper().strip()

        # ── Nivel 1: contiene exacto ─────────────────────────────
        for i, texto in enumerate(textos):
            texto_up = texto.upper()
            if valor_up in texto_up or texto_up in valor_up:
                await items.nth(i).click()
                await asyncio.sleep(0.5)
                logger.debug(f"Dropdown '{formcontrolname}' [L1] → '{texto}'")
                return True

        # ── Nivel 2: contiene normalizado ────────────────────────
        valor_norm = _normalizar_entidad(valor)
        for i, texto in enumerate(textos):
            texto_norm = _normalizar_entidad(texto)
            if valor_norm in texto_norm or texto_norm in valor_norm:
                await items.nth(i).click()
                await asyncio.sleep(0.5)
                logger.warning(
                    f"Dropdown '{formcontrolname}' [L2-norm] '{valor}' → '{texto}'"
                )
                return True

        # ── Nivel 3: fuzzy matching (sobre items ya cargados) ───────
        resultado = _mejor_match_fuzzy(valor, textos, umbral=0.65)
        if resultado:
            idx, texto_match, score = resultado
            await items.nth(idx).click()
            await asyncio.sleep(0.5)
            logger.warning(
                f"Dropdown '{formcontrolname}' [L3-fuzzy {score:.0%}] '{valor}' → '{texto_match}'"
            )
            return True

        # ── Nivel 4: keyboard.type() directo con foco en el dropdown ───
        # PrimeNG intercepta keypresses cuando el panel está abierto.
        # Si el dropdown tiene filtro, los caracteres van al input del filtro.
        # Si no tiene filtro, navega al ítem que comienza con esa letra.
        # CRÍTICO: NO hacer click en nada — mantener foco en el dropdown.
        valor_norm_short = _normalizar_entidad(valor)
        texto_busqueda = (valor_norm_short or valor_up)[:8]

        try:
            # Reforzar foco en el p-dropdown sin mover el panel
            await dropdown.focus()
            await asyncio.sleep(0.2)

            # Tipear con delay generoso para que PrimeNG procese cada char
            await page.keyboard.type(texto_busqueda, delay=180)
            await asyncio.sleep(1.2)  # Esperar que Angular filtre y re-renderice

            new_count = await items.count()
            textos_despues = []
            for i in range(new_count):
                t = (await items.nth(i).inner_text()).strip()
                if t:
                    textos_despues.append(t)

            logger.debug(f"Dropdown '{formcontrolname}' [L4-type] {len(textos_despues)} ítems tras buscar '{texto_busqueda}': {textos_despues[:5]}")

            # Verificar con los 3 niveles sobre los items actuales
            for texto in textos_despues:
                texto_up2 = texto.upper()
                if valor_up in texto_up2 or texto_up2 in valor_up:
                    for j in range(new_count):
                        if (await items.nth(j).inner_text()).strip().upper() == texto_up2:
                            await items.nth(j).click()
                            await asyncio.sleep(0.5)
                            logger.warning(f"Dropdown '{formcontrolname}' [L4-type-exact] '{valor}' → '{texto}'")
                            return True

            for texto in textos_despues:
                if valor_norm in _normalizar_entidad(texto) or _normalizar_entidad(texto) in valor_norm:
                    for j in range(new_count):
                        if (await items.nth(j).inner_text()).strip() == texto:
                            await items.nth(j).click()
                            await asyncio.sleep(0.5)
                            logger.warning(f"Dropdown '{formcontrolname}' [L4-type-norm] '{valor}' → '{texto}'")
                            return True

            resultado = _mejor_match_fuzzy(valor, textos_despues, umbral=0.55)
            if resultado:
                idx, texto_match, score = resultado
                await items.nth(idx).click()
                await asyncio.sleep(0.5)
                logger.warning(f"Dropdown '{formcontrolname}' [L4-type-fuzzy {score:.0%}] '{valor}' → '{texto_match}'")
                return True
        except Exception as e:
            logger.debug(f"L4 keyboard.type falló: {e}")

        # ── Nivel 5: JavaScript — forzar valor en el filtro PrimeNG ─────
        # Usa el setter nativo para disparar los eventos que Angular detecta
        try:
            filter_result = await page.evaluate(f"""
                () => {{
                    const panel = document.querySelector('.p-dropdown-panel');
                    if (!panel) return 'no-panel';
                    const filterInput = panel.querySelector('input');
                    if (!filterInput) return 'no-filter';
                    const setter = Object.getOwnPropertyDescriptor(
                        window.HTMLInputElement.prototype, 'value'
                    ).set;
                    setter.call(filterInput, '{texto_busqueda}');
                    filterInput.dispatchEvent(new KeyboardEvent('keydown', {{bubbles: true, cancelable: true}}));
                    filterInput.dispatchEvent(new InputEvent('input', {{bubbles: true, data: '{texto_busqueda}', inputType: 'insertText'}}));
                    filterInput.dispatchEvent(new KeyboardEvent('keyup', {{bubbles: true}}));
                    return 'ok';
                }}
            """)
            logger.debug(f"L5 JS filter result: {filter_result}")
            await asyncio.sleep(1.0)

            if filter_result == 'ok':
                new_count = await items.count()
                textos_js = []
                for i in range(new_count):
                    t = (await items.nth(i).inner_text()).strip()
                    if t:
                        textos_js.append(t)
                logger.debug(f"Dropdown '{formcontrolname}' [L5-JS] ítems tras filtro JS: {textos_js[:8]}")
                resultado = _mejor_match_fuzzy(valor, textos_js, umbral=0.55)
                if resultado:
                    idx, texto_match, score = resultado
                    await items.nth(idx).click()
                    await asyncio.sleep(0.5)
                    logger.warning(f"Dropdown '{formcontrolname}' [L5-JS-fuzzy {score:.0%}] '{valor}' → '{texto_match}'")
                    return True
        except Exception as e:
            logger.debug(f"L5 JS filter falló: {e}")

        # Cerrar dropdown sin seleccionar
        await page.keyboard.press("Escape")
        await asyncio.sleep(0.3)
        logger.error(
            f"Dropdown '{formcontrolname}': '{valor}' no encontrado en ningún nivel. "
            f"Opciones visibles iniciales: {textos[:8]}"
        )
        return False

    except Exception as e:
        logger.error(f"Error en dropdown '{formcontrolname}': {e}")
        await screenshot(page, f"error_dropdown_{formcontrolname}")
        # Si hubo timeout, verificar si el modal "ya afiliado" está bloqueando la página
        if "Timeout" in str(e) or "timeout" in str(e):
            if await detectar_ya_afiliado(page):
                raise YaAfiliadoError("El trabajador ya cuenta con afiliaciones vigentes en el sistema ARL.")
        return False


async def seleccionar_dropdown_por_id(page: Page, dropdown_id: str, valor: str) -> bool:
    """Versión para dropdowns identificados por ID en lugar de formcontrolname."""
    selector = f"p-dropdown#{dropdown_id}"
    try:
        dropdown = page.locator(selector).first
        await dropdown.scroll_into_view_if_needed()
        await dropdown.click()
        await asyncio.sleep(0.8)

        panel = page.locator(".p-dropdown-panel").first
        await panel.wait_for(state="visible", timeout=5000)

        opciones = page.locator(".p-dropdown-item")
        count = await opciones.count()
        valor_norm = valor.upper().strip()

        for i in range(count):
            opcion = opciones.nth(i)
            texto = (await opcion.inner_text()).strip().upper()
            if valor_norm in texto or texto in valor_norm:
                await opcion.click()
                await asyncio.sleep(0.5)
                return True

        await page.keyboard.press("Escape")
        logger.error(f"Dropdown ID '{dropdown_id}': '{valor}' no encontrado")
        return False
    except Exception as e:
        logger.error(f"Error dropdown ID '{dropdown_id}': {e}")
        return False


async def obtener_opciones_dropdown(page: Page, selector: str) -> list:
    """
    Extrae todas las opciones de un p-dropdown del portal.
    Útil para el script de descubrimiento.
    """
    try:
        dropdown = page.locator(selector).first
        await dropdown.scroll_into_view_if_needed()
        await dropdown.click()
        await asyncio.sleep(1)

        panel = page.locator(".p-dropdown-panel").first
        await panel.wait_for(state="visible", timeout=5000)
        await asyncio.sleep(0.5)

        opciones = page.locator(".p-dropdown-item")
        count = await opciones.count()
        textos = []
        for i in range(count):
            texto = (await opciones.nth(i).inner_text()).strip()
            if texto:
                textos.append(texto)

        await page.keyboard.press("Escape")
        await asyncio.sleep(0.3)
        return textos

    except Exception as e:
        logger.error(f"Error obteniendo opciones de '{selector}': {e}")
        return []


async def click_boton_siguiente(page: Page) -> bool:
    """
    Hace click en el botón 'Siguiente'.
    Si está deshabilitado, retorna False inmediatamente sin hacer timeout.
    """
    try:
        selectores = [
            "button:has-text('Siguiente')",
            "button.btn-siguiente",
            "button[type='submit']:has-text('Siguiente')",
        ]
        for sel in selectores:
            btn = page.locator(sel).first
            try:
                visible = await btn.is_visible(timeout=3000)
            except Exception:
                continue
            if not visible:
                continue

            # Verificar si está deshabilitado ANTES de intentar hacer click
            disabled = await btn.get_attribute("disabled")
            if disabled is not None:
                logger.warning("Botón 'Siguiente' está deshabilitado — formulario incompleto")
                return False

            await btn.scroll_into_view_if_needed()
            await btn.click()
            await asyncio.sleep(1)
            await esperar_angular(page)
            logger.debug("Botón 'Siguiente' presionado ✓")
            return True

        logger.error("No se encontró botón 'Siguiente'")
        return False
    except Exception as e:
        logger.error(f"Error en botón Siguiente: {e}")
        return False


# ═══════════════════════════════════════════════════════════════════
# PASO 1: LOGIN
# ═══════════════════════════════════════════════════════════════════

async def hacer_login(page: Page, usuario: str, password: str) -> bool:
    """Realiza el login en el portal ARL Seguros Bolívar."""
    from config.settings import ARL_URL

    logger.info("Iniciando login en portal ARL...")

    try:
        await page.goto(ARL_URL, wait_until="networkidle", timeout=30000)
        await asyncio.sleep(3)

        # El portal redirige a un formulario de login clásico (no Angular)
        # Esperar que cargue el formulario
        await page.wait_for_load_state("domcontentloaded")
        await asyncio.sleep(2)

        # Campo usuario — puede ser Identification o username
        campo_usuario = page.locator(
            "input[name='Ecom_User_ID'], "
            "input[name='username'], "
            "input[name='user'], "
            "input[type='text']:visible, "
            "#Ecom_User_ID"
        ).first
        await campo_usuario.wait_for(state="visible", timeout=15000)
        await campo_usuario.click()
        await asyncio.sleep(0.3)
        # Seleccionar todo y reemplazar (compatible con todas las versiones)
        await page.keyboard.press("Meta+a")
        await asyncio.sleep(0.1)
        await page.keyboard.press("Backspace")
        await asyncio.sleep(0.1)
        for char in str(usuario):
            await page.keyboard.type(char)
            await asyncio.sleep(0.08)
        await asyncio.sleep(0.8)

        # Campo contraseña
        campo_pass = page.locator(
            "input[name='Ecom_Password'], "
            "input[name='password'], "
            "input[type='password']:visible"
        ).first
        await campo_pass.wait_for(state="visible", timeout=10000)
        await campo_pass.click()
        await asyncio.sleep(0.3)
        await page.keyboard.press("Meta+a")
        await asyncio.sleep(0.1)
        await page.keyboard.press("Backspace")
        await asyncio.sleep(0.1)
        for char in str(password):
            await page.keyboard.type(char)
            await asyncio.sleep(0.08)
        await asyncio.sleep(0.8)

        # Botón INGRESA — en el portal es un input[type='submit'] con value='INGRESA'
        btn_login = page.locator(
            "input[type='submit'][value='INGRESA'], "
            "input[type='submit'][value='Ingresar'], "
            "input[type='submit'][value='INGRESAR'], "
            "input[type='image'], "
            "button:has-text('INGRESA'), "
            "button:has-text('Ingresar'), "
            "button[type='submit']"
        ).first
        await btn_login.wait_for(state="visible", timeout=10000)
        await btn_login.click()
        await asyncio.sleep(5)

        # Esperar que la página cargue (sea lo que sea que aparezca después del login)
        await page.wait_for_load_state("domcontentloaded", timeout=30000)
        await asyncio.sleep(3)

        url_actual = page.url
        logger.info(f"URL después del login: {url_actual}")
        await screenshot(page, "post_login")

        # Verificar si hubo error de credenciales (seguimos en la página de login)
        login_indicators = ["nidp", "login", "signin", "ingresa"]
        if any(ind in url_actual.lower() for ind in login_indicators):
            # Comprobar si hay mensaje de error visible
            try:
                error_msg = await page.locator(
                    ".error, .alert, [class*='error'], [class*='invalid'], "
                    "p:has-text('incorrecto'), p:has-text('inválido'), "
                    "span:has-text('incorrecto')"
                ).first.inner_text()
                logger.error(f"Error de credenciales: {error_msg}")
            except Exception:
                logger.warning("Login posiblemente fallido — aún en página de login")
            await screenshot(page, "error_credenciales")
            return False

        # Si llegamos al portal Angular
        if "arlonline" in url_actual and "#" in url_actual:
            await esperar_angular(page)
            logger.info("Login exitoso — portal Angular cargado ✓")
            return True

        # Puede haber una página intermedia (selección de perfil, avisos, etc.)
        # Intentar navegar directo al home del portal
        logger.info("Página intermedia detectada, navegando al home...")
        await page.goto(ARL_URL, wait_until="networkidle", timeout=20000)
        await asyncio.sleep(3)
        await screenshot(page, "post_login_home")

        url_final = page.url
        logger.info(f"URL final: {url_final}")

        if "arlonline" in url_final:
            logger.info("Login exitoso ✓")
            return True

        logger.error(f"No se pudo confirmar login. URL final: {url_final}")
        return False

    except Exception as e:
        await screenshot(page, "error_login")
        logger.error(f"Error en login: {e}")
        return False


# ═══════════════════════════════════════════════════════════════════
# PASO 2: NAVEGAR A AFILIACIÓN
# ═══════════════════════════════════════════════════════════════════

async def _cerrar_modales(page: Page):
    """
    Cierra cualquier modal, overlay o diálogo que esté bloqueando la pantalla.
    Se llama antes de intentar hacer click en las tarjetas del home.
    """
    botones_cerrar = [
        "button.p-dialog-header-close",
        "button[aria-label='Close']",
        "button:has-text('Cerrar')",
        "button:has-text('Aceptar')",
        "button:has-text('OK')",
        ".p-dialog-footer button",
        ".modal-footer button",
    ]
    for sel in botones_cerrar:
        try:
            btn = page.locator(sel).first
            if await btn.is_visible(timeout=800):
                await btn.click()
                await asyncio.sleep(0.5)
                logger.debug(f"Modal cerrado con: {sel}")
        except Exception:
            continue

    # También intentar presionar Escape para cerrar overlays
    try:
        await page.keyboard.press("Escape")
        await asyncio.sleep(0.3)
    except Exception:
        pass


async def _volver_al_home(page: Page):
    """
    Navega de vuelta al home del portal para empezar desde cero.

    Problema con Angular SPA + hash routing:
    page.goto('#/home') NO fuerza recarga si el router Angular intercepta.
    Solución: navegar a la URL BASE (sin hash) para forzar recarga completa,
    lo cual resetea el router Angular y carga el home correctamente.
    """
    from config.settings import ARL_URL
    logger.info("Volviendo al home del portal...")
    try:
        # Separar URL base del hash
        base_url = ARL_URL.split("#")[0]  # e.g. "https://arlonline.segurosbolivar.com/portal/arl/"

        # Forzar recarga completa navegando a la URL base (sin hash)
        # Esto borra el estado del router Angular
        await page.goto(base_url, wait_until="domcontentloaded", timeout=30000)
        await asyncio.sleep(2)

        # Si el portal no redirige solo al home, forzar el hash
        if "#/home" not in page.url:
            await page.evaluate("window.location.hash = '#/home'")
            await asyncio.sleep(2)

        await esperar_angular(page)
        await _cerrar_modales(page)
        await asyncio.sleep(1)
        await screenshot(page, "volver_al_home")
        logger.debug(f"Home cargado: {page.url}")
    except Exception as e:
        logger.warning(f"Error volviendo al home: {e}")
        try:
            # Último recurso: recarga total
            await page.reload(wait_until="domcontentloaded", timeout=20000)
            await asyncio.sleep(3)
        except Exception:
            pass


async def navegar_a_afiliacion(page: Page) -> bool:
    """
    Navega a la sección 'Afiliación de trabajadores' y luego a 'Afiliación individual'.

    Flujo típico del portal:
      1. Home → click en card 'Afiliación de trabajadores'
      2. Sub-menú → click en 'Afiliación individual' (si aparece)
      3. Formulario inicial con p-dropdown[formcontrolname='empresa']
    """
    logger.info("Navegando a Afiliación de trabajadores...")

    try:
        # ── Paso A: Siempre volver al home limpio ────────────────────
        # Nota: ejecutar_proceso_completo ya llamó _volver_al_home, pero
        # navegar_a_afiliacion lo hace de nuevo para garantizar estado limpio
        # y cerrar posibles modales del empleado anterior.
        await _volver_al_home(page)
        await esperar_angular(page)

        # ── Paso B: Click en la card 'Afiliación de trabajadores' ──────
        opciones_a_intentar = [
            ".accesos__acceso:has-text('Afiliación de trabajadores')",
            "div.accesos__acceso:has-text('Afiliación')",
            "div[class*='acceso']:has-text('Afiliación de trabajadores')",
            "p.titulo:has-text('Afiliación de trabajadores')",
        ]

        # Esperar hasta 10 s a que aparezca la tarjeta (Angular puede tardar)
        clickeado = False
        for intento_nav in range(2):  # 2 intentos: normal + reintento con más espera
            for sel in opciones_a_intentar:
                try:
                    opcion = page.locator(sel).first
                    if await opcion.is_visible(timeout=5000):
                        await opcion.scroll_into_view_if_needed()
                        await opcion.click()
                        logger.info(f"  Click en tarjeta con selector: {sel}")
                        clickeado = True
                        break
                except Exception:
                    continue
            if clickeado:
                break
            if intento_nav == 0:
                # Primer intento falló → esperar más y cerrar posibles overlays
                logger.warning("Tarjeta no visible aún, esperando 5s más...")
                await asyncio.sleep(5)
                await _cerrar_modales(page)

        if not clickeado:
            await screenshot(page, "no_se_encontro_tarjeta_afiliacion")
            logger.error("No se encontró la tarjeta 'Afiliación de trabajadores'")
            return False

        # Esperar que Angular cargue la nueva pantalla
        await asyncio.sleep(2)
        await esperar_angular(page)
        await screenshot(page, "post_click_afiliacion_card")
        logger.info(f"  URL después del click: {page.url}")

        # ── Paso C: Sub-menú opcional → 'Afiliación individual' ────────
        # Después de hacer click en la card, el portal puede mostrar un sub-menú
        # con opciones: "Afiliación individual" / "Afiliación masiva" / etc.
        sub_opciones = [
            "button:has-text('Afiliación individual')",
            "a:has-text('Afiliación individual')",
            "span:has-text('Afiliación individual')",
            "li:has-text('Afiliación individual')",
            "div:has-text('Afiliación individual')",
            ".accesos__acceso:has-text('individual')",
            "p.titulo:has-text('individual')",
            # También puede llamarse "Nueva afiliación"
            "button:has-text('Nueva afiliación')",
            "a:has-text('Nueva afiliación')",
            "div:has-text('Nueva afiliación')",
            "p.titulo:has-text('Nueva afiliación')",
        ]

        for sel in sub_opciones:
            try:
                btn = page.locator(sel).first
                if await btn.is_visible(timeout=2000):
                    logger.info(f"  Sub-opción encontrada: {sel}")
                    await btn.scroll_into_view_if_needed()
                    await btn.click()
                    await asyncio.sleep(2)
                    await esperar_angular(page)
                    await screenshot(page, "post_click_individual")
                    logger.info(f"  URL después de sub-opción: {page.url}")
                    break
            except Exception:
                continue

        # ── Paso D: Verificar que el formulario está presente ──────────
        # Esperar el dropdown de empresa (primer campo del formulario)
        try:
            empresa_dropdown = page.locator(
                "p-dropdown[formcontrolname='empresa'], "
                "p-dropdown[ng-reflect-name='empresa']"
            ).first
            await empresa_dropdown.wait_for(state="visible", timeout=10000)
            logger.info("Formulario de afiliación cargado ✓ (dropdown empresa visible)")
            return True
        except Exception:
            # El formulario no apareció — tomar screenshot para diagnóstico
            await screenshot(page, "formulario_no_encontrado")
            logger.warning(
                "Dropdown 'empresa' no encontrado después de la navegación. "
                "Revisando la pantalla actual..."
            )

            # Intentar detectar qué hay en pantalla para ayudar al diagnóstico
            try:
                titulos = await page.locator("h1, h2, h3, p.titulo, .page-title").all_inner_texts()
                logger.info(f"  Títulos visibles en pantalla: {titulos}")
            except Exception:
                pass

            try:
                botones = await page.locator("button:visible").all_inner_texts()
                logger.info(f"  Botones visibles: {botones[:10]}")
            except Exception:
                pass

            # Retornar False pero NO crashear — el orquestador decidirá
            return False

    except Exception as e:
        await screenshot(page, "error_navegacion_afiliacion")
        logger.error(f"Error navegando a afiliación: {e}")
        return False


# ═══════════════════════════════════════════════════════════════════
# PASO 3: FORMULARIO INICIAL (empresa, tipo cotizante, documento)
# ═══════════════════════════════════════════════════════════════════

async def llenar_formulario_inicial(page: Page, datos: dict) -> bool:
    """Llena el primer formulario: empresa, tipo cotizante, tipo y número de documento."""
    logger.info(f"Formulario inicial: {datos.get('nombre_empleado', '')}")

    try:
        await esperar_angular(page)

        # 1. Empresa
        empresa_ok = await seleccionar_dropdown_primeng(
            page, "empresa", datos["empresa_arl"]
        )
        if not empresa_ok:
            logger.error(f"No se pudo seleccionar empresa: {datos['empresa_arl']}")
            return False

        await asyncio.sleep(0.5)

        # 2. Tipo cotizante → "1-DEPENDIENTE"
        await seleccionar_dropdown_primeng(
            page, "tipoCotizante", datos["tipo_cotizante"]
        )

        await asyncio.sleep(0.5)

        # 3. Tipo de documento
        await seleccionar_dropdown_primeng(
            page, "tipoDocumento", datos["tipo_documento"]
        )

        # Esperar que Angular muestre el campo de número (puede aparecer condicionalmente)
        await asyncio.sleep(1.5)
        await esperar_angular(page)
        await screenshot(page, "post_tipo_documento")

        # 4. Número de documento — el portal usa formcontrolname='numeroIdentificacion'
        selectores_num_doc = [
            "input[formcontrolname='numeroIdentificacion']",   # nombre real del portal ✓
            "#identification",                                  # id real del portal ✓
            "input[placeholder*='número de identificación']",
            "input[placeholder*='identificación']",
            "input[formcontrolname='numeroDocumento']",        # fallbacks anteriores
            "#numeroDocumento",
            "input[id='numeroDocumento']",
            "input[placeholder*='documento']",
            "input[placeholder*='Documento']",
        ]
        campo_num_doc = None
        for sel in selectores_num_doc:
            try:
                elem = page.locator(sel).first
                if await elem.is_visible(timeout=2000):
                    campo_num_doc = sel
                    logger.debug(f"Campo número doc encontrado: {sel}")
                    break
            except Exception:
                continue

        if not campo_num_doc:
            # Último recurso: buscar todos los inputs visibles después de los dropdowns
            await screenshot(page, "no_campo_numero_doc")
            logger.warning("Campo número documento no encontrado con selectores conocidos")
            # Intentar con cualquier input de texto visible que no sea un dropdown
            try:
                inputs_visibles = page.locator(
                    "input[type='text']:visible, input[type='number']:visible, input:not([type]):visible"
                )
                count = await inputs_visibles.count()
                logger.info(f"  Inputs visibles en pantalla: {count}")
                if count > 0:
                    # Listar los inputs para diagnóstico
                    for i in range(min(count, 5)):
                        inp = inputs_visibles.nth(i)
                        id_attr = await inp.get_attribute("id") or ""
                        name_attr = await inp.get_attribute("name") or ""
                        fc_attr = await inp.get_attribute("formcontrolname") or ""
                        ph_attr = await inp.get_attribute("placeholder") or ""
                        logger.info(f"    input[{i}]: id='{id_attr}' name='{name_attr}' "
                                    f"formcontrolname='{fc_attr}' placeholder='{ph_attr}'")
                    # Usar el último input visible (que suele ser el de número de doc)
                    campo_num_doc = "input[type='text']:visible, input[type='number']:visible, input:not([type]):visible"
            except Exception as ex:
                logger.error(f"No se pudo detectar inputs: {ex}")
            if not campo_num_doc:
                return False

        # Usar el input encontrado — digitar carácter a carácter (Angular requiere eventos)
        locator_inputs = page.locator(campo_num_doc)
        campo = locator_inputs.last
        await campo.scroll_into_view_if_needed()
        await campo.click()
        await asyncio.sleep(0.2)
        await page.keyboard.press("Control+a")
        await page.keyboard.press("Backspace")
        await asyncio.sleep(0.1)
        num_doc_str = str(datos["numero_documento"])
        for char in num_doc_str:
            await page.keyboard.type(char)
            await asyncio.sleep(0.05)
        await asyncio.sleep(0.5)

        await asyncio.sleep(0.5)

        # 5. Click Siguiente
        ok = await click_boton_siguiente(page)

        # 6. Verificar si el portal indica que ya está afiliado
        if await detectar_ya_afiliado(page):
            raise YaAfiliadoError("El trabajador ya cuenta con afiliaciones vigentes en el sistema ARL.")

        return ok

    except YaAfiliadoError:
        raise  # Dejar que rpa_engine la capture y marque como completado
    except Exception as e:
        await screenshot(page, "error_formulario_inicial")
        logger.error(f"Error en formulario inicial: {e}")
        return False


# ═══════════════════════════════════════════════════════════════════
# PASO 4: DATOS PERSONALES
# ═══════════════════════════════════════════════════════════════════

async def _campo_habilitado(page: Page, selector: str) -> bool:
    """Verifica si un campo existe y está habilitado (no disabled)."""
    try:
        elem = page.locator(selector).first
        if not await elem.is_visible(timeout=2000):
            return False
        disabled = await elem.get_attribute("disabled")
        return disabled is None  # None = no tiene atributo disabled → habilitado
    except Exception:
        return False


async def digitar_si_habilitado(page: Page, selector: str, valor: str):
    """
    Digita en un campo solo si existe y está habilitado.
    El portal ARL auto-rellena nombres/apellidos desde la cédula y los deja disabled.
    """
    if not valor:
        return
    habilitado = await _campo_habilitado(page, selector)
    if habilitado:
        await digitar_humano(page, selector, valor)
    else:
        logger.debug(f"Campo '{selector}' está disabled (auto-rellenado por el portal) — omitiendo")


async def llenar_datos_personales(page: Page, datos: dict) -> bool:
    """
    Llena el formulario de datos personales.

    NOTA: El portal ARL consulta RUAF/BDUA con la cédula del paso anterior
    y auto-rellena nombres y apellidos poniéndolos en disabled.
    Por eso se usan funciones que verifican si el campo está habilitado antes de escribir.
    """
    logger.info("Formulario datos personales...")

    try:
        await esperar_angular(page)

        # ── Verificar modal "ya afiliado" ──────────────────────────────
        # El portal consulta el backend de forma ASÍNCRONA después de cargar
        # la página de datos personales. El modal puede tardar 3-8 segundos
        # en aparecer. Esperamos un tiempo prudente antes de verificar.
        await asyncio.sleep(5)
        if await detectar_ya_afiliado(page):
            raise YaAfiliadoError("El trabajador ya cuenta con afiliaciones vigentes en el sistema ARL.")

        await screenshot(page, "inicio_datos_personales")

        # Nombres — el portal los puede rellenar automáticamente (disabled)
        await digitar_si_habilitado(
            page, "#nombres, input[formcontrolname='nombres']",
            datos.get("nombres", "")
        )

        # Apellidos — igual, puede estar disabled
        await digitar_si_habilitado(
            page, "#apellidos, input[formcontrolname='apellidos']",
            datos.get("apellidos", "")
        )

        await asyncio.sleep(0.3)

        # Fecha de nacimiento — p-calendar de PrimeNG
        # El ID real puede variar; probamos varios selectores
        fecha_nac = datos.get("fecha_nacimiento")
        if fecha_nac:
            # Detectar qué input es el de fecha de nacimiento
            selectores_fecha = [
                "#fechaNacimiento",
                "poc-refarl-calendar[formcontrolname='fechaNacimiento'] input",
                "p-calendar[formcontrolname='fechaNacimiento'] input",
                "input[id*='fechaNacimiento']",
                "input[placeholder*='DD/MM']",
            ]
            input_id_fecha = None
            for sel in selectores_fecha:
                try:
                    loc = page.locator(sel).first
                    if await loc.is_visible(timeout=2000):
                        # Extraer el id del elemento para pasarlo a llenar_fecha_pcalendar
                        el_id = await loc.get_attribute("id")
                        if el_id:
                            input_id_fecha = el_id
                        else:
                            # Sin id propio: usar el selector directo pasando el locator
                            input_id_fecha = "__locator__"
                        logger.debug(f"Campo fecha nacimiento encontrado con: {sel}")
                        break
                except Exception:
                    continue

            if input_id_fecha:
                if input_id_fecha == "__locator__":
                    # Usar el selector directo con la versión de llenar_fecha por selector
                    ok = await llenar_fecha_por_selector(
                        page, sel, fecha_nac
                    )
                else:
                    ok = await llenar_fecha_pcalendar(page, input_id_fecha, fecha_nac)
                if not ok:
                    logger.warning(f"No se pudo llenar fecha de nacimiento: {fecha_nac}")
            else:
                logger.warning("No se encontró el input de fecha de nacimiento en el formulario")

        await asyncio.sleep(0.3)

        # Sexo/Género
        if datos.get("sexo"):
            await seleccionar_dropdown_primeng(page, "sexoVariable", datos["sexo"])

        await asyncio.sleep(0.3)

        # Email
        await digitar_si_habilitado(
            page, "#email, input[formcontrolname='email']",
            datos.get("email", "")
        )

        # Celular
        await digitar_si_habilitado(
            page, "#celular, input[formcontrolname='celular']",
            datos.get("celular", "")
        )

        # Teléfono (opcional)
        await digitar_si_habilitado(
            page, "#telefono, input[formcontrolname='telefono']",
            datos.get("telefono", "")
        )

        # Dirección
        await digitar_si_habilitado(
            page, "#direccion, input[formcontrolname='direccion']",
            datos.get("direccion", "")
        )

        await asyncio.sleep(0.3)

        # Ciudad
        if datos.get("ciudad"):
            await seleccionar_dropdown_primeng(page, "ciudad", datos["ciudad"])

        # Zona → URBANA
        await seleccionar_dropdown_primeng(page, "zona", datos.get("zona", "URBANA"))

        await asyncio.sleep(0.5)

        return await click_boton_siguiente(page)

    except YaAfiliadoError:
        raise  # Propagar para que rpa_engine la marque como completado
    except Exception as e:
        await screenshot(page, "error_datos_personales")
        logger.error(f"Error en datos personales: {e}")
        return False


# ═══════════════════════════════════════════════════════════════════
# PASO 5: DATOS LABORALES
# ═══════════════════════════════════════════════════════════════════

async def seleccionar_primera_opcion_dropdown(page: Page, formcontrolname: str) -> bool:
    """
    Selecciona la PRIMERA opción disponible en un p-dropdown.
    Útil para campos como 'centroTrabajo' donde no conocemos el texto exacto.
    """
    selector = f"p-dropdown[formcontrolname='{formcontrolname}']"
    try:
        dropdown = page.locator(selector).first
        await dropdown.scroll_into_view_if_needed()
        await dropdown.click()
        await asyncio.sleep(0.8)
        panel = page.locator(".p-dropdown-panel").first
        await panel.wait_for(state="visible", timeout=5000)
        await asyncio.sleep(0.3)
        primera_opcion = page.locator(".p-dropdown-item").first
        texto = (await primera_opcion.inner_text()).strip()
        await primera_opcion.click()
        await asyncio.sleep(0.5)
        logger.debug(f"Dropdown '{formcontrolname}' → primera opción: '{texto}'")
        return True
    except Exception as e:
        logger.error(f"Error seleccionando primera opción de '{formcontrolname}': {e}")
        return False


async def llenar_autocomplete_cargo(page: Page, cargo: str) -> bool:
    """
    Llena el campo 'cargo' que es un p-autocomplete (no p-dropdown).
    Tipea el texto y espera sugerencias, luego selecciona la primera.
    """
    try:
        # El input del p-autocomplete tiene class 'p-autocomplete-input'
        input_cargo = page.locator(
            "p-autocomplete[formcontrolname='cargo'] input.p-autocomplete-input, "
            "p-autocomplete[formcontrolname='cargo'] input"
        ).first
        await input_cargo.scroll_into_view_if_needed()
        await input_cargo.click()
        await asyncio.sleep(0.3)

        # Limpiar y tipear el cargo carácter a carácter
        await page.keyboard.press("Control+a")
        await page.keyboard.press("Backspace")
        cargo_texto = str(cargo).strip()
        for char in cargo_texto:
            await page.keyboard.type(char)
            await asyncio.sleep(0.05)
        await asyncio.sleep(1.0)  # Esperar sugerencias del autocomplete

        # Esperar el panel de sugerencias
        panel_sugerencias = page.locator(
            ".custom-autocomplete__panel, .p-autocomplete-panel, ul.p-autocomplete-items"
        ).first
        try:
            await panel_sugerencias.wait_for(state="visible", timeout=4000)
            await asyncio.sleep(0.3)
            # Seleccionar la primera sugerencia
            primera = page.locator(
                ".p-autocomplete-item, li.p-autocomplete-item"
            ).first
            texto_sugerencia = (await primera.inner_text()).strip()
            await primera.click()
            await asyncio.sleep(0.5)
            logger.debug(f"Cargo autocomplete → '{texto_sugerencia}'")
            return True
        except Exception:
            # Si no hay sugerencias, presionar Enter con lo que escribimos
            logger.warning(f"Sin sugerencias para cargo '{cargo}', usando texto directo")
            await page.keyboard.press("Enter")
            await asyncio.sleep(0.5)
            return True

    except Exception as e:
        logger.error(f"Error en autocomplete cargo: {e}")
        await screenshot(page, "error_cargo_autocomplete")
        return False


async def seleccionar_radio_tipo_salario(page: Page, tipo: str) -> bool:
    """
    Selecciona el tipo de salario que son p-radiobutton (Fijo o Variable).
    tipo: 'F' o 'FIJO' → salarioFijo | 'V' o 'VARIABLE' → salarioVariable
    """
    try:
        tipo_upper = tipo.upper().strip()
        if tipo_upper in ("F", "FIJO", "FIJO"):
            radio_id = "salarioFijo"
        else:
            radio_id = "salarioVariable"

        # Hacer click en el div del radiobutton (no en el input hidden)
        radio = page.locator(f"p-radiobutton[inputid='{radio_id}'] .p-radiobutton-box").first
        await radio.scroll_into_view_if_needed()
        await radio.click()
        await asyncio.sleep(0.5)
        logger.debug(f"Tipo salario → '{radio_id}'")
        return True
    except Exception as e:
        logger.error(f"Error seleccionando tipo salario: {e}")
        return False


async def llenar_fecha_pcalendar(page: Page, input_id: str, fecha: str) -> bool:
    """
    Llena un campo de fecha p-calendar de PrimeNG (dd/mm/yyyy).

    El problema con Ctrl+A en inputs con máscara:
    - Ctrl+A NO garantiza que el cursor quede en posición 0
    - Los dígitos caen en slots desalineados → "22/51/1199" en vez de "22/05/1999"

    Estrategia: ir explícitamente al inicio con Home y tipear
    segmento a segmento (dd → saltar '/' → mm → saltar '/' → yyyy).
    Se intenta 3 veces con verificación, y como último recurso usa JS.
    """
    try:
        # Validar y descomponer la fecha
        partes = str(fecha).strip().split("/")
        if len(partes) != 3:
            logger.warning(f"Fecha con formato inesperado: '{fecha}' (esperado dd/mm/yyyy)")
            return False
        dd   = partes[0].zfill(2)
        mm   = partes[1].zfill(2)
        yyyy = partes[2].zfill(4)
        fecha_esperada = f"{dd}/{mm}/{yyyy}"

        campo = page.locator(f"#{input_id}").first
        await campo.wait_for(state="visible", timeout=5000)
        await campo.scroll_into_view_if_needed()

        def _valor_ok(v: str) -> bool:
            return v.strip() == fecha_esperada

        # ── Helper: tipear un segmento dígito a dígito ───────────
        async def _tipear_segmento(digitos: str):
            for char in digitos:
                await page.keyboard.type(char)
                await asyncio.sleep(0.12)

        # ════════════════════════════════════════════════════════
        # INTENTO 1: Home → dd → ArrowRight → mm → ArrowRight → yyyy
        # No usa Ctrl+A — evita el problema de cursor desalineado
        # ════════════════════════════════════════════════════════
        await campo.click()
        await asyncio.sleep(0.3)
        await page.keyboard.press("Home")          # Cursor al slot 0 (día[0])
        await asyncio.sleep(0.15)

        await _tipear_segmento(dd)                 # día: 2 dígitos
        await asyncio.sleep(0.1)
        # La máscara puede auto-avanzar tras 2 dígitos válidos;
        # si no, el ArrowRight salta el '/'
        await page.keyboard.press("ArrowRight")    # Saltar '/'
        await asyncio.sleep(0.1)

        await _tipear_segmento(mm)                 # mes: 2 dígitos
        await asyncio.sleep(0.1)
        await page.keyboard.press("ArrowRight")    # Saltar '/'
        await asyncio.sleep(0.1)

        await _tipear_segmento(yyyy)               # año: 4 dígitos
        await asyncio.sleep(0.3)

        await page.keyboard.press("Escape")        # Cerrar popover calendario
        await asyncio.sleep(0.2)
        await page.keyboard.press("Tab")
        await asyncio.sleep(0.4)

        valor = await campo.input_value()
        if _valor_ok(valor):
            logger.debug(f"p-calendar #{input_id} [I1] → '{valor}' ✓")
            return True

        logger.warning(f"p-calendar #{input_id} I1='{valor}' ≠ '{fecha_esperada}', reintentando I2...")

        # ════════════════════════════════════════════════════════
        # INTENTO 2: igual pero con triple-click para limpiar primero
        # ════════════════════════════════════════════════════════
        await campo.click(click_count=3)           # Triple-click selecciona todo en el input
        await asyncio.sleep(0.2)
        await page.keyboard.press("Delete")        # Borrar selección
        await asyncio.sleep(0.15)
        await page.keyboard.press("Home")
        await asyncio.sleep(0.15)

        await _tipear_segmento(dd)
        await page.keyboard.press("ArrowRight")
        await asyncio.sleep(0.1)
        await _tipear_segmento(mm)
        await page.keyboard.press("ArrowRight")
        await asyncio.sleep(0.1)
        await _tipear_segmento(yyyy)
        await asyncio.sleep(0.3)

        await page.keyboard.press("Escape")
        await asyncio.sleep(0.2)
        await page.keyboard.press("Tab")
        await asyncio.sleep(0.4)

        valor = await campo.input_value()
        if _valor_ok(valor):
            logger.debug(f"p-calendar #{input_id} [I2] → '{valor}' ✓")
            return True

        logger.warning(f"p-calendar #{input_id} I2='{valor}' ≠ '{fecha_esperada}', intentando JS...")

        # ════════════════════════════════════════════════════════
        # INTENTO 3 (último recurso): setear valor por JavaScript
        # Usa el setter nativo del prototipo para que Angular lo detecte
        # ════════════════════════════════════════════════════════
        await page.evaluate("""
            (args) => {
                const el = document.querySelector(args.sel);
                if (!el) return;
                const setter = Object.getOwnPropertyDescriptor(
                    window.HTMLInputElement.prototype, 'value'
                ).set;
                setter.call(el, args.val);
                el.dispatchEvent(new Event('input',  { bubbles: true }));
                el.dispatchEvent(new Event('change', { bubbles: true }));
                el.dispatchEvent(new Event('blur',   { bubbles: true }));
            }
        """, {"sel": f"#{input_id}", "val": fecha_esperada})
        await asyncio.sleep(0.5)
        await page.keyboard.press("Tab")
        await asyncio.sleep(0.4)

        valor = await campo.input_value()
        if _valor_ok(valor):
            logger.debug(f"p-calendar #{input_id} [I3-JS] → '{valor}' ✓")
            return True

        logger.error(
            f"p-calendar #{input_id}: los 3 intentos fallaron. "
            f"Valor final: '{valor}' (esperado: '{fecha_esperada}')"
        )
        await screenshot(page, f"error_fecha_{input_id}")
        return False

    except Exception as e:
        logger.warning(f"Error llenando fecha #{input_id}: {e}")
        await screenshot(page, f"error_fecha_{input_id}")
        return False


async def llenar_fecha_por_selector(page: Page, selector: str, fecha: str) -> bool:
    """
    Versión de llenar_fecha_pcalendar cuando el input no tiene id propio.
    Usa el selector CSS directamente en lugar de #id.
    Misma lógica de 3 intentos con verificación.
    """
    try:
        partes = str(fecha).strip().split("/")
        if len(partes) != 3:
            return False
        dd   = partes[0].zfill(2)
        mm   = partes[1].zfill(2)
        yyyy = partes[2].zfill(4)
        fecha_esperada = f"{dd}/{mm}/{yyyy}"

        campo = page.locator(selector).first
        await campo.wait_for(state="visible", timeout=5000)
        await campo.scroll_into_view_if_needed()

        def _ok(v): return v.strip() == fecha_esperada

        async def _tipear(digitos):
            for c in digitos:
                await page.keyboard.type(c)
                await asyncio.sleep(0.12)

        for intento in range(1, 3):
            await campo.click(click_count=intento)  # 1=click, 2=doble, 3=triple
            await asyncio.sleep(0.3)
            await page.keyboard.press("Home")
            await asyncio.sleep(0.1)
            await _tipear(dd)
            await page.keyboard.press("ArrowRight")
            await _tipear(mm)
            await page.keyboard.press("ArrowRight")
            await _tipear(yyyy)
            await asyncio.sleep(0.3)
            await page.keyboard.press("Escape")
            await asyncio.sleep(0.2)
            await page.keyboard.press("Tab")
            await asyncio.sleep(0.4)
            valor = await campo.input_value()
            if _ok(valor):
                logger.debug(f"fecha_por_selector [I{intento}] → '{valor}' ✓")
                return True
            logger.warning(f"fecha_por_selector I{intento}='{valor}' ≠ '{fecha_esperada}'")

        return False
    except Exception as e:
        logger.warning(f"Error en llenar_fecha_por_selector: {e}")
        return False


async def llenar_datos_laborales(page: Page, datos: dict) -> dict:
    """
    Llena el formulario de datos laborales.
    Retorna: {"exito": bool, "campos_fallidos": list}

    Si un campo no se puede llenar automáticamente, lo agrega a campos_fallidos
    para que el humano lo complete en el dashboard.

    Notas del portal:
    - subtipoCotizante: p-dropdown normal
    - centroTrabajo: p-dropdown → primera opción o valor manual si viene del dashboard
    - cargo: p-autocomplete (NO p-dropdown)
    - salario: input texto
    - tipoSalario: p-radiobutton (F=Fijo, V=Variable)
    - fechaInicioCobertura: p-calendar
    - eps, afp, formaPago, modalidad, jornada: p-dropdown normales
    """
    logger.info("Formulario datos laborales...")
    campos_fallidos = []

    try:
        await esperar_angular(page)
        await screenshot(page, "inicio_datos_laborales")

        # 1. Subtipo cotizante → "0 - No aplica" (raramente falla)
        await seleccionar_dropdown_primeng(
            page, "subtipoCotizante", datos.get("subtipo_cotizante", "0 - No aplica")
        )
        await asyncio.sleep(0.5)

        # 2. Centro de trabajo
        # Si el humano ya especificó un valor en el dashboard, usarlo; si no, primera opción
        centro = datos.get("centroTrabajo", "").strip()
        if centro:
            ok = await seleccionar_dropdown_primeng(page, "centroTrabajo", centro)
        else:
            ok = await seleccionar_primera_opcion_dropdown(page, "centroTrabajo")
        if not ok:
            campos_fallidos.append("centroTrabajo")
        await asyncio.sleep(0.5)

        # 3. Cargo → p-autocomplete
        cargo = datos.get("cargo_arl", "").strip()
        if cargo:
            ok = await llenar_autocomplete_cargo(page, cargo)
            if not ok:
                campos_fallidos.append("cargo_arl")
        else:
            campos_fallidos.append("cargo_arl")
        await asyncio.sleep(0.5)

        # 4. Salario
        salario = str(datos.get("salario", "")).strip()
        if salario and salario != "0":
            ok = await digitar_si_habilitado(
                page, "#salario, input[formcontrolname='salario']", salario
            )
            # digitar_si_habilitado no retorna bool — verificar que el campo tiene valor
        else:
            campos_fallidos.append("salario")
        await asyncio.sleep(0.5)

        # 5. Tipo salario → radiobutton
        tipo_sal = datos.get("tipo_salario", "F")
        ok = await seleccionar_radio_tipo_salario(page, tipo_sal)
        if not ok:
            campos_fallidos.append("tipo_salario")
        await asyncio.sleep(0.5)

        # 6. Fecha inicio cobertura → p-calendar
        fecha_cob = datos.get("fecha_inicio_cobertura", "").strip()
        if fecha_cob:
            ok = await llenar_fecha_pcalendar(page, "fechaInicioCobertura", fecha_cob)
            if not ok:
                campos_fallidos.append("fecha_inicio_cobertura")
        else:
            campos_fallidos.append("fecha_inicio_cobertura")
        await asyncio.sleep(0.5)

        # 7. EPS
        eps = datos.get("eps", "").strip()
        if eps:
            ok = await seleccionar_dropdown_primeng(page, "eps", eps)
            if not ok:
                eps_corto = eps.replace("EPS", "").replace("EPS.", "").strip()
                ok = await seleccionar_dropdown_primeng(page, "eps", eps_corto)
            if not ok:
                campos_fallidos.append("eps")
        else:
            campos_fallidos.append("eps")
        await asyncio.sleep(0.5)

        # 8. AFP
        afp = datos.get("afp", "").strip()
        if afp:
            ok = await seleccionar_dropdown_primeng(page, "afp", afp)
            if not ok:
                campos_fallidos.append("afp")
        else:
            campos_fallidos.append("afp")
        await asyncio.sleep(0.5)

        # 9. Forma de pago → VENCIDO (raramente falla)
        await seleccionar_dropdown_primeng(
            page, "formaPago", datos.get("forma_pago", "VENCIDO")
        )
        await asyncio.sleep(0.5)

        # 10. Modalidad
        modalidad = datos.get("modalidad", "").strip()
        if modalidad:
            ok = await seleccionar_dropdown_primeng(page, "modalidad", modalidad)
            if not ok:
                campos_fallidos.append("modalidad")
        else:
            campos_fallidos.append("modalidad")
        await asyncio.sleep(0.5)

        # 11. Jornada → UNICA (raramente falla)
        await seleccionar_dropdown_primeng(
            page, "jornada", datos.get("jornada", "UNICA")
        )
        await asyncio.sleep(0.5)

        await screenshot(page, "pre_siguiente_datos_laborales")

        if campos_fallidos:
            logger.warning(f"Campos no llenados automáticamente: {campos_fallidos}")
            # No intentar click en Siguiente — el form estaría inválido
            return {"exito": False, "campos_fallidos": campos_fallidos}

        # Intentar Siguiente
        ok = await click_boton_siguiente(page)
        if not ok:
            # Capturar qué errores de validación quedan
            try:
                errores_labels = []
                error_elems = page.locator(".field__error small:visible, .field__error .ng-star-inserted:visible")
                count = await error_elems.count()
                for i in range(min(count, 10)):
                    txt = (await error_elems.nth(i).inner_text()).strip()
                    if txt:
                        errores_labels.append(txt)
                if errores_labels:
                    logger.warning(f"Errores de validación: {errores_labels}")
            except Exception:
                pass
            return {"exito": False, "campos_fallidos": ["formulario_invalido"]}

        return {"exito": True, "campos_fallidos": []}

    except Exception as e:
        await screenshot(page, "error_datos_laborales")
        logger.error(f"Error en datos laborales: {e}")
        return {"exito": False, "campos_fallidos": campos_fallidos or ["error_inesperado"]}


# ═══════════════════════════════════════════════════════════════════
# PASO 6: VALIDACIÓN FINAL Y AFILIACIÓN
# ═══════════════════════════════════════════════════════════════════

async def confirmar_afiliacion(page: Page) -> dict:
    """
    Valida y confirma la afiliación.
    Retorna: {exito: bool, numero_afiliacion: str, mensaje: str}
    """
    logger.info("Confirmando afiliación...")

    try:
        await esperar_angular(page)

        # Buscar y click en "Afiliar"
        btn_afiliar = page.locator(
            "button:has-text('Afiliar'), button:has-text('AFILIAR')"
        ).first
        await btn_afiliar.wait_for(state="visible", timeout=10000)
        await btn_afiliar.scroll_into_view_if_needed()
        await btn_afiliar.click()
        await asyncio.sleep(1)

        # Modal de confirmación → click "Sí"
        btn_si = page.locator(
            "button:has-text('Sí'), button:has-text('SI'), button:has-text('Confirmar')"
        ).first
        if await btn_si.is_visible(timeout=5000):
            await btn_si.click()
            await asyncio.sleep(2)
            await esperar_angular(page)

        # Capturar número de afiliación del mensaje de éxito
        numero = None
        try:
            mensaje_exito = page.locator(
                ".alert-success, .success-message, [class*='success']"
            ).first
            if await mensaje_exito.is_visible(timeout=5000):
                texto = await mensaje_exito.inner_text()
                # Buscar número de afiliación en el texto
                match = re.search(r'(\d{6,})', texto)
                if match:
                    numero = match.group(1)
                logger.info(f"Afiliación exitosa: {texto}")
                await screenshot(page, "afiliacion_exitosa")
                return {
                    "exito": True,
                    "numero_afiliacion": numero,
                    "mensaje": texto.strip()
                }
        except Exception:
            pass

        # Verificar si hubo error
        try:
            msg_error = page.locator(".alert-danger, .error-message, [class*='error']").first
            if await msg_error.is_visible(timeout=3000):
                texto_error = await msg_error.inner_text()
                logger.error(f"Error en afiliación: {texto_error}")
                await screenshot(page, "error_afiliacion")
                return {"exito": False, "numero_afiliacion": None, "mensaje": texto_error}
        except Exception:
            pass

        # Si llegamos aquí, revisar URL o estado de la página
        await screenshot(page, "estado_final_afiliacion")
        return {"exito": True, "numero_afiliacion": None, "mensaje": "Afiliación procesada"}

    except Exception as e:
        await screenshot(page, "error_confirmacion")
        logger.error(f"Error en confirmación: {e}")
        return {"exito": False, "numero_afiliacion": None, "mensaje": str(e)}
