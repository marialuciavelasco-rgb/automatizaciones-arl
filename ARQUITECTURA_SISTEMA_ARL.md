# 🏗️ ARQUITECTURA COMPLETA — SISTEMA AUTOMATIZACIÓN ARL SEGUROS BOLÍVAR

**Versión:** 1.0
**Fecha:** Abril 2026
**Empresa:** BIA Technologies / BIA Energy
**Portal objetivo:** https://arlonline.segurosbolivar.com/portal/arl/#/home

---

## 1. VISIÓN GENERAL

```
┌─────────────────────────────────────────────────────────────────────┐
│                     SISTEMA ARL AUTOMATION                          │
│                                                                     │
│  [Excel] ──► [Validador] ──► [Transformador] ──► [Firebase]         │
│                                                         │           │
│                                              ┌──────────▼──────┐    │
│                                              │   Motor RPA      │    │
│                                              │  (Playwright)   │    │
│                                              └──────────┬──────┘    │
│                                                         │           │
│                              ┌──────────────────────────┤           │
│                              │                          │           │
│                         ¿Éxito?                   ¿Falta dato?     │
│                              │                          │           │
│                    [Firebase: completado]    [Firebase: revisión]   │
│                                                         │           │
│                                              [Dashboard web local]  │
│                                                         │           │
│                                              [Humano llena dato]    │
│                                                         │           │
│                                              [Reintento automático] │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 2. DECISIONES TÉCNICAS FUNDAMENTALES

### 2.1 Playwright vs Selenium → **PLAYWRIGHT** ✅

| Criterio | Playwright | Selenium |
|---|---|---|
| Angular SPAs | ✅ Excelente (auto-waits) | ⚠️ Requiere waits manuales |
| Inputs restringidos | ✅ Simula teclado real | ❌ Problemático |
| p-dropdown PrimeNG | ✅ Manejo nativo | ⚠️ Complejo |
| Velocidad | ✅ Más rápido | ⚠️ Más lento |
| Mantenimiento | ✅ Más simple | ❌ Más frágil |
| Detección bot | ✅ Stealth mode | ❌ Detectable |
| Licencia | ✅ Gratuito | ✅ Gratuito |

**Decisión: Python + Playwright**

### 2.2 Base de Datos → **Firebase Firestore** ✅

- Gratis (hasta 1GB / 50K lecturas / 20K escrituras por día)
- Tiempo real
- Funciona desde cualquier computador
- No requiere servidor propio
- Accesible desde el dashboard web y el script RPA

### 2.3 Dashboard → **Flask (Web Local)** ✅

- Corre en `http://localhost:5000`
- Sin instalación adicional
- Compatible Mac y Windows
- El operador abre el navegador y ve los casos pendientes

---

## 3. ESTRUCTURA DE CARPETAS DEL PROYECTO

```
arl-automation/
│
├── 📁 config/
│   ├── settings.py          # Configuración general (timeouts, rutas, URLs)
│   ├── mappings.py          # Mapeo de datos: empresa, EPS, AFP, cargos, etc.
│   └── firebase_key.json    # Credenciales Firebase (NUNCA compartir)
│
├── 📁 modules/
│   ├── excel_reader.py      # Lectura y validación del Excel
│   ├── transformer.py       # Transformación datos Excel → formato ARL
│   ├── firebase_client.py   # Todas las operaciones con Firebase
│   ├── rpa_engine.py        # Motor Playwright (automatización web)
│   ├── form_filler.py       # Llenado de formularios (paso a paso)
│   ├── fuzzy_matcher.py     # Matching inteligente: cargos, EPS, AFP
│   └── logger.py            # Sistema de logs centralizado
│
├── 📁 dashboard/
│   ├── app.py               # Servidor Flask (dashboard web)
│   ├── 📁 templates/
│   │   ├── index.html       # Lista de afiliaciones y estados
│   │   ├── detalle.html     # Ver detalles de una afiliación
│   │   └── editar.html      # Formulario de intervención humana
│   └── 📁 static/
│       └── style.css        # Estilos del dashboard
│
├── 📁 logs/                 # Logs automáticos por fecha
├── 📁 data/
│   └── excel_input/         # Aquí se deja el Excel a procesar
│
├── main.py                  # Punto de entrada principal (menú simple)
├── requirements.txt         # Dependencias Python
├── .env                     # Credenciales ARL (NUNCA compartir)
├── .env.example             # Plantilla de credenciales (sí se comparte)
├── instalar_mac.sh          # Script de instalación Mac (1 click)
├── instalar_windows.bat     # Script de instalación Windows (1 click)
├── ejecutar_mac.sh          # Script de ejecución Mac
└── ejecutar_windows.bat     # Script de ejecución Windows
```

