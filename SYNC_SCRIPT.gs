/**
 * SINCRONIZACIÓN AUTOMÁTICA — Sheet Principal BIA → Sheet Automatización ARL
 *
 * Instalación:
 *   1. Abre el Google Sheet PRINCIPAL de BIA (Notificaciones Nómina Buk)
 *   2. Extensiones → Apps Script
 *   3. Borra el contenido que haya y pega TODO este código
 *   4. Cambia AUTOMATION_SHEET_ID por el ID de tu Sheet de automatización
 *   5. Guarda (Ctrl+S)
 *   6. Ejecuta configurarTriggerRRHH() UNA SOLA VEZ para programar las 11 PM
 *   7. Listo — sincroniza automáticamente cada noche
 *
 * Para probar manualmente: ejecuta sincronizarAhora()
 */

// ─── CONFIGURACIÓN ────────────────────────────────────────────────────────────

// ID del Google Sheet de automatización (el que compartiste con el service account)
// Lo encuentras en la URL: docs.google.com/spreadsheets/d/ESTE_ID/edit
var AUTOMATION_SHEET_ID = "PEGA_AQUI_EL_ID_DEL_SHEET_DE_AUTOMATIZACION";

// Nombre de la hoja destino dentro del Sheet de automatización
var AUTOMATION_TAB_NAME = "Sync";

// Hojas del sheet principal que NO son de nómina (se ignoran)
var HOJAS_EXCLUIDAS = [
  "NVScriptsProperties",
  "DO NOT DELETE - AutoCrat Job Se"
];

// ─── FUNCIÓN PRINCIPAL ────────────────────────────────────────────────────────

function ejecutarTriggerAutomatizacionRRHH() {
  var inicio = new Date();
  Logger.log("=== SINCRONIZACIÓN INICIADA: " + inicio.toLocaleString("es-CO") + " ===");

  try {
    // 1. Abrir el Sheet principal (el de BIA, donde está instalado este script)
    var sheetPrincipal = SpreadsheetApp.getActiveSpreadsheet();

    // 2. Detectar la hoja de nómina más reciente
    var nombreHoja = encontrarHojaMasReciente(sheetPrincipal);
    if (!nombreHoja) {
      Logger.log("ERROR: No se encontró ninguna hoja de nómina válida.");
      enviarAlertaEmail("No se encontró hoja de nómina", "El script no pudo detectar la pestaña más reciente.");
      return;
    }
    Logger.log("Hoja detectada: " + nombreHoja);

    // 3. Leer todos los datos de esa hoja
    var hojaFuente = sheetPrincipal.getSheetByName(nombreHoja);
    var datos = hojaFuente.getDataRange().getValues();
    Logger.log("Filas leídas: " + datos.length);

    // 4. Abrir el Sheet de automatización y escribir los datos
    var sheetAuto = SpreadsheetApp.openById(AUTOMATION_SHEET_ID);
    var hojaDestino = sheetAuto.getSheetByName(AUTOMATION_TAB_NAME);

    // Crear la hoja destino si no existe
    if (!hojaDestino) {
      hojaDestino = sheetAuto.insertSheet(AUTOMATION_TAB_NAME);
      Logger.log("Hoja '" + AUTOMATION_TAB_NAME + "' creada en el Sheet de automatización.");
    }

    // Limpiar contenido anterior y escribir los nuevos datos
    hojaDestino.clearContents();
    if (datos.length > 0) {
      hojaDestino.getRange(1, 1, datos.length, datos[0].length).setValues(datos);
    }

    // 5. Registrar metadatos de la sincronización en la hoja "SyncLog"
    registrarLog(sheetAuto, nombreHoja, datos.length, "OK", "");

    var fin = new Date();
    var duracion = Math.round((fin - inicio) / 1000);
    Logger.log("=== SINCRONIZACIÓN COMPLETADA en " + duracion + "s ===");

  } catch (error) {
    Logger.log("ERROR CRÍTICO: " + error.toString());
    registrarLogError(error.toString());
    enviarAlertaEmail("Error en sincronización ARL", error.toString());
  }
}


// ─── DETECTAR HOJA MÁS RECIENTE ──────────────────────────────────────────────

