"""
ARL AUTOMATION — Punto de entrada principal
Menú simple para usuarios no técnicos.
"""
import sys
import os
import asyncio
from pathlib import Path
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich import print as rprint

# Agregar el directorio raíz al path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

console = Console()


def mostrar_banner():
    console.print(Panel.fit(
        "[bold blue]🏥 ARL AUTOMATION[/bold blue]\n"
        "[dim]Seguros Bolívar · BIA Technologies & BIA Energy[/dim]",
        border_style="blue"
    ))
    print()


def verificar_configuracion() -> bool:
    """Verifica que el sistema esté correctamente configurado."""
    from config.settings import (
        ARL_USUARIO, ARL_PASSWORD, FIREBASE_KEY_PATH, EXCEL_INPUT_DIR,
        GOOGLE_SHEETS_ID, GOOGLE_SHEETS_CREDENTIALS_PATH,
    )

    errores = []

    if not ARL_USUARIO or not ARL_PASSWORD:
        errores.append("❌ Credenciales ARL no configuradas (ARL_USUARIO / ARL_PASSWORD en .env)")

    if not FIREBASE_KEY_PATH.exists():
        errores.append(f"❌ No se encontró firebase_key.json en: {FIREBASE_KEY_PATH}")

    if not EXCEL_INPUT_DIR.exists():
        EXCEL_INPUT_DIR.mkdir(parents=True, exist_ok=True)

    # Google Sheets es opcional — solo avisar si está a medias configurado
    if GOOGLE_SHEETS_ID and not GOOGLE_SHEETS_CREDENTIALS_PATH.exists():
        errores.append(
            f"⚠️  GOOGLE_SHEETS_ID configurado pero falta el archivo de credenciales: "
            f"{GOOGLE_SHEETS_CREDENTIALS_PATH}"
        )

    if errores:
        console.print("\n[bold red]⚠️  Problemas de configuración:[/bold red]")
        for e in errores:
            console.print(f"  {e}")
        console.print("\n[dim]Revisa el archivo .env y asegúrate de tener firebase_key.json[/dim]\n")
        return False

    return True


def encontrar_excel() -> object:
    """Busca el archivo Excel en la carpeta de entrada."""
    from config.settings import EXCEL_INPUT_DIR
    excels = list(EXCEL_INPUT_DIR.glob("*.xlsx")) + list(EXCEL_INPUT_DIR.glob("*.xls"))
    if not excels:
        return None
    # Retornar el más reciente
    return sorted(excels, key=lambda x: x.stat().st_mtime, reverse=True)[0]


def menu_principal():
    """Muestra el menú principal y retorna la opción elegida."""
    from modules.sheets_reader import sheets_disponible
    fuente = "[green]Google Sheets ✓[/green]" if sheets_disponible() else "[dim]Excel local[/dim]"

    console.print("[bold]¿Qué quieres hacer?[/bold]\n")
    console.print(f"  [bold cyan]1[/bold cyan]  Procesar nómina → Afiliar empleados  ({fuente})")
    console.print("  [bold cyan]2[/bold cyan]  Reintentar casos con datos incompletos")
    console.print("  [bold cyan]3[/bold cyan]  Abrir panel de control (Dashboard)")
    console.print("  [bold cyan]4[/bold cyan]  Ver resumen de afiliaciones")
    console.print("  [bold cyan]5[/bold cyan]  Descubrir opciones del portal ARL")
    console.print("  [bold cyan]6[/bold cyan]  Salir")
    print()

    while True:
        opcion = input("  Ingresa el número de la opción: ").strip()
        if opcion in ("1", "2", "3", "4", "5", "6"):
            return opcion
        console.print("  [red]Opción no válida. Ingresa 1, 2, 3, 4, 5 o 6[/red]")


# ═══════════════════════════════════════════════════════════════════
# OPCIÓN 1: Procesar nómina (Google Sheets o Excel local)
# ═══════════════════════════════════════════════════════════════════