---

## 4. MÓDULOS DEL SISTEMA (DESCRIPCIÓN DETALLADA)

### 4.1 `excel_reader.py` — Lector de Excel

**Responsabilidad:** Leer el archivo Excel sin modificarlo nunca.

**Columnas esperadas del Excel:**
| Columna Excel | Descripción |
|---|---|
| Colaborador | Nombre completo (se separa en Nombres/Apellidos) |
| Empresa | BIA TECHNOLOGIES SAS / BIA ENERGY SAS ESP |
| Tipo de Documento | CC |
| Número de Documento | Cédula |
| Género | Masculino / Femenino |
| Email Personal | Correo electrónico |
| Teléfono | Celular/fijo |
| Dirección | Dirección residencia |
| Ciudad de servicio | Ciudad |
| Cargo | Cargo en la empresa |
| Salario | Valor numérico |
| Fecha de ingreso | Fecha inicio cobertura |
| EPS | Nombre EPS |
| AFP / Pensión | Nombre AFP |
| Modalidad | Presencial / Teletrabajo / etc. |

**Validaciones:**
- Columnas obligatorias presentes
- Número de documento no vacío
- Empresa válida (BIA TECHNOLOGIES o BIA ENERGY)
- Salario numérico y > 0
- Fecha de ingreso válida

**Output:** Lista de diccionarios con datos crudos + reporte de filas con errores.

---

### 4.2 `transformer.py` — Motor de Transformación

**Responsabilidad:** Convertir datos Excel al formato exacto que usa el portal ARL.

**Transformaciones críticas:**

```
SEPARACIÓN DE NOMBRES:
"Juan Carlos Pérez Gómez"
  → Nombres: "Juan Carlos"
  → Apellidos: "Pérez Gómez"

Regla: últimas 2 palabras = apellidos, resto = nombres
Excepción: si solo hay 3 palabras → 1 nombre + 2 apellidos
```

```
MAPEO DE EMPRESA:
"BIA TECHNOLOGIES SAS"  → "NT-901637465-BIA TECHNOLOGIES S.A.S"
"BIA ENERGY SAS ESP"    → "NT-901588412-BIA ENERGY S.A.S. E.S.P"
```

```
MAPEO TIPO DOCUMENTO:
"CC" → "CEDULA DE CIUDADANIA"
```

```
NORMALIZACIÓN EPS (ejemplos):
"Sanitas"      → "E.P.S SANITAS"
"Compensar"    → "EPS COMPENSAR"
"Nueva EPS"    → "NUEVA EPS"
"Sura"         → "EPS SURA"
(tabla completa en mappings.py)
```

```
NORMALIZACIÓN AFP (ejemplos):
"Porvenir"     → "PORVENIR"
"Colpensiones" → "COLPENSIONES"
"Protección"   → "PROTECCION"
(tabla completa en mappings.py)
```

```
VALORES FIJOS (siempre iguales):
Tipo cotizante     → "1-DEPENDIENTE"
Subtipo cotizante  → "0 - No aplica"
Centro de trabajo  → "1 - PRINCIPAL"
Tipo salario       → "FIJO"
Forma de pago      → "VENCIDO"
Jornada            → "UNICA"
Zona               → "URBANA"
Localidad          → (no se llena)
```

```
CAMPOS SIN DATO EN EXCEL (→ fallback humano):
- Fecha de nacimiento (no existe en Excel)
- Modalidad (si no se puede inferir)
```

