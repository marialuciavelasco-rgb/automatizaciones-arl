# Despliegue en AWS Lambda — ARL Automation

Guía para migrar la ejecución del RPA de GitHub Actions a AWS Lambda con imagen Docker.
El dashboard en Render se mantiene igual; solo cambia el motor de ejecución.

---

## Arquitectura objetivo

```
Google Sheets
      ↓
EventBridge (cron L-V 7 AM)
      ↓
AWS Lambda (imagen ECR con Playwright)
      ↓
Firebase Firestore (estado)
      ↑
Render Dashboard (trigger manual → API Gateway → Lambda)
```

---

## Prerrequisitos

- Cuenta AWS activa con permisos para: ECR, Lambda, IAM, EventBridge, CloudWatch
- AWS CLI instalado y configurado (`aws configure`)
- Docker instalado y corriendo
- Código del proyecto actualizado en tu máquina

Verificar que la CLI funciona:
```bash
aws sts get-caller-identity
```

---

## PASO 1 — Crear repositorio en Amazon ECR

ECR es el registro privado de imágenes Docker de AWS. Lambda usará la imagen desde aquí.

```bash
# Crear el repositorio
aws ecr create-repository \
  --repository-name arl-automation \
  --region us-east-1

# Guardar la URI que devuelve el comando (la necesitarás en el paso 3)
# Formato: 123456789012.dkr.ecr.us-east-1.amazonaws.com/arl-automation
```

---

## PASO 2 — Crear rol IAM para Lambda

Lambda necesita permisos para escribir logs en CloudWatch.

```bash
# Crear el rol
aws iam create-role \
  --role-name arl-lambda-role \
  --assume-role-policy-document '{
    "Version": "2012-10-17",
    "Statement": [{
      "Effect": "Allow",
      "Principal": {"Service": "lambda.amazonaws.com"},
      "Action": "sts:AssumeRole"
    }]
  }'

# Adjuntar política de logs básica
aws iam attach-role-policy \
  --role-name arl-lambda-role \
  --policy-arn arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole
```

> Guarda el ARN del rol que devuelve el comando. Formato:
> `arn:aws:iam::123456789012:role/arl-lambda-role`

---

## PASO 3 — Construir y subir la imagen Docker a ECR

Desde la carpeta `arl-automation/`:

```bash
# Variables de entorno (reemplaza con tus valores)
AWS_ACCOUNT_ID=123456789012
AWS_REGION=us-east-1
ECR_URI=$AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com/arl-automation

# Autenticarse en ECR
aws ecr get-login-password --region $AWS_REGION \
  | docker login --username AWS --password-stdin $ECR_URI

# Construir la imagen (puede tardar 5-10 min la primera vez por Playwright)
docker build --platform linux/amd64 -t arl-automation .

# Etiquetar y subir
docker tag arl-automation:latest $ECR_URI:latest
docker push $ECR_URI:latest
```

> `--platform linux/amd64` es obligatorio si construyes desde un Mac con chip Apple Silicon (M1/M2/M3).

---

## PASO 4 — Preparar las variables de entorno (Secrets)

Las credenciales no van en la imagen; se inyectan como variables de entorno en Lambda.

Valores que necesitas tener listos:

| Variable | Descripción |
|---|---|
| `ARL_USUARIO` | Usuario del portal ARL Bolívar |
| `ARL_PASSWORD` | Contraseña del portal ARL Bolívar |
| `FIREBASE_PROJECT_ID` | ID del proyecto Firebase (ej. `bia-arl-automation`) |
| `FIREBASE_KEY_JSON` | Contenido completo del JSON de credenciales de Firebase |
| `GOOGLE_SHEETS_ID` | ID del spreadsheet de Google Sheets |
| `SHEETS_KEY_JSON` | Contenido completo del JSON del service account de Sheets |
| `HEADLESS` | `true` (siempre headless en Lambda) |

Para copiar el contenido de los JSON:
```bash
cat config/firebase_key.json | pbcopy   # Mac
cat config/sheets_key.json | pbcopy
```