def opcion_procesar_excel():
    """
    Lee la nómina desde Google Sheets (preferido) o desde Excel local.
    Los empleados ya afiliados en la fuente (columna ARL rellena) y los
    ya completados en Firebase se omiten automáticamente.
    """
    from modules.transformer import transformar_lote
    import modules.firebase_client as fb
    from modules.rpa_engine import ejecutar_proceso_completo
    from modules.sheets_reader import sheets_disponible, listar_hojas as sheets_listar, leer_sheets

    console.print("\n[bold]📊 PROCESAR NÓMINA[/bold]\n")

    usa_sheets = sheets_disponible()
    usa_excel  = encontrar_excel() is not None

    # ── Elegir fuente ────────────────────────────────────────────────
    if usa_sheets and usa_excel:
        console.print("[bold]Fuentes disponibles:[/bold]")
        console.print("  [bold cyan]1[/bold cyan]  Google Sheets (siempre actualizado)")
        console.print("  [bold cyan]2[/bold cyan]  Archivo Excel local")
        op = input("\n  ¿Cuál usar? (1/2, Enter = Google Sheets): ").strip()
        usa_sheets = op != "2"
    elif not usa_sheets and not usa_excel:
        console.print("[red]No hay fuente de datos disponible.[/red]")
        console.print("\n  Opción A: Configura GOOGLE_SHEETS_ID en .env")
        console.print("  Opción B: Copia el Excel a data/excel_input/")
        return

    # ── Leer datos ────────────────────────────────────────────────────
    if usa_sheets:
        console.print("📡 [bold]Leyendo desde Google Sheets...[/bold]")
        try:
            hojas = sheets_listar()
            console.print(f"\nHojas disponibles ({len(hojas)}):")
            for i, h in enumerate(hojas[-5:], 1):
                console.print(f"  {i}. {h}")
            hoja_input = input("\n¿Qué hoja procesar? (Enter = más reciente): ").strip()
            hoja = None
            if hoja_input and hoja_input.isdigit():
                idx = int(hoja_input) - 1
                if 0 <= idx < len(hojas[-5:]):
                    hoja = hojas[-5:][idx]
            resultado = leer_sheets(nombre_hoja=hoja)
            fuente_nombre = "Google Sheets"
        except Exception as e:
            console.print(f"[red]Error leyendo Google Sheets: {e}[/red]")
            console.print("[dim]Verifica que el service account tiene acceso al spreadsheet.[/dim]")
            return
    else:
        from modules.excel_reader import leer_excel, listar_hojas
        from config.settings import EXCEL_INPUT_DIR
        excel_path = encontrar_excel()
        console.print(f"📄 [bold]Excel:[/bold] {excel_path.name}")
        hojas = listar_hojas(excel_path)
        console.print(f"\nHojas disponibles ({len(hojas)}):")
        for i, h in enumerate(hojas[-5:], 1):
            console.print(f"  {i}. {h}")
        hoja_input = input("\n¿Qué hoja procesar? (Enter = más reciente): ").strip()
        hoja = None if not hoja_input else hojas[-1]
        if hoja_input and hoja_input.isdigit():
            idx = int(hoja_input) - 1
            if 0 <= idx < len(hojas[-5:]):
                hoja = hojas[-5:][idx]
        console.print("\n[bold]Leyendo Excel...[/bold]")
        resultado = leer_excel(excel_path, hoja=hoja)
        fuente_nombre = "Excel"

    # ── Mostrar resumen ───────────────────────────────────────────────
    console.print(f"\n  ✅ Nuevos para procesar: [bold green]{len(resultado['registros'])}[/bold green]")
    console.print(f"  ⚠️  Con errores de lectura: [bold yellow]{len(resultado['errores'])}[/bold yellow]")
    console.print(f"  📋 Hoja procesada: [bold]{resultado['hoja_usada']}[/bold]")
    console.print(f"  [dim](Los que ya tienen ARL en la fuente se omitieron automáticamente)[/dim]")

    if resultado['errores']:
        console.print("\n[yellow]Errores de lectura:[/yellow]")
        for e in resultado['errores'][:5]:
            console.print(f"  Fila {e['fila']}: {e['campo']} — {e['error']}")

    if not resultado['registros']:
        console.print("\n[green]✅ No hay empleados nuevos para afiliar.[/green]")
        return

    confirmacion = input(f"\n¿Continuar con {len(resultado['registros'])} empleado(s)? (s/n): ").strip().lower()
    if confirmacion != 's':
        console.print("[dim]Proceso cancelado.[/dim]")
        return

    # ── Transformar datos ─────────────────────────────────────────────
    console.print("\n[bold]Transformando datos...[/bold]")
    transformados = transformar_lote(resultado['registros'])
    console.print(f"  ✅ Completos:            {sum(1 for t in transformados if not t['campos_faltantes'])}")
    console.print(f"  ⚠️  Con datos faltantes: {sum(1 for t in transformados if t['campos_faltantes'])}")

    # ── Guardar en Firebase ───────────────────────────────────────────
    console.print("\n[bold]Guardando en Firebase...[/bold]")
    doc_ids = []
    nuevos = 0
    reutilizados = 0
    for t in transformados:
        try:
            num_doc = t["datos_originales"].get("numero_doc", "")
            es_nuevo = fb.buscar_por_documento(num_doc) is None
            doc_id = fb.crear_afiliacion(
                datos_originales=t["datos_originales"],
                datos_transformados=t["datos_transformados"],
                campos_faltantes=t["campos_faltantes"],
                advertencias=t["advertencias"],
            )
            doc_ids.append(doc_id)
            if es_nuevo:
                nuevos += 1
            else:
                reutilizados += 1
        except Exception as e:
            console.print(f"  [red]Error guardando {t['datos_originales'].get('colaborador')}: {e}[/red]")

    console.print(f"  ✅ {nuevos} registro(s) nuevo(s) en Firebase")
    if reutilizados:
        console.print(f"  🔄 {reutilizados} registro(s) existente(s) actualizados para reintento")

    if not doc_ids:
        console.print("[red]No se pudo guardar ningún registro.[/red]")
        return

    # ── Ejecutar RPA ──────────────────────────────────────────────────
    console.print("\n[bold]¿Iniciar automatización ahora?[/bold]")
    inicio = input("  ¿Continuar? (s/n): ").strip().lower()
    if inicio != 's':
        console.print("[dim]Registros guardados. Procésalos luego con la opción 1.[/dim]")
        return

    console.print("\n[bold blue]🤖 Iniciando automatización...[/bold blue]")
    resumen = asyncio.run(ejecutar_proceso_completo(doc_ids=doc_ids))
    _mostrar_resumen_rpa(resumen)


