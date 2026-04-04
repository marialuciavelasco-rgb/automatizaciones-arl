#!/bin/bash
# ═══════════════════════════════════════════════════════════
# INSTALADOR ARL AUTOMATION — macOS
# Doble clic en este archivo para instalar todo
# ═══════════════════════════════════════════════════════════

echo ""
echo "═══════════════════════════════════════════════════"
echo "  🏥 ARL AUTOMATION — Instalador para Mac"
echo "═══════════════════════════════════════════════════"
echo ""

# Verificar Python
if ! command -v python3 &> /dev/null; then
    echo "❌ Python 3 no está instalado."
    echo "   Ve a https://www.python.org/downloads/ y descárgalo."
    echo ""
    read -p "Presiona Enter para cerrar..."
    exit 1
fi

PYTHON_VERSION=$(python3 --version 2>&1)
echo "✅ Python encontrado: $PYTHON_VERSION"

# Ir al directorio del script
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"
echo "📁 Directorio: $SCRIPT_DIR"

# Crear entorno virtual si no existe
if [ ! -d "venv" ]; then
    echo ""
    echo "📦 Creando entorno virtual..."
    python3 -m venv venv
    echo "✅ Entorno virtual creado"
fi

# Activar entorno virtual
source venv/bin/activate
echo "✅ Entorno virtual activado"

# Actualizar pip
echo ""
echo "📥 Actualizando pip..."
pip install --upgrade pip -q

# Instalar dependencias
echo ""
echo "📥 Instalando dependencias (puede tomar 2-3 minutos)..."
pip install -r requirements.txt -q
if [ $? -ne 0 ]; then
    echo "❌ Error instalando dependencias"
    read -p "Presiona Enter para cerrar..."
    exit 1
fi
echo "✅ Dependencias instaladas"

# Instalar Playwright
echo ""
echo "📥 Instalando navegador Chromium para Playwright..."
python3 -m playwright install chromium
if [ $? -ne 0 ]; then
    echo "❌ Error instalando Chromium"
    read -p "Presiona Enter para cerrar..."
    exit 1
fi
echo "✅ Chromium instalado"

# Crear archivo .env si no existe
if [ ! -f ".env" ]; then
    cp .env.example .env
    echo ""
    echo "⚠️  Se creó el archivo .env"
    echo "   IMPORTANTE: Edítalo con tus credenciales ARL antes de usar el sistema"
fi

# Crear carpetas necesarias
mkdir -p data/excel_input data/portal_options logs screenshots

echo ""
echo "═══════════════════════════════════════════════════"
echo "  ✅ INSTALACIÓN COMPLETA"
echo ""
echo "  Próximos pasos:"
echo "  1. Edita el archivo .env con tus credenciales"
echo "  2. Coloca firebase_key.json en la carpeta config/"
echo "  3. Copia el Excel en data/excel_input/"
echo "  4. Ejecuta: ./ejecutar_mac.sh"
echo "═══════════════════════════════════════════════════"
echo ""
read -p "Presiona Enter para cerrar..."
