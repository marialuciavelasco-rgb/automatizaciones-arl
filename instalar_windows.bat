@echo off
:: ═══════════════════════════════════════════════════════════
:: INSTALADOR ARL AUTOMATION — Windows
:: Doble clic en este archivo para instalar
:: ═══════════════════════════════════════════════════════════

echo.
echo ═══════════════════════════════════════════════════
echo   ARL AUTOMATION - Instalador para Windows
echo ═══════════════════════════════════════════════════
echo.

:: Verificar Python
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo ERROR: Python no esta instalado.
    echo   Ve a https://www.python.org/downloads/ y descargalo.
    echo   Asegurate de marcar "Add Python to PATH" durante la instalacion.
    pause
    exit /b 1
)

echo Python encontrado OK
cd /d "%~dp0"
echo Directorio: %CD%

:: Crear entorno virtual
if not exist "venv" (
    echo.
    echo Creando entorno virtual...
    python -m venv venv
    echo Entorno virtual creado OK
)

:: Activar entorno virtual
call venv\Scripts\activate.bat
echo Entorno virtual activado OK

:: Instalar dependencias
echo.
echo Instalando dependencias (puede tomar 2-3 minutos)...
pip install --upgrade pip -q
pip install -r requirements.txt -q
if %errorlevel% neq 0 (
    echo ERROR instalando dependencias
    pause
    exit /b 1
)
echo Dependencias instaladas OK

:: Instalar Playwright
echo.
echo Instalando navegador Chromium...
python -m playwright install chromium
if %errorlevel% neq 0 (
    echo ERROR instalando Chromium
    pause
    exit /b 1
)
echo Chromium instalado OK

:: Crear .env si no existe
if not exist ".env" (
    copy .env.example .env
    echo.
    echo IMPORTANTE: Se creo el archivo .env
    echo Editalo con tus credenciales ARL antes de usar el sistema
)

:: Crear carpetas necesarias
if not exist "data\excel_input"    mkdir data\excel_input
if not exist "data\portal_options" mkdir data\portal_options
if not exist "logs"                mkdir logs
if not exist "screenshots"         mkdir screenshots

echo.
echo ═══════════════════════════════════════════════════
echo   INSTALACION COMPLETA
echo.
echo   Proximos pasos:
echo   1. Edita el archivo .env con tus credenciales
echo   2. Coloca firebase_key.json en la carpeta config/
echo   3. Copia el Excel en data/excel_input/
echo   4. Ejecuta: ejecutar_windows.bat
echo ═══════════════════════════════════════════════════
echo.
pause
