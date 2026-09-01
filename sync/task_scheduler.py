"""
Registro de la tarea programada de Windows para el auto-sync.

Vive en sync/ (no en scripts/) para que viaje dentro del .exe: así el
ejecutable puede registrar su propia tarea, y la tarea lo invoca a él
mismo, sin depender de que la carpeta del proyecto siga existiendo.

Elige solo el comando correcto:
  - Empaquetado: "MusicDownloader.exe" --auto-sync
  - Desarrollo:  "pythonw.exe" "scripts/auto_sync.py" --config ...
"""
import json
import logging
import os
import subprocess
import sys
from pathlib import Path

from config.manager import DEFAULT_CONFIG_PATH

logger = logging.getLogger(__name__)

TASK_NAME = "MusicDownloaderAutoSync"


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def load_interval_from_config(config_path: str = None) -> int:
    """Intervalo en minutos configurado en la app (default: 24 h)."""
    p = Path(config_path or DEFAULT_CONFIG_PATH)
    if not p.exists():
        return 1440
    try:
        with open(p, "r", encoding="utf-8") as f:
            config = json.load(f)
        return int(config.get("soundcloud", {}).get("sync_interval_minutes", 1440))
    except (json.JSONDecodeError, ValueError, OSError):
        return 1440


def _silent_python() -> str:
    """pythonw.exe (sin ventana de consola) si existe junto al python actual."""
    exe = Path(sys.executable)
    pythonw = exe.with_name("pythonw.exe")
    return str(pythonw) if pythonw.exists() else str(exe)


def build_command(config_path: str = None) -> str:
    """
    Comando que ejecutará la tarea. Empaquetado se llama a sí mismo con
    --auto-sync; en desarrollo invoca scripts/auto_sync.py.
    """
    if is_frozen():
        return f'"{sys.executable}" --auto-sync'

    base = Path(__file__).resolve().parents[1]
    script = base / "scripts" / "auto_sync.py"
    cfg = config_path or str(DEFAULT_CONFIG_PATH)
    return f'"{_silent_python()}" "{script}" --config "{cfg}"'


def _allow_battery(task_name: str = TASK_NAME) -> bool:
    """Permite que la tarea corra con batería (schtasks no expone estos flags)."""
    ps = (
        f"$s = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries "
        f"-DontStopIfGoingOnBatteries; "
        f"Set-ScheduledTask -TaskName '{task_name}' -Settings $s"
    )
    result = subprocess.run(
        ["powershell", "-NoProfile", "-Command", ps],
        capture_output=True, text=True,
    )
    return result.returncode == 0


def _schedule_args(interval_minutes: int) -> tuple[str, str]:
    """
    Traduce minutos al par (/sc, /mo) de schtasks. HOURLY solo acepta /mo
    entre 1 y 23 (24 h ya es DAILY); MINUTE se usa para menos de una hora.
    """
    if interval_minutes >= 1440 and interval_minutes % 1440 == 0:
        return "DAILY", str(interval_minutes // 1440)
    if interval_minutes >= 60 and interval_minutes % 60 == 0 and interval_minutes // 60 <= 23:
        return "HOURLY", str(interval_minutes // 60)
    return "MINUTE", str(max(interval_minutes, 1))


def register(interval_minutes: int, config_path: str = None) -> tuple[bool, str]:
    """Crea (o reemplaza) la tarea programada para el usuario actual."""
    if sys.platform != "win32":
        return False, "Solo Windows. En Linux/macOS usá systemd/music-sync.timer."

    command = build_command(config_path)
    sc, mo = _schedule_args(interval_minutes)

    result = subprocess.run(
        ["schtasks", "/create", "/tn", TASK_NAME, "/tr", command,
         "/sc", sc, "/mo", mo, "/f"],
        capture_output=True, text=True,
    )
    ok = result.returncode == 0
    msg = result.stdout.strip() if ok else (result.stderr.strip() or result.stdout.strip())

    if ok:
        logger.info("Tarea '%s' registrada cada %d min: %s", TASK_NAME, interval_minutes, command)
        if _allow_battery():
            msg += "\n✓ Habilitada la ejecución con batería"
        else:
            msg += "\n⚠️  No se pudo habilitar ejecución con batería (igual corre enchufada)"

    return ok, msg


def remove() -> tuple[bool, str]:
    result = subprocess.run(
        ["schtasks", "/delete", "/tn", TASK_NAME, "/f"],
        capture_output=True, text=True,
    )
    ok = result.returncode == 0
    return ok, (result.stdout.strip() if ok else result.stderr.strip())


def status() -> tuple[bool, str]:
    result = subprocess.run(
        ["schtasks", "/query", "/tn", TASK_NAME, "/fo", "LIST"],
        capture_output=True, text=True,
    )
    ok = result.returncode == 0
    return ok, (result.stdout.strip() if ok else "No configurada")
