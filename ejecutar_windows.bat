@echo off
cd /d "%~dp0"
if not exist "venv" (
    echo ERROR: Primero debes ejecutar instalar_windows.bat
    pause
    exit /b 1
)
call venv\Scripts\activate.bat
python main.py
pause
