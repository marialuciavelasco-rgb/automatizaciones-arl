"""
Dashboard web para intervención humana en afiliaciones ARL.
Acceso local:  http://localhost:5001
Acceso nube:   https://tu-app.onrender.com
"""
import sys
import os
import requests
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flask import (Flask, render_template, request, redirect,
                   url_for, jsonify, flash, session)
from functools import wraps
from loguru import logger
import modules.firebase_client as fb
from config.mappings import MODALIDAD_OPTIONS
from modules.transformer import separar_nombre

app = Flask(__name__)
app.secret_key = os.getenv("DASHBOARD_SECRET_KEY", "arl-automation-secret-2024")

# ─── Credenciales de acceso (configurar en variables de entorno) ───
DASHBOARD_USER     = os.getenv("DASHBOARD_USER", "admin")
DASHBOARD_PASSWORD = os.getenv("DASHBOARD_PASSWORD", "arl2024")

# ─── GitHub Actions para trigger remoto ───────────────────────────
GITHUB_TOKEN  = os.getenv("GITHUB_TOKEN", "")
GITHUB_REPO   = os.getenv("GITHUB_REPO", "")   # formato: "usuario/repo"
GITHUB_WORKFLOW = os.getenv("GITHUB_WORKFLOW", "rpa.yml")


LABELS_CAMPOS = {
    "fecha_nacimiento":      "Fecha de Nacimiento (dd/mm/yyyy)",
    "modalidad":             "Modalidad de Trabajo",
    "ciudad":                "Ciudad",
    "empresa_arl":           "Empresa en ARL",
    "nombres":               "Nombres",
    "apellidos":             "Apellidos",
    "numero_documento":      "Número de Documento",
    "sexo":                  "Género",
    "email":                 "Email",
    "celular":               "Celular",
    "telefono":              "Teléfono",
    "direccion":             "Dirección",
    "cargo_arl":             "Cargo (texto exacto como aparece en ARL)",
    "centroTrabajo":         "Centro de Trabajo",
    "eps":                   "EPS (nombre como aparece en ARL)",
    "afp":                   "AFP / Pensión (nombre como aparece en ARL)",
    "salario":               "Salario (solo números, sin puntos)",
    "tipo_salario":          "Tipo de Salario (F=Fijo, V=Variable)",
    "fecha_inicio_cobertura":"Fecha Inicio Cobertura (dd/mm/yyyy)",
    "formulario_invalido":   "El formulario quedó inválido — revise los datos e intente de nuevo",
    "error_inesperado":      "Error inesperado — revise los logs y reintente",
}

ESTADO_COLORES = {
    "pendiente":              "badge-warning",
    "en_proceso":             "badge-info",
    "requiere_intervencion":  "badge-danger",
    "completado":             "badge-success",
    "error":                  "badge-dark",
}

ESTADO_ICONOS = {
    "pendiente":              "⏳",
    "en_proceso":             "⚙️",
    "requiere_intervencion":  "🔴",
    "completado":             "✅",
    "error":                  "❌",
}


# ─────────────────────────────────────────────────────────────────
# AUTH
# ─────────────────────────────────────────────────────────────────

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("logged_in"):
            return redirect(url_for("login", next=request.url))
        return f(*args, **kwargs)
    return decorated


@app.route("/login", methods=["GET", "POST"])
def login():
    error = None
    if request.method == "POST":
        user = request.form.get("username", "").strip()
        pwd  = request.form.get("password", "").strip()
        if user == DASHBOARD_USER and pwd == DASHBOARD_PASSWORD:
            session["logged_in"] = True
            session["username"]  = user
            next_url = request.args.get("next") or url_for("index")
            return redirect(next_url)
        error = "Usuario o contraseña incorrectos"
    return render_template("login.html", error=error)


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


# ─────────────────────────────────────────────────────────────────
# INICIO
# ─────────────────────────────────────────────────────────────────

