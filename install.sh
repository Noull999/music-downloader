#!/bin/bash
# Instalador automático para Music Downloader en macOS/Linux
set -e

echo "🎵 Music Downloader - Instalador"
echo "================================"

# Detectar sistema operativo
if [[ "$OSTYPE" == "darwin"* ]]; then
    OS="macOS"
elif [[ "$OSTYPE" == "linux-gnu"* ]]; then
    OS="Linux"
else
    echo "❌ Sistema operativo no soportado: $OSTYPE"
    exit 1
fi

echo "📱 Sistema detectado: $OS"

# 1. Verificar Python
echo -e "\n1️⃣  Verificando Python..."
if ! command -v python3 &> /dev/null; then
    echo "❌ Python 3 no está instalado"
    echo "   Por favor, instala Python 3.9 o superior"
    exit 1
fi

PYTHON_VERSION=$(python3 --version | awk '{print $2}')
echo "✓ Python $PYTHON_VERSION encontrado"

# 2. Instalar ffmpeg si falta
echo -e "\n2️⃣  Verificando ffmpeg..."
if ! command -v ffmpeg &> /dev/null; then
    echo "ffmpeg no encontrado. Instalando..."

    if [[ "$OS" == "macOS" ]]; then
        if ! command -v brew &> /dev/null; then
            echo "❌ Homebrew no está instalado"
            echo "   Instala Homebrew desde: https://brew.sh"
            exit 1
        fi
        echo "Instalando ffmpeg con Homebrew..."
        brew install ffmpeg
    elif [[ "$OS" == "Linux" ]]; then
        echo "Instalando ffmpeg con apt-get..."
        sudo apt-get update
        sudo apt-get install -y ffmpeg
    fi
else
    FFMPEG_VERSION=$(ffmpeg -version 2>/dev/null | head -n1)
    echo "✓ ffmpeg ya está instalado"
    echo "  $FFMPEG_VERSION"
fi

# Verificar que ffmpeg está en PATH
if ! command -v ffmpeg &> /dev/null; then
    echo "❌ ffmpeg sigue sin estar disponible en PATH"
    echo "   Intenta instalar manualmente"
    exit 1
fi

# 3. Crear carpeta de datos
echo -e "\n3️⃣  Preparando carpeta de datos..."
DATA_DIR="$HOME/.music_downloader"
if [ ! -d "$DATA_DIR" ]; then
    mkdir -p "$DATA_DIR"
    echo "✓ Carpeta creada: $DATA_DIR"
else
    echo "✓ Carpeta ya existe: $DATA_DIR"
fi

# 4. Instalar dependencias Python
echo -e "\n4️⃣  Instalando dependencias Python..."
python3 -m pip install --upgrade pip

if [ -f "requirements.txt" ]; then
    pip install -r requirements.txt
    echo "✓ Dependencias instaladas"
else
    echo "❌ requirements.txt no encontrado"
    exit 1
fi

# 5. Instalar pytest para tests (opcional)
echo -e "\n5️⃣  Instalando herramientas de testing..."
pip install pytest

# 6. Verificar instalación
echo -e "\n6️⃣  Verificando instalación..."
python3 -c "from handlers.base_handler import ffmpeg_location; print('✓ Importación OK')"

if ffmpeg_location_result=$(python3 -c "from handlers.base_handler import ffmpeg_location; loc=ffmpeg_location(); print(loc or 'PATH')"); then
    echo "✓ FFmpeg detection: $ffmpeg_location_result"
fi

# 7. Resumen
echo -e "\n✅ Instalación completada"
echo "================================"
echo "Próximos pasos:"
echo "1. Ejecuta: python3 main.py"
echo "2. Configura las credenciales en la interfaz gráfica"
echo "3. ¡Comienza a descargar!"
echo ""
echo "📁 Datos: $DATA_DIR"
echo "🎵 Música: ~/Music (configurable en la app)"
