#!/bin/bash
# ═══════════════════════════════════════════════════════════
# EJECUTAR ARL AUTOMATION — macOS
# ═══════════════════════════════════════════════════════════

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

if [ ! -d "venv" ]; then
    echo "❌ Primero debes ejecutar instalar_mac.sh"
    read -p "Presiona Enter para cerrar..."
    exit 1
fi

source venv/bin/activate
python3 main.py
