@echo off
chcp 65001 >nul
echo Configurando auto-sync en el Programador de tareas de Windows...

python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python no esta en PATH. Instalalo desde python.org
    pause
    exit /b 1
)

python scripts\setup_task_scheduler.py --register

pause
