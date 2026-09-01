@echo off
REM ============================================================
REM Music Downloader - Instalador para Windows
REM ============================================================
color 0A
title Music Downloader - Instalador Windows

echo.
echo ============================================================
echo  Music Downloader - Windows Installer
echo ============================================================
echo.

REM Verificar si Python está instalado
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python no está instalado o no está en PATH
    echo.
    echo Descarga Python desde: https://www.python.org/downloads/
    echo IMPORTANTE: Marca "Add Python to PATH" durante la instalación
    echo.
    pause
    exit /b 1
)

echo [✓] Python detectado
python --version

REM Verificar FFmpeg
ffmpeg -version >nul 2>&1
if errorlevel 1 (
    echo.
    echo [!] FFmpeg no detectado. Instalando...
    echo.

    REM Intenta instalar con winget si está disponible
    winget install ffmpeg >nul 2>&1
    if errorlevel 1 (
        echo ERROR: No se pudo instalar FFmpeg automáticamente
        echo.
        echo Opciones manuales:
        echo 1. Descarga desde: https://ffmpeg.org/download.html
        echo 2. O usa: choco install ffmpeg (si tienes Chocolatey)
        echo 3. O usa: scoop install ffmpeg (si tienes Scoop)
        echo.
        pause
        exit /b 1
    )
    echo [✓] FFmpeg instalado
) else (
    echo [✓] FFmpeg detectado
)

REM Instalar dependencias Python
echo.
echo [*] Instalando dependencias Python...
python -m pip install --upgrade pip
pip install -r requirements.txt

if errorlevel 1 (
    echo.
    echo ERROR: Falló la instalación de dependencias
    pause
    exit /b 1
)

echo.
echo ============================================================
echo [✓] Instalación completada exitosamente!
echo ============================================================
echo.
echo Para iniciar la aplicación, ejecuta:
echo   python main.py
echo.
pause
