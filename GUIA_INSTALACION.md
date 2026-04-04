# 📋 GUÍA DE INSTALACIÓN Y USO — ARL AUTOMATION

**Para:** Equipo BIA Technologies / BIA Energy
**Sistema:** Automatización de afiliaciones ARL Seguros Bolívar

---

## PASO 1: Configurar Firebase (solo una vez)

1. Ve a [https://console.firebase.google.com](https://console.firebase.google.com)
2. Haz click en **"Crear un proyecto"**
3. Nombre del proyecto: `bia-arl-automation`
4. Desactiva Google Analytics → Click **"Crear proyecto"**
5. En el menú izquierdo → **Firestore Database** → **"Crear base de datos"**
   - Elige **"Iniciar en modo de producción"**
   - Ubicación: `us-central1` → **"Listo"**
6. En el menú izquierdo → **Configuración del proyecto** (ícono ⚙️)
7. Tab **"Cuentas de servicio"** → Click **"Generar nueva clave privada"**
8. Se descarga un archivo `.json` → Renómbralo a `firebase_key.json`
9. Cópialo a la carpeta `config/` del proyecto

---

## PASO 2: Configurar credenciales (.env)

1. En la carpeta del proyecto, edita el archivo `.env`
2. Llena los valores:

```
ARL_USUARIO=tu_usuario_del_portal_arl
ARL_PASSWORD=tu_contraseña_del_portal_arl
FIREBASE_PROJECT_ID=bia-arl-automation
HEADLESS=False
```

> ⚠️ **NUNCA compartas el archivo .env con nadie**

---

## PASO 3: Instalar el sistema (solo una vez por computador)

### En Mac:
1. Doble click en `instalar_mac.sh`
2. Si pide permiso, haz click en **"Abrir"**
3. Espera 3-5 minutos hasta que termine

### En Windows:
1. Doble click en `instalar_windows.bat`
2. Espera 3-5 minutos hasta que termine

---

## PASO 4: Primera vez — Descubrir opciones del portal

> **Solo se hace una vez.** Esto conecta el sistema al portal ARL y descarga la lista completa de cargos, EPS, AFP y ciudades.

1. Copia tu Excel en la carpeta `data/excel_input/`
2. Ejecuta el sistema (`ejecutar_mac.sh` o `ejecutar_windows.bat`)
3. Elige la opción **5 — Descubrir opciones del portal ARL**
4. El sistema se conectará al portal y guardará todas las opciones

---

## PASO 5: Uso diario

### Para afiliar empleados nuevos:

1. Copia el Excel `Notificaciones Nómina Buk.xlsx` a la carpeta `data/excel_input/`
2. Ejecuta el sistema con doble click en `ejecutar_mac.sh`
3. Elige la opción **1 — Procesar nuevo Excel**
4. Confirma la hoja y la cantidad de empleados
5. Espera: el sistema llenará todos los formularios automáticamente

### Qué pasa con los datos que faltan:

El sistema **nunca afilia con datos incompletos**. Si falta información:
- Guarda el caso en Firebase con estado **"Requiere revisión"**
- Puedes ver y completar los datos en el **dashboard web**

### Usar el dashboard:

1. Elige la opción **3 — Abrir panel de control**
2. Se abre tu navegador en `http://localhost:5000`
3. Los casos 🔴 **rojos** necesitan tu atención
4. Click en **"✏️ Completar datos"** → llena los campos faltantes
5. Guarda → vuelve al menú y elige la opción **2 — Reintentar**

---

## CAMPOS QUE SIEMPRE NECESITAN INTERVENCIÓN MANUAL

| Campo | Por qué | Cómo completarlo |
|---|---|---|
| **Fecha de nacimiento** | No está en el Excel de nómina | Dashboard → "Completar datos" |
| **Modalidad** | No está definida en el Excel | Dashboard → Seleccionar: Presencial / Teletrabajo / Trabajo en casa |

---

## ESTRUCTURA DE CARPETAS

```
arl-automation/
├── config/
│   ├── firebase_key.json    ← Aquí va el archivo de Firebase
│   └── settings.py
├── data/
│   ├── excel_input/         ← Aquí va el Excel de nómina
│   └── portal_options/      ← Opciones del portal (generadas automáticamente)
├── logs/                    ← Historial de todo lo que hace el sistema
├── screenshots/             ← Capturas de pantalla cuando hay errores
├── .env                     ← Credenciales (NUNCA compartir)
├── ejecutar_mac.sh          ← Doble click para usar en Mac
└── ejecutar_windows.bat     ← Doble click para usar en Windows
```

---

## SOLUCIÓN DE PROBLEMAS

**"Firebase no configurado"**
→ Verifica que `config/firebase_key.json` existe y que `FIREBASE_PROJECT_ID` en `.env` es correcto.

**"Credenciales ARL no configuradas"**
→ Abre el archivo `.env` y verifica que `ARL_USUARIO` y `ARL_PASSWORD` tienen valores.

**"Login fallido"**
→ Verifica que el usuario y contraseña en `.env` son correctos probando entrar manualmente al portal.

**"No hay registros para procesar"**
→ Todos los empleados del Excel ya tienen ARL registrado, o el Excel no tiene la hoja correcta seleccionada.

**El sistema se detiene a mitad del proceso**
→ Los casos ya procesados quedan guardados en Firebase. Puedes retomar desde donde paró con la opción 1 o 2.

---

*Para soporte técnico, contacta a quien mantiene el sistema.*
