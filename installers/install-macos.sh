#!/bin/bash

# ============================================================
# Music Downloader - Instalador para macOS
# ============================================================

echo ""
echo "============================================================"
echo " Music Downloader - macOS Installer"
echo "============================================================"
echo ""

# Verificar si Homebrew está instalado
if ! command -v brew &> /dev/null; then
    echo "[!] Homebrew no detectado. Instalando..."
    /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

    if [ $? -ne 0 ]; then
        echo "ERROR: No se pudo instalar Homebrew"
        echo "Descarga desde: https://brew.sh"
        exit 1
    fi
    echo "[✓] Homebrew instalado"
fi

# Verificar Python
if ! command -v python3 &> /dev/null; then
    echo "[!] Python3 no detectado. Instalando con Homebrew..."
    brew install python3

    if [ $? -ne 0 ]; then
        echo "ERROR: No se pudo instalar Python3"
        exit 1
    fi
    echo "[✓] Python3 instalado"
else
    echo "[✓] Python3 detectado"
    python3 --version
fi

# Verificar FFmpeg
if ! command -v ffmpeg &> /dev/null; then
    echo ""
    echo "[!] FFmpeg no detectado. Instalando con Homebrew..."
    brew install ffmpeg

    if [ $? -ne 0 ]; then
        echo "ERROR: No se pudo instalar FFmpeg"
        exit 1
    fi
    echo "[✓] FFmpeg instalado"
else
    echo "[✓] FFmpeg detectado"
fi

# Instalar dependencias Python
echo ""
echo "[*] Instalando dependencias Python..."
python3 -m pip install --upgrade pip
pip3 install -r requirements.txt

if [ $? -ne 0 ]; then
    echo ""
    echo "ERROR: Falló la instalación de dependencias"
    exit 1
fi

echo ""
echo "============================================================"
echo "[✓] Instalación completada exitosamente!"
echo "============================================================"
echo ""
echo "Para iniciar la aplicación, ejecuta:"
echo "  python3 main.py"
echo ""
