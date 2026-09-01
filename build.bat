@echo off
chcp 65001 >nul
echo Building Music Downloader...

REM Asegurar Python en PATH
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python no esta en PATH. Instalalo desde python.org
    pause
    exit /b 1
)

REM Instalar PyInstaller si falta
python -c "import PyInstaller" >nul 2>&1
if errorlevel 1 (
    echo Instalando PyInstaller...
    pip install pyinstaller
)

REM Build
python scripts\build.py --console

pause
