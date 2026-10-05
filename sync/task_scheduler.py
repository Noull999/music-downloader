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

from utils.subprocess_utils import NO_WINDOW
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
    """Batería y hora perdida (schtasks no expone estos flags): si el PC estaba apagado a la hora, corre al encender."""
    ps = (
        f"$s = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries "
        f"-DontStopIfGoingOnBatteries -StartWhenAvailable; "
        f"Set-ScheduledTask -TaskName '{task_name}' -Settings $s"
    )
    result = subprocess.run(
        ["powershell", "-NoProfile", "-Command", ps],
        capture_output=True, text=True, creationflags=NO_WINDOW,
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
    if sys.platform == "darwin":
        return _register_mac(interval_minutes, config_path)
    if sys.platform != "win32":
        return False, "Solo Windows y macOS. En Linux usá systemd/music-sync.timer."

    command = build_command(config_path)
    sc, mo = _schedule_args(interval_minutes)

    result = subprocess.run(
        ["schtasks", "/create", "/tn", TASK_NAME, "/tr", command,
         "/sc", sc, "/mo", mo, "/f"],
        capture_output=True, text=True, creationflags=NO_WINDOW,
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


# ── macOS: launchd ────────────────────────────────────────────────────────
LAUNCHD_LABEL = "com.musicdownloader.autosync"


def _plist_path() -> Path:
    return Path.home() / "Library" / "LaunchAgents" / f"{LAUNCHD_LABEL}.plist"


def build_argumentos(config_path: str = None) -> list[str]:
    """Mismo comando que build_command, como lista (launchd no usa un shell)."""
    if is_frozen():
        return [sys.executable, "--auto-sync"]
    base = Path(__file__).resolve().parents[1]
    return [sys.executable, str(base / "scripts" / "auto_sync.py"),
            "--config", config_path or str(DEFAULT_CONFIG_PATH)]


def build_plist(interval_minutes: int, config_path: str = None) -> str:
    """
    LaunchAgent con StartInterval: si el Mac estaba dormido o apagado a la
    hora, corre al despertar (el equivalente de StartWhenAvailable).
    """
    from xml.sax.saxutils import escape
    args = "\n".join(f"        <string>{escape(a)}</string>" for a in build_argumentos(config_path))
    log = Path.home() / ".music_downloader" / "launchd.log"
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>{LAUNCHD_LABEL}</string>
    <key>ProgramArguments</key>
    <array>
{args}
    </array>
    <key>StartInterval</key>
    <integer>{max(int(interval_minutes), 1) * 60}</integer>
    <key>StandardOutPath</key>
    <string>{escape(str(log))}</string>
    <key>StandardErrorPath</key>
    <string>{escape(str(log))}</string>
</dict>
</plist>
"""


def _launchctl(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["launchctl", *args], capture_output=True, text=True)


def _register_mac(interval_minutes: int, config_path: str = None) -> tuple[bool, str]:
    plist = _plist_path()
    plist.parent.mkdir(parents=True, exist_ok=True)
    plist.write_text(build_plist(interval_minutes, config_path), encoding="utf-8")
    dominio = f"gui/{os.getuid()}"
    _launchctl("bootout", dominio, str(plist))  # si ya estaba, se reemplaza
    r = _launchctl("bootstrap", dominio, str(plist))
    ok = r.returncode == 0
    return ok, ("Tarea registrada con launchd" if ok else (r.stderr.strip() or r.stdout.strip()))


def _remove_mac() -> tuple[bool, str]:
    plist = _plist_path()
    _launchctl("bootout", f"gui/{os.getuid()}", str(plist))
    existia = plist.exists()
    plist.unlink(missing_ok=True)
    return True, "Tarea eliminada" if existia else "No había tarea"


def _status_mac() -> tuple[bool, str]:
    r = _launchctl("print", f"gui/{os.getuid()}/{LAUNCHD_LABEL}")
    return r.returncode == 0, (r.stdout.strip()[:400] if r.returncode == 0 else "No configurada")


def remove() -> tuple[bool, str]:
    if sys.platform == "darwin":
        return _remove_mac()
    result = subprocess.run(
        ["schtasks", "/delete", "/tn", TASK_NAME, "/f"],
        capture_output=True, text=True, creationflags=NO_WINDOW,
    )
    ok = result.returncode == 0
    return ok, (result.stdout.strip() if ok else result.stderr.strip())


def status() -> tuple[bool, str]:
    if sys.platform == "darwin":
        return _status_mac()
    result = subprocess.run(
        ["schtasks", "/query", "/tn", TASK_NAME, "/fo", "LIST"],
        capture_output=True, text=True, creationflags=NO_WINDOW,
    )
    ok = result.returncode == 0
    return ok, (result.stdout.strip() if ok else "No configurada")