**Fuzzy matching para Cargo:**
- Score ≥ 90%: match automático
- Score 70–89%: acepta el mejor candidato con log de advertencia
- Score < 70%: marca para revisión humana
- Soporte inglés → español (ej: "Software Engineer" → "Ingeniero de Software")

---

### 4.3 `firebase_client.py` — Integración Firebase

**Responsabilidad:** Guardar y consultar el estado de cada afiliación.

**Operaciones:**
- `crear_afiliacion(datos)` → Crea registro con estado "pendiente"
- `actualizar_estado(id, estado)` → Cambia el estado
- `agregar_log(id, mensaje, nivel)` → Agrega entrada al historial
- `marcar_campo_faltante(id, campo)` → Registra qué falta
- `guardar_campo_manual(id, campo, valor)` → Guarda dato ingresado por humano
- `obtener_pendientes()` → Lista registros para el dashboard
- `obtener_para_reintento()` → Registros con datos manuales listos para reintentar

---

### 4.4 `rpa_engine.py` — Motor de Automatización

**Responsabilidad:** Controlar el navegador y ejecutar el proceso completo.

**Manejo especial de Angular:**

```python
# Para campos que no permiten copiar/pegar:
# Se simula digitación letra por letra con delay humano
await page.type("#numeroDocumento", "12345678", delay=150)

# Para p-dropdown (PrimeNG):
# 1. Click en el dropdown para abrirlo
# 2. Esperar que aparezca el panel con opciones
# 3. Buscar la opción correcta
# 4. Hacer click en la opción
await page.click("p-dropdown[formcontrolname='empresa']")
await page.wait_for_selector(".p-dropdown-items", state="visible")
await page.click(f"li:has-text('{valor_empresa}')")

# Para campos de fecha con Angular:
# Se hace click, se escribe con formato, se dispara evento change
await page.click("#fechaNacimiento")
await page.type("#fechaNacimiento", "01/01/1990")
await page.dispatch_event("#fechaNacimiento", "change")

# Esperar que Angular procese:
await page.wait_for_load_state("networkidle", timeout=10000)
```

**Pasos del proceso RPA:**

```
PASO 1: Login
  → Navegar a portal
  → Esperar página carga
  → Ingresar usuario (desde .env)
  → Ingresar contraseña (desde .env)
  → Click "Ingresar"
  → Verificar login exitoso
  → Log: "Login exitoso"

PASO 2: Navegación a Afiliación
  → Esperar dashboard
  → Click "Afiliación de trabajadores"
  → Verificar navegación
  → Log: "En sección afiliación"

PASO 3: Formulario inicial
  → Seleccionar Empresa (p-dropdown)
  → Seleccionar Tipo cotizante = "1-DEPENDIENTE"
  → Seleccionar Tipo documento = "CEDULA DE CIUDADANIA"
  → Digitar Número documento (letra por letra)
  → Click "Siguiente"
  → Verificar paso superado

PASO 4: Datos Personales
  → Escribir Nombres
  → Escribir Apellidos
  → Ingresar Fecha nacimiento (o marcar faltante)
  → Seleccionar Sexo
  → Ingresar Email
  → Ingresar Celular
  → Ingresar Teléfono
  → Ingresar Dirección
  → Seleccionar Ciudad
  → Seleccionar Zona = "URBANA"
  → Click "Siguiente"

PASO 5: Datos Laborales
  → Subtipo cotizante = "0 - No aplica"
  → Centro de trabajo = "1 - PRINCIPAL"
  → Cargo (fuzzy match)
  → Salario
  → Tipo salario = "FIJO"
  → Fecha inicio cobertura
  → EPS (normalizado)
  → AFP (normalizado)
  → Forma de pago = "VENCIDO"
  → Modalidad (o marcar faltante)
  → Jornada = "UNICA"
  → Click "Siguiente"

PASO 6: Validación y Afiliación
  → Click "Afiliar"
  → Click "Sí" en confirmación
  → Capturar número de afiliación
  → Log: "Afiliación exitosa: #XXXXX"
  → Firebase: estado = "completado"
```

---

### 4.5 `dashboard/app.py` — Panel de Control Web