@app.route("/")
@login_required
def index():
    try:
        conteos      = fb.contar_por_estado()
        afiliaciones = fb.obtener_todos(limit=100)
        github_configurado = bool(GITHUB_TOKEN and GITHUB_REPO)
        return render_template("index.html",
                               afiliaciones=afiliaciones,
                               conteos=conteos,
                               estado_colores=ESTADO_COLORES,
                               estado_iconos=ESTADO_ICONOS,
                               github_configurado=github_configurado)
    except Exception as e:
        return render_template("error.html", error=str(e))


# ─────────────────────────────────────────────────────────────────
# DETALLE
# ─────────────────────────────────────────────────────────────────

@app.route("/detalle/<doc_id>")
@login_required
def detalle(doc_id):
    afiliacion = fb.obtener_por_id(doc_id)
    if not afiliacion:
        flash("Afiliación no encontrada", "danger")
        return redirect(url_for("index"))
    return render_template("detalle.html",
                           a=afiliacion,
                           labels=LABELS_CAMPOS,
                           estado_colores=ESTADO_COLORES,
                           estado_iconos=ESTADO_ICONOS)


# ─────────────────────────────────────────────────────────────────
# EDITAR (Intervención humana)
# ─────────────────────────────────────────────────────────────────

@app.route("/editar/<doc_id>", methods=["GET", "POST"])
@login_required
def editar(doc_id):
    afiliacion = fb.obtener_por_id(doc_id)
    if not afiliacion:
        flash("Afiliación no encontrada", "danger")
        return redirect(url_for("index"))

    if request.method == "POST":
        CAMPOS_SENTINEL = {"formulario_invalido", "error_inesperado"}
        campos_guardados = {}
        campos_faltantes = afiliacion.get("campos_faltantes", [])

        for campo in campos_faltantes:
            if campo in CAMPOS_SENTINEL:
                campos_guardados[campo] = "__cleared__"
                continue
            valor = request.form.get(campo, "").strip()
            if valor:
                campos_guardados[campo] = valor

        campos_reales = {k: v for k, v in campos_guardados.items()
                         if v != "__cleared__"}
        sentinels_a_limpiar = [k for k, v in campos_guardados.items()
                                if v == "__cleared__"]

        if campos_reales:
            fb.guardar_campos_manuales_bulk(doc_id, campos_reales)

        if sentinels_a_limpiar:
            doc_ref_data = fb.obtener_por_id(doc_id)
            nuevos_faltantes = [c for c in doc_ref_data.get("campos_faltantes", [])
                                 if c not in sentinels_a_limpiar]
            import firebase_admin
            from firebase_admin import firestore as fs
            db = fb._init_firebase()
            db.collection(fb.COLECCION).document(doc_id).update({
                "campos_faltantes": nuevos_faltantes,
                "fecha_actualizacion": fb.ahora(),
            })
            if not nuevos_faltantes and not campos_reales:
                fb.actualizar_estado(doc_id, "pendiente")

        if campos_reales or sentinels_a_limpiar:
            flash(
                f"✅ {len(campos_reales)} campo(s) guardado(s). "
                "El sistema procesará esta afiliación en el próximo ciclo.",
                "success"
            )
        else:
            flash("No se ingresó ningún dato", "warning")

        return redirect(url_for("detalle", doc_id=doc_id))

    campos_faltantes = afiliacion.get("campos_faltantes", [])
    datos_tx         = afiliacion.get("datos_transformados", {})
    campos_manuales  = afiliacion.get("campos_manuales", {})
    opciones_campos  = {
        "modalidad": MODALIDAD_OPTIONS,
        "sexo":      ["MASCULINO", "FEMENINO"],
    }
    valores_actuales = {}
    for campo in campos_faltantes:
        valores_actuales[campo] = (
            campos_manuales.get(campo) or
            datos_tx.get(campo) or ""
        )

    return render_template("editar.html",
                           a=afiliacion,
                           campos_faltantes=campos_faltantes,
                           labels=LABELS_CAMPOS,
                           opciones_campos=opciones_campos,
                           valores_actuales=valores_actuales)