function encontrarHojaMasReciente(spreadsheet) {
  var meses = {
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4,
    "mayo": 5, "junio": 6, "julio": 7, "agosto": 8,
    "septiembre": 9, "octubre": 10, "noviembre": 11, "diciembre": 12
  };

  var hojas = spreadsheet.getSheets();
  var hojasConFecha = [];

  for (var i = 0; i < hojas.length; i++) {
    var nombre = hojas[i].getName();

    // Ignorar hojas del sistema
    if (HOJAS_EXCLUIDAS.indexOf(nombre) !== -1) continue;

    // Buscar patrón "Mes Año" (ej: "Abril 2026")
    var partes = nombre.toLowerCase().split(" ");
    var anio = null;
    var mes = null;

    for (var j = 0; j < partes.length; j++) {
      if (/^\d{4}$/.test(partes[j])) anio = parseInt(partes[j]);
      if (meses[partes[j]]) mes = meses[partes[j]];
    }

    if (anio && mes) {
      hojasConFecha.push({
        nombre: nombre,
        fecha: new Date(anio, mes - 1, 1)
      });
    }
  }

  if (hojasConFecha.length === 0) return null;

  // Ordenar por fecha descendente y tomar la más reciente
  hojasConFecha.sort(function(a, b) { return b.fecha - a.fecha; });
  return hojasConFecha[0].nombre;
}


// ─── REGISTRO DE LOGS ─────────────────────────────────────────────────────────

function registrarLog(sheetAuto, nombreHoja, totalFilas, estado, error) {
  var hojaLog = sheetAuto.getSheetByName("SyncLog");
  if (!hojaLog) {
    hojaLog = sheetAuto.insertSheet("SyncLog");
    hojaLog.appendRow(["Fecha", "Hora Colombia", "Hoja sincronizada", "Filas", "Estado", "Error"]);
  }

  var ahora = new Date();
  hojaLog.appendRow([
    Utilities.formatDate(ahora, "America/Bogota", "dd/MM/yyyy"),
    Utilities.formatDate(ahora, "America/Bogota", "HH:mm:ss"),
    nombreHoja,
    totalFilas,
    estado,
    error
  ]);
}

function registrarLogError(errorMsg) {
  try {
    var sheetAuto = SpreadsheetApp.openById(AUTOMATION_SHEET_ID);
    registrarLog(sheetAuto, "—", 0, "ERROR", errorMsg);
  } catch(e) {
    Logger.log("No se pudo registrar el error en el log: " + e);
  }
}


// ─── ALERTA POR EMAIL ─────────────────────────────────────────────────────────

function enviarAlertaEmail(asunto, cuerpo) {
  try {
    var email = Session.getActiveUser().getEmail();
    MailApp.sendEmail({
      to: email,
      subject: "[ARL Automation] " + asunto,
      body: "Hora Colombia: " + new Date().toLocaleString("es-CO") + "\n\n" + cuerpo
    });
    Logger.log("Alerta enviada a: " + email);
  } catch(e) {
    Logger.log("No se pudo enviar email de alerta: " + e);
  }
}


// ─── CONFIGURAR TRIGGER AUTOMÁTICO ───────────────────────────────────────────

/**
 * Ejecuta esta función UNA SOLA VEZ desde el editor de Apps Script
 * para programar la sincronización automática a las 11 PM Colombia.
 *
 * Apps Script usa la zona horaria del script — asegúrate de que
 * esté en "America/Bogota" (ver Configuración del proyecto → Zona horaria).
 */
function configurarTriggerRRHH() {
  // Eliminar triggers anteriores de este script para evitar duplicados
  var triggers = ScriptApp.getProjectTriggers();
  for (var i = 0; i < triggers.length; i++) {
    if (triggers[i].getHandlerFunction() === "ejecutarTriggerAutomatizacionRRHH") {
      ScriptApp.deleteTrigger(triggers[i]);
    }
  }

  // Crear nuevo trigger: todos los días a las 11 PM Colombia
  ScriptApp.newTrigger("ejecutarTriggerAutomatizacionRRHH")
    .timeBased()
    .everyDays(1)
    .atHour(23)       // 23 = 11 PM en la zona horaria del script
    .nearMinute(0)
    .create();

  Logger.log("✓ Trigger configurado: ejecutarTriggerAutomatizacionRRHH() correrá todos los días a las 11 PM Colombia.");
  Logger.log("Recuerda: la zona horaria del script debe estar en America/Bogota");
}


// ─── ELIMINAR TRIGGER ────────────────────────────────────────────────────────

function eliminarTriggerRRHH() {
  var triggers = ScriptApp.getProjectTriggers();
  var eliminados = 0;
  for (var i = 0; i < triggers.length; i++) {
    if (triggers[i].getHandlerFunction() === "ejecutarTriggerAutomatizacionRRHH") {
      ScriptApp.deleteTrigger(triggers[i]);
      eliminados++;
    }
  }
  Logger.log("Triggers eliminados: " + eliminados);
}