# ═══════════════════════════════════════════════════════════════════
# OPCIÓN 2: Reintentar
# ═══════════════════════════════════════════════════════════════════

def opcion_reintentar():
    import modules.firebase_client as fb
    from modules.rpa_engine import ejecutar_proceso_completo

    console.print("\n[bold]🔁 REINTENTAR CASOS CON DATOS COMPLETADOS[/bold]\n")

    # Buscar tanto en 'requiere_intervencion' como en 'pendiente'
    # (el dashboard mueve los casos completados de requiere_intervencion → pendiente)
    para_reintento = fb.obtener_para_reintento()
    pendientes = fb.obtener_pendientes()

    # Combinar sin duplicados (por id)
    ids_vistos = {c["id"] for c in para_reintento}
    for p in pendientes:
        if p["id"] not in ids_vistos:
            para_reintento.append(p)
            ids_vistos.add(p["id"])

    if not para_reintento:
        pendientes_intervencion = fb.obtener_por_estado("requiere_intervencion")
        if pendientes_intervencion:
            console.print(f"[yellow]⚠️  Hay {len(pendientes_intervencion)} caso(s) que requieren intervención,[/yellow]")
            console.print("[yellow]   pero aún tienen campos faltantes sin completar.[/yellow]")
            console.print("\n   Abre el dashboard (opción 3) para completar los datos.")
        else:
            console.print("[green]✅ No hay casos pendientes de reintento.[/green]")
        return

    console.print(f"Casos listos para procesar: [bold green]{len(para_reintento)}[/bold green]\n")
    for caso in para_reintento[:10]:
        console.print(f"  • {caso.get('nombre_empleado', caso['id'])}")

    inicio = input(f"\n¿Procesar estos {len(para_reintento)} casos? (s/n): ").strip().lower()
    if inicio != 's':
        return

    console.print("\n[bold blue]🤖 Iniciando proceso...[/bold blue]")
    doc_ids = [c["id"] for c in para_reintento]
    resumen = asyncio.run(ejecutar_proceso_completo(doc_ids=doc_ids))
    _mostrar_resumen_rpa(resumen)


# ═══════════════════════════════════════════════════════════════════
# OPCIÓN 3: Dashboard
# ═══════════════════════════════════════════════════════════════════

def opcion_dashboard():
    import subprocess
    import webbrowser
    import time

    console.print("\n[bold]🌐 ABRIENDO DASHBOARD[/bold]\n")
    console.print("  El dashboard se abrirá en tu navegador en: [link]http://localhost:5000[/link]")
    console.print("  Presiona [bold]Ctrl+C[/bold] en la terminal para cerrar el dashboard.\n")

    webbrowser.open("http://localhost:5000")
    time.sleep(1)

    dashboard_path = Path(__file__).parent / "dashboard" / "app.py"
    try:
        subprocess.run([sys.executable, str(dashboard_path)], check=True)
    except KeyboardInterrupt:
        console.print("\n[dim]Dashboard cerrado.[/dim]")