# ─────────────────────────────────────────────────────────────────
# REINICIAR
# ─────────────────────────────────────────────────────────────────

@app.route("/reiniciar/<doc_id>", methods=["POST"])
@login_required
def reiniciar(doc_id):
    afiliacion = fb.obtener_por_id(doc_id)
    if not afiliacion:
        flash("Afiliación no encontrada", "danger")
        return redirect(url_for("index"))
    nombre = afiliacion.get("nombre_empleado", doc_id)
    fb.reiniciar_afiliacion(doc_id)
    fb.agregar_log(doc_id, "Reiniciado manualmente desde el dashboard", "WARNING", "reinicio_manual")
    flash(f"✅ {nombre} reiniciado. Estado → pendiente, intentos → 0.", "success")
    return redirect(url_for("detalle", doc_id=doc_id))


# ─────────────────────────────────────────────────────────────────
# ELIMINAR
# ─────────────────────────────────────────────────────────────────

@app.route("/eliminar/<doc_id>", methods=["POST"])
@login_required
def eliminar(doc_id):
    afiliacion = fb.obtener_por_id(doc_id)
    if not afiliacion:
        flash("Afiliación no encontrada", "danger")
        return redirect(url_for("index"))
    nombre = afiliacion.get("nombre_empleado", doc_id)
    fb.eliminar_afiliacion(doc_id)
    flash(f"🗑️ Registro de {nombre} eliminado permanentemente.", "warning")
    return redirect(url_for("index"))


# ─────────────────────────────────────────────────────────────────
# TRIGGER GITHUB ACTIONS (ejecutar RPA manualmente desde la web)
# ─────────────────────────────────────────────────────────────────

@app.route("/ejecutar", methods=["POST"])
@login_required
def ejecutar_rpa():
    if not GITHUB_TOKEN or not GITHUB_REPO:
        return jsonify({
            "ok": False,
            "mensaje": "GitHub no configurado. Agrega GITHUB_TOKEN y GITHUB_REPO en las variables de entorno."
        }), 400

    url = f"https://api.github.com/repos/{GITHUB_REPO}/actions/workflows/{GITHUB_WORKFLOW}/dispatches"
    resp = requests.post(
        url,
        headers={
            "Authorization": f"Bearer {GITHUB_TOKEN}",
            "Accept": "application/vnd.github+json",
        },
        json={"ref": "main"},
        timeout=10
    )

    if resp.status_code == 204:
        logger.info(f"GitHub Actions disparado por {session.get('username', 'dashboard')}")
        return jsonify({"ok": True, "mensaje": "✅ Automatización iniciada en la nube. Tarda ~1 minuto en arrancar."})
    else:
        logger.error(f"Error disparando GitHub Actions: {resp.status_code} {resp.text}")
        return jsonify({"ok": False, "mensaje": f"Error GitHub: {resp.status_code} — {resp.text}"}), 500


# ─────────────────────────────────────────────────────────────────
# API
# ─────────────────────────────────────────────────────────────────

@app.route("/api/conteos")
@login_required
def api_conteos():
    try:
        return jsonify(fb.contar_por_estado())
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/pendientes")
@login_required
def api_pendientes():
    try:
        docs = fb.obtener_pendientes()
        return jsonify([{"id": d["id"], "nombre": d.get("nombre_empleado")} for d in docs])
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/para_reintento")
@login_required
def api_para_reintento():
    try:
        docs = fb.obtener_para_reintento()
        return jsonify([{"id": d["id"], "nombre": d.get("nombre_empleado")} for d in docs])
    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    logger.info("Dashboard iniciando en http://localhost:5001")
    app.run(debug=False, port=5001, host="0.0.0.0")