**Acceso:** Abrir navegador → `http://localhost:5000`

**Páginas:**

```
/ (inicio)
  - Resumen: cuántos pendientes, en proceso, completados, errores
  - Lista de todas las afiliaciones con estado visual
  - Botón "Procesar nuevos" (lanza el RPA)
  - Botón "Reintentar revisiones" (procesa casos con datos manuales)

/detalle/{id}
  - Ver todos los datos del empleado
  - Ver historial de logs
  - Ver campos faltantes
  - Botón para ir a editar

/editar/{id}
  - Formulario con SOLO los campos faltantes
  - Ejemplo: "Fecha de nacimiento: [__/__/____]"
  - Botón "Guardar y reintentar"
  → Guarda en Firebase → lanza RPA para ese registro
```

---

## 5. ESTRUCTURA FIREBASE (FIRESTORE)

### Colección: `afiliaciones`

Cada documento representa un empleado en proceso de afiliación:

```json
{
  "id": "auto-generado-firestore",
  "estado": "pendiente",

  "empresa": "BIA TECHNOLOGIES SAS",
  "documento_empleado": "1234567890",
  "nombre_empleado": "Juan Carlos Pérez Gómez",

  "datos_originales": {
    "Colaborador": "Juan Carlos Pérez Gómez",
    "Empresa": "BIA TECHNOLOGIES SAS",
    "Tipo de Documento": "CC",
    "Número de Documento": "1234567890",
    "Género": "Masculino",
    "Email Personal": "juan@bia.app",
    "Teléfono": "3001234567",
    "Dirección": "Calle 100 # 15-20",
    "Ciudad de servicio": "Bogotá",
    "Cargo": "Software Engineer",
    "Salario": 5000000,
    "Fecha de ingreso": "2024-02-01",
    "EPS": "Sanitas",
    "AFP": "Porvenir",
    "Modalidad": ""
  },

  "datos_transformados": {
    "empresa_arl": "NT-901637465-BIA TECHNOLOGIES S.A.S",
    "tipo_cotizante": "1-DEPENDIENTE",
    "tipo_documento": "CEDULA DE CIUDADANIA",
    "numero_documento": "1234567890",
    "nombres": "Juan Carlos",
    "apellidos": "Pérez Gómez",
    "fecha_nacimiento": null,
    "sexo": "MASCULINO",
    "email": "juan@bia.app",
    "celular": "3001234567",
    "telefono": "3001234567",
    "direccion": "Calle 100 # 15-20",
    "ciudad": "BOGOTA",
    "zona": "URBANA",
    "subtipo_cotizante": "0 - No aplica",
    "centro_trabajo": "1 - PRINCIPAL",
    "cargo_original": "Software Engineer",
    "cargo_arl": "INGENIERO DE SOFTWARE",
    "cargo_score": 92,
    "salario": 5000000,
    "tipo_salario": "FIJO",
    "fecha_inicio": "01/02/2024",
    "eps": "E.P.S SANITAS",
    "afp": "PORVENIR",
    "forma_pago": "VENCIDO",
    "modalidad": null,
    "jornada": "UNICA"
  },

  "campos_faltantes": ["fecha_nacimiento", "modalidad"],

  "campos_manuales": {},

  "logs": [
    {
      "timestamp": "2024-04-02T10:30:00",
      "mensaje": "Registro creado desde Excel",
      "nivel": "INFO",
      "paso": "ingesta"
    },
    {
      "timestamp": "2024-04-02T10:31:00",
      "mensaje": "Transformación completada. Campos faltantes: fecha_nacimiento, modalidad",
      "nivel": "WARNING",
      "paso": "transformacion"
    }
  ],

  "intentos": 0,
  "fecha_creacion": "2024-04-02T10:30:00",
  "fecha_actualizacion": "2024-04-02T10:31:00",
  "resultado": null,
  "error_detalle": null
}
```

### Estados posibles:

| Estado | Descripción | Siguiente acción |
|---|---|---|
| `pendiente` | Listo para procesar | RPA lo toma |
| `en_proceso` | RPA trabajando en él | Esperar |
| `requiere_intervencion` | Falta un dato | Humano llena en dashboard |
| `completado` | Afiliado exitosamente | Ninguna |
| `error` | Error inesperado | Revisar logs |

---

## 6. SEGURIDAD Y CREDENCIALES

### Archivo `.env` (nunca compartir, nunca subir a GitHub)

```
ARL_USUARIO=tu_usuario_aqui
ARL_PASSWORD=tu_contraseña_aqui
FIREBASE_PROJECT_ID=nombre-proyecto-firebase
```

### Archivo `.env.example` (sí se comparte como plantilla)

```
ARL_USUARIO=
ARL_PASSWORD=
FIREBASE_PROJECT_ID=
```

### Firebase Key
- Se descarga como `firebase_key.json` desde consola Firebase
- Se guarda en `config/firebase_key.json`
- Nunca se sube a repositorios

---

## 7. REGLAS DE NEGOCIO (IMPLEMENTACIÓN)

```
REGLA 1 — NUNCA AFILIAR CON DATOS INCOMPLETOS
  Si campos_faltantes no está vacío:
    → NO continuar al paso de afiliación
    → Guardar en Firebase como "requiere_intervencion"
    → Notificar en dashboard

REGLA 2 — CARGO SIN MATCH ACEPTABLE
  Si fuzzy score < 70%:
    → Guardar cargo sugerido como "posible_cargo" en Firebase
    → Marcar campo como faltante
    → Mostrar al humano: "No encontramos '${cargo}'. ¿Es alguno de estos?: [lista]"

REGLA 3 — EPS/AFP NO RECONOCIDA
  Si EPS o AFP no está en el mapeo:
    → Intentar búsqueda fuzzy
    → Si score < 80%: marcar como faltante
    → Dashboard muestra las opciones disponibles en el portal

REGLA 4 — ERROR EN FORMULARIO (validación ARL)
  Si el portal muestra mensaje de error:
    → Tomar screenshot
    → Guardar screenshot en Firebase Storage (o local)
    → Log con el error exacto
    → Marcar como "requiere_intervencion"

REGLA 5 — IDEMPOTENCIA
  Antes de procesar, verificar por número de documento:
    → Si ya existe en Firebase como "completado": saltar
    → Si está "en_proceso": verificar si está bloqueado (timeout 30min)
    → Si está "requiere_intervencion": solo procesar si tiene campos_manuales

REGLA 6 — LÍMITE DE REINTENTOS
  intentos >= 3 → estado = "error"
  Requiere revisión manual del log
```

---

## 8. FLUJO COMPLETO PASO A PASO

```
INICIO
  │
  ▼
[1] Operadora pone el Excel en la carpeta data/excel_input/
  │
  ▼
[2] Abre la terminal y ejecuta: python main.py
  (O doble clic en ejecutar_mac.sh)
  │
  ▼
[3] Menú simple aparece:
    1. Procesar nuevo Excel
    2. Ver dashboard
    3. Reintentar casos con intervención
    4. Salir
  │
  ▼ (elige opción 1)
[4] Sistema lee el Excel
    → Valida columnas
    → Reporta filas con errores de formato
    → Pregunta: "¿Continuar con las X filas válidas?"
  │
  ▼
[5] Transformación de datos
    → Separa nombres/apellidos
    → Mapea empresa, documentos, EPS, AFP
    → Fuzzy match de cargos
    → Identifica campos faltantes
  │
  ▼
[6] Guarda en Firebase (estado: pendiente)
    → Un documento por empleado
    → Log: "X registros guardados"
  │
  ▼
[7] Abre el navegador automáticamente
    → Login en ARL
  │
  ▼
[8] Para cada registro pendiente:
    │
    ├── Sin campos faltantes → Proceso automático completo
    │     → Firebase: completado
    │     → Log: "Afiliado exitosamente"
    │
    └── Con campos faltantes → Guarda y marca para revisión
          → Firebase: requiere_intervencion
          → Continúa con el siguiente empleado
  │
  ▼
[9] Al terminar:
    "Procesados: 8 exitosos, 3 requieren revisión"
    "Abre http://localhost:5000 para ver los casos pendientes"
  │
  ▼
[10] Operadora abre http://localhost:5000
     → Ve los 3 casos con campos faltantes
     → Para cada uno: ve qué falta y lo llena
     → Click "Guardar y reintentar"
  │
  ▼
[11] Sistema reintenta automáticamente esos 3 casos
     → Completa la afiliación
  │
  ▼
FIN: Todos los empleados afiliados ✅
```