# ═══════════════════════════════════════════════════════════════════
# OPCIÓN 4: Ver resumen
# ═══════════════════════════════════════════════════════════════════

def opcion_resumen():
    import modules.firebase_client as fb

    console.print("\n[bold]📊 RESUMEN DE AFILIACIONES[/bold]\n")

    try:
        conteos = fb.contar_por_estado()

        table = Table(show_header=True, header_style="bold blue")
        table.add_column("Estado", style="bold")
        table.add_column("Cantidad", justify="right")

        iconos = {
            "pendiente": "⏳", "en_proceso": "⚙️",
            "requiere_intervencion": "🔴", "completado": "✅", "error": "❌"
        }
        for estado, count in conteos.items():
            table.add_row(
                f"{iconos.get(estado, '')} {estado.replace('_', ' ').title()}",
                str(count)
            )

        console.print(table)

        total = sum(conteos.values())
        console.print(f"\n  Total registros: [bold]{total}[/bold]")

        if conteos.get("requiere_intervencion", 0) > 0:
            console.print(
                f"\n  [red]⚠️  {conteos['requiere_intervencion']} caso(s) necesitan tu atención.[/red]"
                "\n  Abre el dashboard (opción 3) para completar los datos faltantes."
            )

    except Exception as e:
        console.print(f"[red]Error conectando a Firebase: {e}[/red]")
        console.print("[dim]¿Está configurado el archivo .env y firebase_key.json?[/dim]")


# ═══════════════════════════════════════════════════════════════════
# OPCIÓN 5: Descubrimiento
# ═══════════════════════════════════════════════════════════════════

def opcion_descubrimiento():
    from modules.rpa_engine import ejecutar_proceso_completo

    console.print("\n[bold]🔍 DESCUBRIR OPCIONES DEL PORTAL ARL[/bold]\n")
    console.print("  Esta opción inicia sesión en el portal y extrae automáticamente")
    console.print("  todas las opciones disponibles (cargos, EPS, AFP, ciudades).")
    console.print("  Solo necesitas hacerlo una vez o cuando el portal cambie.\n")

    inicio = input("  ¿Continuar? (s/n): ").strip().lower()
    if inicio != 's':
        return

    console.print("\n[bold blue]🔍 Descubriendo opciones...[/bold blue]")
    asyncio.run(ejecutar_proceso_completo(descubrir=True))
    console.print("\n[green]✅ Opciones guardadas. El sistema usará estos datos para el matching.[/green]")


def _mostrar_resumen_rpa(resumen: dict):
    """Muestra el resumen final del proceso RPA."""
    print()
    console.print(Panel.fit(
        f"[bold green]✅ Exitosos:[/bold green]            {len(resumen['exitosos'])}\n"
        f"[bold yellow]⚠️  Requieren revisión:[/bold yellow]  {len(resumen['requieren_intervencion'])}\n"
        f"[bold red]❌ Fallidos:[/bold red]            {len(resumen['fallidos'])}\n"
        f"[bold]Total procesados:[/bold]       {resumen['total_procesados']}",
        title="RESULTADO DEL PROCESO",
        border_style="blue"
    ))

    if resumen['requieren_intervencion']:
        console.print("\n[yellow]Casos que necesitan datos:[/yellow]")
        for caso in resumen['requieren_intervencion'][:5]:
            console.print(f"  • {caso['nombre']}: {caso['mensaje']}")
        console.print("\n  → Abre el dashboard (opción 3) para completarlos")


# ═══════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════

def main():
    mostrar_banner()

    if not verificar_configuracion():
        input("Presiona Enter para salir...")
        return

    while True:
        menu_principal()
        opcion = input("  Ingresa el número de la opción: ").strip()

        if opcion == "1":
            opcion_procesar_excel()
        elif opcion == "2":
            opcion_reintentar()
        elif opcion == "3":
            opcion_dashboard()
        elif opcion == "4":
            opcion_resumen()
        elif opcion == "5":
            opcion_descubrimiento()
        elif opcion == "6":
            console.print("\n[dim]¡Hasta luego![/dim]\n")
            break
        else:
            console.print("[red]Opción no válida[/red]")

        print()
        input("  Presiona Enter para volver al menú...")
        print()


if __name__ == "__main__":
    main()