---

## PASO 5 — Crear la función Lambda

```bash
ECR_URI=123456789012.dkr.ecr.us-east-1.amazonaws.com/arl-automation
ROLE_ARN=arn:aws:iam::123456789012:role/arl-lambda-role

aws lambda create-function \
  --function-name arl-rpa \
  --package-type Image \
  --code ImageUri=$ECR_URI:latest \
  --role $ROLE_ARN \
  --timeout 900 \
  --memory-size 2048 \
  --region us-east-1 \
  --environment "Variables={
    ARL_USUARIO=TU_USUARIO,
    ARL_PASSWORD=TU_PASSWORD,
    FIREBASE_PROJECT_ID=bia-arl-automation,
    FIREBASE_KEY_JSON=PEGA_AQUI_EL_JSON,
    GOOGLE_SHEETS_ID=TU_SHEETS_ID,
    SHEETS_KEY_JSON=PEGA_AQUI_EL_JSON,
    HEADLESS=true
  }"
```

> - `--timeout 900` = 15 minutos (máximo de Lambda). El RPA puede tardar varios minutos por afiliación.
> - `--memory-size 2048` = 2 GB RAM. Playwright + Chromium requieren al menos 1.5 GB.

---

## PASO 6 — Probar la función manualmente

```bash
aws lambda invoke \
  --function-name arl-rpa \
  --region us-east-1 \
  --log-type Tail \
  output.json

# Ver respuesta
cat output.json

# Ver logs (están en base64)
aws lambda invoke \
  --function-name arl-rpa \
  --region us-east-1 \
  --log-type Tail \
  --query 'LogResult' \
  output.json | tr -d '"' | base64 --decode
```

Respuesta esperada en `output.json`:
```json
{"statusCode": 200, "body": "Proceso completado"}
```

---

## PASO 7 — Programar ejecución automática con EventBridge

Equivalente al cron de GitHub Actions (L-V 7 AM hora Colombia = 12:00 UTC).

```bash
# Crear la regla de cron
aws events put-rule \
  --name arl-rpa-diario \
  --schedule-expression "cron(0 12 ? * MON-FRI *)" \
  --state ENABLED \
  --region us-east-1

# Dar permiso a EventBridge para invocar Lambda
aws lambda add-permission \
  --function-name arl-rpa \
  --statement-id EventBridgeTrigger \
  --action lambda:InvokeFunction \
  --principal events.amazonaws.com \
  --source-arn arn:aws:events:us-east-1:123456789012:rule/arl-rpa-diario \
  --region us-east-1

# Conectar la regla con la función Lambda
LAMBDA_ARN=$(aws lambda get-function \
  --function-name arl-rpa \
  --region us-east-1 \
  --query 'Configuration.FunctionArn' \
  --output text)

aws events put-targets \
  --rule arl-rpa-diario \
  --targets "Id=1,Arn=$LAMBDA_ARN" \
  --region us-east-1
```

---

## PASO 8 — Conectar el Dashboard de Render con Lambda

Para que el botón "Ejecutar ahora" del dashboard dispare Lambda en vez de GitHub Actions, actualiza las variables de entorno en Render:

| Variable | Valor anterior (GitHub) | Valor nuevo (Lambda) |
|---|---|---|
| `GITHUB_TOKEN` | Token de GitHub | *(eliminar)* |
| `GITHUB_REPO` | `usuario/arl-automation` | *(eliminar)* |
| `GITHUB_WORKFLOW` | `rpa.yml` | *(eliminar)* |
| `AWS_ACCESS_KEY_ID` | — | Access key de usuario IAM |
| `AWS_SECRET_ACCESS_KEY` | — | Secret key de usuario IAM |
| `AWS_REGION` | — | `us-east-1` |
| `LAMBDA_FUNCTION_NAME` | — | `arl-rpa` |

