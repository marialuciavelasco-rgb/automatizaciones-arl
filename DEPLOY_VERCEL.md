# Deploy del dashboard a Vercel

Guía paso a paso para migrar el dashboard Flask desde Render a Vercel.
El RPA (GitHub Actions) y tu `python main.py` local **no cambian**; Firebase
sigue siendo la base de datos compartida.

---

## 1. Cómo funciona

- Vercel corre `api/index.py` como una **función serverless** cada vez que
  llega una petición HTTP.
- `api/index.py` importa el `app` de `dashboard/app.py` (el mismo Flask que
  ya usábamos en Render).
- `vercel.json` dice: "todas las rutas van a `api/index.py`". Vercel
  auto-detecta que `app` es WSGI y lo levanta.
- `api/requirements.txt` sólo instala las dependencias del dashboard
  (Flask, firebase-admin, etc.). Pandas / Playwright / gspread se
  quedan en el `requirements.txt` raíz para GitHub Actions y local.

**Firebase sigue siendo la fuente de verdad.** El dashboard en Vercel lee
y escribe a la misma colección `afiliaciones` que el RPA y `main.py`.

---

## 2. Env vars que hay que configurar en Vercel

En el dashboard de Vercel (Settings → Environment Variables) agrega:

| Variable                | Valor                                          | Notas                                             |
|-------------------------|------------------------------------------------|---------------------------------------------------|
| `DASHBOARD_USER`        | `admin` (o el que uses)                        | Login del dashboard                                |
| `DASHBOARD_PASSWORD`    | tu contraseña                                  | Login del dashboard                                |
| `DASHBOARD_SECRET_KEY`  | cadena aleatoria larga                         | Firma cookies de sesión. Genera con `openssl rand -hex 32` |
| `FIREBASE_PROJECT_ID`   | id del proyecto Firebase                       | El mismo que ya usas                               |
| `FIREBASE_KEY_JSON`     | contenido completo del `firebase_key.json`     | Pega el JSON entero como string, no una ruta       |
| `GITHUB_TOKEN`          | Personal Access Token de GitHub                | Permiso `workflow` para disparar el RPA remoto     |
| `GITHUB_REPO`           | `marialuciavelasco-rgb/automatizaciones-arl`   | Formato usuario/repo                               |
| `GITHUB_WORKFLOW`       | `rpa.yml`                                      | Archivo del workflow                               |

**Tip:** copia los mismos valores que tienes hoy en Render — son idénticos.

---

## 3. Deploy en 3 clics (recomendado — vía Git)

Requisitos: cuenta Vercel, código en GitHub.

1. Entra a https://vercel.com/new
2. **Import Git Repository** → selecciona `automatizaciones-arl`.
3. Cuando pregunte por la rama, elige **`vercel-migration`** (o `main`
   después del merge).
4. **Framework Preset:** deja "Other" (Vercel detecta el `vercel.json`).
5. **Root Directory:** deja `.` (raíz del repo).
6. Antes de darle Deploy, click **Environment Variables** y agrega
   TODAS las de la tabla anterior.
7. Click **Deploy**.

El primer deploy tarda 2-4 minutos (instala dependencias). Los
siguientes son mucho más rápidos por caché.

Al terminar te dan una URL tipo `https://arl-dashboard.vercel.app`.

---

## 4. Deploy con Vercel CLI (alternativa)

```bash
# Instalar Vercel CLI una sola vez
npm install -g vercel

# Desde la raíz del repo
vercel login
vercel link            # asocia el proyecto local con Vercel
vercel env add DASHBOARD_USER
vercel env add DASHBOARD_PASSWORD
# ... resto de las env vars
vercel --prod          # deploy productivo
```

---

## 5. Verificar que funcionó

Abre la URL de Vercel:

1. Debe redirigir a `/login`.
2. Entra con `DASHBOARD_USER` / `DASHBOARD_PASSWORD`.
3. La página `/` debe mostrar los mismos empleados y estados que veías
   en Render (Firebase es la misma base).
4. Prueba `/detalle/<id>` y `/editar/<id>` con un caso real.
5. En `/api/conteos` deberías ver el JSON con los conteos.
6. Botón "Ejecutar automatización" debe disparar el workflow de
   GitHub Actions (verifica en la pestaña Actions del repo).

Si algo no funciona, ver sección 8 (Troubleshooting).

---

## 6. Probar localmente antes de deploy

**Opción A — Flask directo (como siempre):**
```bash
./.venv/bin/python dashboard/app.py
# abre http://localhost:5001
```

**Opción B — Simular el ambiente Vercel:**
```bash
npm install -g vercel
vercel dev
# abre http://localhost:3000
```

Ambos deben mostrar el mismo comportamiento. Si `vercel dev` falla y
Flask directo funciona, es un problema de config de Vercel; si ambos
fallan, es del código.

---

## 7. Ciclo de trabajo diario

- **Cambio pequeño** → commit y push a la rama que Vercel vigila.
  Vercel hace redeploy automático (~1 min).
- **Cambio en env var** → cambiarla en Vercel dashboard → hacer
  redeploy manual desde Vercel (Deployments → Redeploy).
- **Cambio en el RPA (modules/rpa_engine.py, form_filler, etc.)** →
  no afecta a Vercel. Se despliega solo por GitHub Actions.
- **Volver atrás** → Vercel guarda todos los deploys. Un clic para
  volver a una versión anterior desde el dashboard.

---

## 8. Troubleshooting

### "Application Error" al abrir la URL
- Ve a **Vercel → tu proyecto → Deployments → View Function Logs**.
- Los errores más comunes:
  - Falta `FIREBASE_KEY_JSON` o `FIREBASE_PROJECT_ID` → verifica env vars.
  - JSON de Firebase mal pegado (falta un `}` o hay comillas raras).

### "Firebase no configurado"
- El `FIREBASE_KEY_JSON` debe ser el **contenido** del archivo, no una ruta.
  Ábrelo con un editor de texto y copia todo el contenido (incluye `{ ... }`).

### Cold starts lentos (primera petición 2-3s)
- Es normal. Firebase Admin tarda en inicializar. Peticiones siguientes
  son rápidas mientras la función esté "caliente" (~5 min de idle).
- Si molesta mucho: subir a Vercel Pro para tener más instancias
  precalentadas o usar Vercel Cron para ping periódico.

### Timeout de 10s (Hobby)
- Consultas a Firestore muy grandes (`obtener_todos` con muchos docs)
  pueden pasar los 10s. Si llegas ahí, upgradea a Pro (60s de timeout)
  o pagina los resultados.

### El dashboard funciona pero botón "Ejecutar" no dispara el RPA
- Verifica `GITHUB_TOKEN`: debe ser un PAT con scope `workflow`.
- Verifica `GITHUB_REPO`: formato `usuario/repo`, sin URL.
- Mira los logs de Vercel para ver el mensaje exacto de error de la API GitHub.

---

## 9. ¿Y Render?

Puedes dejar el servicio de Render corriendo hasta confirmar que
Vercel funciona bien. Cuando estés seguro:

1. Desactivar el servicio en Render (Suspend).
2. Después de un tiempo sin problemas, eliminarlo definitivamente.
3. Guardar las credenciales de Firebase por si acaso — son las mismas
   que Vercel usa.
