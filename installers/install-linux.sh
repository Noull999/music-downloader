#!/bin/bash

# ============================================================
# Music Downloader - Instalador para Linux
# ============================================================

echo ""
echo "============================================================"
echo " Music Downloader - Linux Installer"
echo "============================================================"
echo ""

# Detectar distribución Linux
if [ -f /etc/os-release ]; then
    . /etc/os-release
    OS=$ID
else
    echo "ERROR: No se pudo detectar la distribución de Linux"
    exit 1
fi

echo "[*] Distribución detectada: $OS"
echo ""

# Instalar dependencias según la distribución
case "$OS" in
    ubuntu|debian)
        echo "[*] Usando apt para instalar dependencias..."
        sudo apt update
        sudo apt install -y python3 python3-pip ffmpeg

        if [ $? -ne 0 ]; then
            echo "ERROR: Falló la instalación de dependencias del sistema"
            exit 1
        fi
        ;;

    fedora|rhel|centos)
        echo "[*] Usando dnf para instalar dependencias..."
        sudo dnf install -y python3 python3-pip ffmpeg

        if [ $? -ne 0 ]; then
            echo "ERROR: Falló la instalación de dependencias del sistema"
            exit 1
        fi
        ;;

    arch|manjaro)
        echo "[*] Usando pacman para instalar dependencias..."
        sudo pacman -S --noconfirm python python-pip ffmpeg

        if [ $? -ne 0 ]; then
            echo "ERROR: Falló la instalación de dependencias del sistema"
            exit 1
        fi
        ;;

    opensuse*)
        echo "[*] Usando zypper para instalar dependencias..."
        sudo zypper install -y python3 python3-pip ffmpeg

        if [ $? -ne 0 ]; then
            echo "ERROR: Falló la instalación de dependencias del sistema"
            exit 1
        fi
        ;;

    *)
        echo "ERROR: Distribución de Linux no soportada: $OS"
        echo ""
        echo "Instala manualmente:"
        echo "  - Python3"
        echo "  - pip3"
        echo "  - FFmpeg"
        echo ""
        exit 1
        ;;
esac

echo "[✓] Dependencias del sistema instaladas"
echo ""

# Verificar Python
if ! command -v python3 &> /dev/null; then
    echo "ERROR: Python3 no se instaló correctamente"
    exit 1
else
    echo "[✓] Python3 detectado"
    python3 --version
fi

# Verificar FFmpeg
if ! command -v ffmpeg &> /dev/null; then
    echo "ERROR: FFmpeg no se instaló correctamente"
    exit 1
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
    echo "ERROR: Falló la instalación de dependencias de Python"
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