Crear usuario IAM solo para el dashboard (principio de mínimo privilegio):
```bash
aws iam create-user --user-name arl-dashboard-invoker

aws iam put-user-policy \
  --user-name arl-dashboard-invoker \
  --policy-name InvokeLambdaOnly \
  --policy-document '{
    "Version": "2012-10-17",
    "Statement": [{
      "Effect": "Allow",
      "Action": "lambda:InvokeFunction",
      "Resource": "arn:aws:iam::123456789012:function/arl-rpa"
    }]
  }'

aws iam create-access-key --user-name arl-dashboard-invoker
# Guarda AccessKeyId y SecretAccessKey que devuelve este comando
```

Luego actualizar `dashboard/app.py` para invocar Lambda en vez de hacer el `workflow_dispatch` de GitHub. El fragmento relevante cambia de:
```python
# Antes (GitHub Actions)
requests.post(
    f"https://api.github.com/repos/{GITHUB_REPO}/actions/workflows/{GITHUB_WORKFLOW}/dispatches",
    headers={"Authorization": f"token {GITHUB_TOKEN}"},
    json={"ref": "main"}
)
```
a:
```python
# Después (Lambda)
import boto3
client = boto3.client("lambda", region_name=AWS_REGION)
client.invoke(
    FunctionName=LAMBDA_FUNCTION_NAME,
    InvocationType="Event"   # asíncrono — no espera respuesta
)
```

---

## PASO 9 — Ver logs en CloudWatch

```bash
# Listar los grupos de log
aws logs describe-log-groups \
  --log-group-name-prefix /aws/lambda/arl-rpa \
  --region us-east-1

# Ver los últimos logs
aws logs tail /aws/lambda/arl-rpa --follow --region us-east-1
```

También puedes verlos en la consola de AWS:
**CloudWatch → Log groups → /aws/lambda/arl-rpa**

---

## PASO 10 — Actualizar la imagen cuando haya cambios de código

Cada vez que se modifique el código:

```bash
AWS_REGION=us-east-1
ECR_URI=123456789012.dkr.ecr.$AWS_REGION.amazonaws.com/arl-automation

# Re-autenticarse en ECR
aws ecr get-login-password --region $AWS_REGION \
  | docker login --username AWS --password-stdin $ECR_URI

# Reconstruir y subir
docker build --platform linux/amd64 -t arl-automation .
docker tag arl-automation:latest $ECR_URI:latest
docker push $ECR_URI:latest

# Forzar que Lambda use la nueva imagen
aws lambda update-function-code \
  --function-name arl-rpa \
  --image-uri $ECR_URI:latest \
  --region us-east-1
```

---

## Costos estimados (referencia)

| Servicio | Uso mensual estimado | Costo aprox. |
|---|---|---|
| Lambda (22 ejecuciones/mes) | ~22 min × 2 GB | < $0.10 USD |
| ECR (almacenamiento imagen) | ~2 GB imagen | ~$0.20 USD/mes |
| CloudWatch Logs | < 1 GB logs | ~$0.03 USD/mes |
| **Total Lambda** | | **< $0.40 USD/mes** |

> Comparado con GitHub Actions (free tier: 2000 min/mes), Lambda es prácticamente igual de barato para este volumen.

---

## Solución de problemas comunes

**Error: "No space left on device" en Lambda**
- Playwright necesita espacio en `/tmp` para el browser. Verifica que el código usa `SCREENSHOTS_DIR = Path("/tmp/screenshots")`. Ya está configurado en `config/settings.py`.

**Error: "Task timed out after 900.00 seconds"**
- El RPA tardó más de 15 min. Revisa cuántas afiliaciones están pendientes. Lambda tiene un máximo de 15 min; si hay muchas afiliaciones, considera procesarlas en lotes o mantener GitHub Actions para volúmenes altos.

**Error: "ECS pull image failed" al crear la función**
- Verifica que el ARN de la imagen ECR es correcto y que el rol IAM tiene permisos para leer ECR.

**Error al ejecutar en Mac M1/M2/M3 sin `--platform linux/amd64`**
- La imagen construida en ARM no funciona en Lambda (que corre en x86). Siempre incluye `--platform linux/amd64`.
