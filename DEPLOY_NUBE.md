# Despliegue en la Nube — ARL Automation

## Arquitectura

```
Google Sheet (BIA)
      ↓  (sync noche via Apps Script)
AutomatizacionesRRHH Sheet
      ↓  (lee datos)
GitHub Actions ──── RPA headless (Playwright + Chrome)
      ↓  ↑               ↑
   Firebase         Render Dashboard
   (estado)         (login web, trigger manual)
```

---

## PASO 1 — Subir el código a GitHub

1. Crea un repositorio **privado** en https://github.com/new
   - Nombre: `arl-automation`
   - Visibilidad: **Private**

2. Desde tu terminal en la carpeta `arl-automation/`:
```bash
git init
git add .
git commit -m "Initial commit"
git branch -M main
git remote add origin https://github.com/TU_USUARIO/arl-automation.git
git push -u origin main
```

> ⚠️ El `.gitignore` ya excluye `.env`, `firebase_key.json` y `sheets_key.json`.
> Nunca subas archivos con contraseñas.

---

## PASO 2 — Configurar Secrets en GitHub Actions

Ve a tu repo → **Settings** → **Secrets and variables** → **Actions** → **New repository secret**

Agrega estos secrets:

| Secret | Valor |
|--------|-------|
| `ARL_USUARIO` | Tu usuario ARL (ej. `1001299126`) |
| `ARL_PASSWORD` | Tu contraseña ARL |
| `FIREBASE_PROJECT_ID` | `bia-arl-automation` |
| `FIREBASE_KEY_JSON` | Contenido completo del archivo `config/firebase_key.json` |
| `GOOGLE_SHEETS_ID` | `1LOeeKsWbj0z2ALPN5M3-7ik-oD3XrVioUPbhk6aTCGI` |
| `SHEETS_KEY_JSON` | Contenido completo del archivo `config/sheets_key.json` |

Para copiar el contenido de un archivo JSON:
```bash
cat config/firebase_key.json | pbcopy   # Mac
```

---

## PASO 3 — Probar GitHub Actions

1. Ve a tu repo → **Actions** → **ARL Automation RPA**
2. Clic en **Run workflow** → **Run workflow**
3. El RPA corre en la nube en ~2-5 minutos
4. Verás los logs en tiempo real

El workflow también se ejecuta **automáticamente de Lunes a Viernes a las 7 AM** hora Colombia.

---

## PASO 4 — Desplegar el Dashboard en Render

1. Ve a https://render.com y crea cuenta con tu Gmail

2. **New** → **Web Service** → conecta tu repo de GitHub

3. Configura:
   - **Name:** `arl-dashboard`
   - **Build Command:** `pip install -r requirements.txt`
   - **Start Command:** `gunicorn dashboard.app:app --bind 0.0.0.0:$PORT`
   - **Instance Type:** Free

4. En **Environment Variables** agrega:

| Variable | Valor |
|----------|-------|
| `DASHBOARD_USER` | El usuario que quieres (ej. `maria`) |
| `DASHBOARD_PASSWORD` | La contraseña que quieres |
| `FIREBASE_KEY_JSON` | Contenido del `firebase_key.json` |
| `FIREBASE_PROJECT_ID` | `bia-arl-automation` |
| `GOOGLE_SHEETS_ID` | `1LOeeKsWbj0z2ALPN5M3-7ik-oD3XrVioUPbhk6aTCGI` |
| `SHEETS_KEY_JSON` | Contenido del `sheets_key.json` |
| `GITHUB_TOKEN` | Token de GitHub (ver abajo) |
| `GITHUB_REPO` | `TU_USUARIO/arl-automation` |
| `GITHUB_WORKFLOW` | `rpa.yml` |

5. Clic en **Deploy** — en 3-4 minutos tienes la URL pública.

---

## PASO 5 — Crear GitHub Token para el trigger manual

1. Ve a https://github.com/settings/tokens
2. **Generate new token (classic)**
3. Nombre: `ARL Dashboard Trigger`
4. Expiration: `No expiration`
5. Permisos: solo marcar ✅ **workflow**
6. Copiar el token y pegarlo en la variable `GITHUB_TOKEN` de Render

---

## Resultado final

- **Dashboard:** `https://arl-dashboard.onrender.com`
  - Login con usuario/contraseña
  - Ver estado de todas las afiliaciones
  - Completar datos faltantes desde cualquier dispositivo
  - Botón **▶ Ejecutar ahora** para disparar el RPA

- **RPA automático:** corre de Lunes a Viernes 7 AM sin que el computador esté encendido

---

## Cambiar contraseña del dashboard

En Render → tu servicio → **Environment** → editar `DASHBOARD_PASSWORD`.
El servicio se reinicia automáticamente en ~30 segundos.
