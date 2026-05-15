@echo off
REM Instalador automático para Music Downloader en Windows
setlocal enabledelayedexpansion

echo.
echo 🎵 Music Downloader - Instalador Windows
echo =========================================
echo.

REM 1. Verificar Python
echo 1️⃣  Verificando Python...
python --version >nul 2>&1
if errorlevel 1 (
    echo ❌ Python no está instalado o no está en PATH
    echo    Por favor, instala Python 3.9 o superior desde python.org
    echo    Asegúrate de marcar "Add Python to PATH"
    pause
    exit /b 1
)

for /f "tokens=2" %%i in ('python --version 2^>^&1') do set PYTHON_VERSION=%%i
echo ✓ Python %PYTHON_VERSION% encontrado
echo.

REM 2. Verificar/instalar ffmpeg
echo 2️⃣  Verificando ffmpeg...
ffmpeg -version >nul 2>&1
if errorlevel 1 (
    echo ffmpeg no encontrado. Intentando instalar con Chocolatey...

    REM Verificar si Chocolatey está instalado
    choco --version >nul 2>&1
    if errorlevel 1 (
        echo.
        echo ❌ Chocolatey no está instalado
        echo    Opción 1: Instala Chocolatey desde https://chocolatey.org/install
        echo             Luego ejecuta: choco install ffmpeg
        echo.
        echo    Opción 2: Descarga ffmpeg manualmente:
        echo             https://ffmpeg.org/download.html
        echo             Extrae en: C:\ffmpeg
        echo             Agrega C:\ffmpeg\bin al PATH
        echo.
        pause
        exit /b 1
    )

    echo Instalando ffmpeg con Chocolatey...
    choco install ffmpeg -y

    REM Agregar ffmpeg a PATH si está en la ubicación estándar
    set FFMPEG_PATH=C:\ProgramData\chocolatey\lib\ffmpeg\tools\ffmpeg\bin
    if exist "!FFMPEG_PATH!" (
        setx PATH "!FFMPEG_PATH!;%PATH%"
        echo ✓ ffmpeg agregado a PATH
    )
) else (
    for /f "tokens=1" %%i in ('ffmpeg -version 2^>^&1 ^| findstr /R "ffmpeg version"') do set FFMPEG_VERSION=%%i
    echo ✓ ffmpeg ya está instalado
    echo   !FFMPEG_VERSION!
)
echo.

REM Verificación final de ffmpeg
ffmpeg -version >nul 2>&1
if errorlevel 1 (
    echo ❌ ffmpeg sigue sin estar disponible en PATH
    echo    Por favor, instala ffmpeg manualmente
    pause
    exit /b 1
)

REM 3. Crear carpeta de datos
echo 3️⃣  Preparando carpeta de datos...
set DATA_DIR=%USERPROFILE%\.music_downloader
if not exist "!DATA_DIR!" (
    mkdir "!DATA_DIR!"
    echo ✓ Carpeta creada: !DATA_DIR!
) else (
    echo ✓ Carpeta ya existe: !DATA_DIR!
)
echo.

REM 4. Instalar dependencias Python
echo 4️⃣  Instalando dependencias Python...
python -m pip install --upgrade pip
if exist "requirements.txt" (
    pip install -r requirements.txt
    echo ✓ Dependencias instaladas
) else (
    echo ❌ requirements.txt no encontrado
    pause
    exit /b 1
)
echo.

REM 5. Instalar pytest
echo 5️⃣  Instalando herramientas de testing...
pip install pytest
echo.

REM 6. Verificar instalación
echo 6️⃣  Verificando instalación...
python -c "from handlers.base_handler import ffmpeg_location; print('✓ Importación OK')" 2>nul
if errorlevel 1 (
    echo ⚠️  Advertencia: No se pudo verificar importación
) else (
    python -c "from handlers.base_handler import ffmpeg_location; loc=ffmpeg_location(); print('✓ FFmpeg detection:', loc or 'PATH')" 2>nul
)
echo.

REM 7. Resumen
echo ✅ Instalación completada
echo =========================================
echo.
echo Próximos pasos:
echo   1. Ejecuta: python main.py
echo   2. Configura las credenciales en la interfaz gráfica
echo   3. ¡Comienza a descargar!
echo.
echo 📁 Datos: !DATA_DIR!
echo 🎵 Música: %%USERPROFILE%%\Music (configurable en la app)
echo.
pause
