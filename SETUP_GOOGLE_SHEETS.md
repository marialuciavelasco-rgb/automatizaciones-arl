# Conectar Google Sheets al sistema ARL

El sistema NUNCA escribe en el Sheet — solo lo lee.
Todo el estado queda en Firebase.

---

## Paso 1 — Google Cloud Console

1. Ve a https://console.cloud.google.com
2. Crea un proyecto nuevo → nombre: `ARL Automation`
3. En el menú: **APIs y servicios → Biblioteca**
4. Habilita **Google Sheets API** y **Google Drive API**

---

## Paso 2 — Crear Service Account

1. Ve a **APIs y servicios → Credenciales**
2. **+ Crear credenciales → Cuenta de servicio**
3. Nombre: `arl-automation-reader` → Crear
4. Rol: **Visor** → Listo
5. Clic en la cuenta creada → pestaña **Claves**
6. **Agregar clave → Crear clave nueva → JSON**
7. Se descarga un archivo `.json` — guárdalo

---

## Paso 3 — Instalar las credenciales

Copia el `.json` descargado aquí:

```
arl-automation/config/sheets_key.json
```

---

## Paso 4 — Compartir el Google Sheet

1. Abre el `.json` y copia el valor de `client_email`
   - Ejemplo: `arl-reader@mi-proyecto.iam.gserviceaccount.com`
2. Abre el Google Sheet de Notificaciones Nómina Buk
3. Botón **Compartir** → pega el email → rol **Lector** → Enviar

---

## Paso 5 — Obtener el ID del spreadsheet

En la URL del Sheet:
```
https://docs.google.com/spreadsheets/d/ESTE_ES_EL_ID/edit
```

---

## Paso 6 — Configurar el .env

Agrega esta línea al archivo `.env`:

```env
GOOGLE_SHEETS_ID=AQUI_VA_EL_ID_QUE_COPIASTE
```

---

## Verificar

Corre `python main.py` y el menú mostrará:

```
1  Procesar nómina → Afiliar empleados  (Google Sheets ✓)
```

---

## Instalar dependencias (si no están)

```bash
cd arl-automation
source venv/bin/activate
pip install gspread google-auth
```

---

## ¿Cómo maneja el sistema a los ya afiliados?

**Nivel 1 — En el Sheet:** si la columna `ARL` del empleado tiene valor, esa fila se ignora automáticamente. No hace falta borrarla.

**Nivel 2 — En Firebase:** si el empleado ya existe como `completado`, se omite. Si está en `error` o `requiere_intervencion`, se reinicia para reintento con los datos actualizados del Sheet.

Puedes correr la opción 1 todos los días: el sistema solo procesa los nuevos.
