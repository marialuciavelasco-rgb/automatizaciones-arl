FROM public.ecr.aws/lambda/python:3.11

WORKDIR /var/task

# Instalar dependencias de Python primero (aprovechar caché de capas)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Instalar Chromium y sus dependencias de sistema
ENV PLAYWRIGHT_BROWSERS_PATH=/ms-playwright
RUN playwright install chromium && playwright install-deps chromium

# Copiar código de la aplicación
COPY . .

CMD ["handler.lambda_handler"]