---

## 9. STACK TÉCNICO COMPLETO

| Componente | Tecnología | Versión | Propósito |
|---|---|---|---|
| Lenguaje | Python | 3.11+ | Todo el sistema |
| Automatización web | Playwright | 1.44+ | Control del navegador |
| Lectura Excel | openpyxl | 3.1+ | Leer .xlsx sin modificar |
| Datos tabulares | pandas | 2.1+ | Transformación de datos |
| Firebase | firebase-admin | 6.3+ | Firestore |
| Dashboard | Flask | 3.0+ | Web local |
| Fuzzy matching | thefuzz | 0.22+ | Match cargos/EPS/AFP |
| Logs | loguru | 0.7+ | Sistema de logs |
| Variables de entorno | python-dotenv | 1.0+ | Credenciales seguras |
| Normalización texto | unidecode | 1.3+ | Quitar tildes/eñes |

---

## 10. PLAN DE IMPLEMENTACIÓN (FASES)

### Fase 1 — Fundamentos (Semana 1)
- [ ] Configurar proyecto Firebase
- [ ] Instalar dependencias Python
- [ ] Implementar `excel_reader.py`
- [ ] Implementar `transformer.py` con mappings base
- [ ] Implementar `firebase_client.py`
- [ ] Prueba: leer Excel → guardar en Firebase

### Fase 2 — RPA Core (Semana 2)
- [ ] Implementar login automático
- [ ] Implementar navegación a afiliación
- [ ] Implementar formulario paso 1 (empresa, doc, cédula)
- [ ] Implementar formulario datos personales
- [ ] Implementar formulario datos laborales
- [ ] Implementar botón Afiliar + confirmación
- [ ] Prueba end-to-end con 1 empleado real

### Fase 3 — Robustez (Semana 3)
- [ ] Manejo de errores del portal
- [ ] Screenshots en errores
- [ ] Sistema de reintentos
- [ ] Fuzzy matching completo (cargos, EPS, AFP)
- [ ] Dashboard Flask completo
- [ ] Prueba con 5+ empleados

### Fase 4 — Pulimiento (Semana 4)
- [ ] Scripts de instalación Mac/Windows
- [ ] Menú simple para operadora no técnica
- [ ] Documentación de uso (manual de usuario)
- [ ] Prueba de estrés con todos los empleados
- [ ] Preparar para Google Sheets (Fase 5 futura)

---

## 11. PREGUNTAS PENDIENTES PARA COMPLETAR LA IMPLEMENTACIÓN

Antes de empezar a escribir el código, necesito que respondas:

1. **Columnas del Excel:** ¿Puedes compartir el Excel real (o una versión sin datos reales)? Necesito ver exactamente los nombres de las columnas.

2. **Credenciales ARL:** ¿Cuál es el usuario con el que se hace login? (No la contraseña, solo el formato: ¿es email, código de empresa, NIT?)

3. **Cargos en ARL:** ¿Tienes acceso al portal ahora? Necesito ver exactamente qué cargos están disponibles en el dropdown del portal para crear la tabla de fuzzy matching.

4. **EPS y AFP disponibles:** Mismo caso — ¿cuáles aparecen en el portal? O ¿puedes hacer screenshot del dropdown de EPS y AFP?

5. **Ciudades disponibles:** ¿En qué ciudades de Colombia están los empleados principalmente? (Bogotá, Medellín, Cali, etc.)

6. **Modalidad:** ¿Qué valores vienen en el Excel para modalidad? ¿Viene como texto libre o hay opciones fijas?

---

*Documento generado como base arquitectónica. Sujeto a ajustes según respuestas pendientes.*
