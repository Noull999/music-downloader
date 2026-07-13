#!/usr/bin/env python3
"""
Registra / consulta / quita una tarea programada de Windows que corre
scripts/auto_sync.py periódicamente, sin necesidad de tener la app abierta.

El intervalo se lee de config.json (soundcloud.sync_interval_minutes),
el mismo valor que se configura desde la pestaña de Sync de la GUI.

Uso:
    python scripts/setup_task_scheduler.py --register
    python scripts/setup_task_scheduler.py --register --interval-minutes 720
    python scripts/setup_task_scheduler.py --status
    python scripts/setup_task_scheduler.py --remove
"""
import argparse
import json
import subprocess
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
TASK_NAME = "MusicDownloaderAutoSync"


def _load_interval_from_config(config_path: str) -> int:
    p = Path(config_path)
    if not p.exists():
        return 1440
    try:
        with open(p, "r", encoding="utf-8") as f:
            config = json.load(f)
        return int(config.get("soundcloud", {}).get("sync_interval_minutes", 1440))
    except (json.JSONDecodeError, ValueError, OSError):
        return 1440


def register(interval_minutes: int) -> tuple[bool, str]:
    """Crea (o reemplaza) la tarea programada para el usuario actual."""
    script = BASE / "scripts" / "auto_sync.py"
    tr = f'"{sys.executable}" "{script}" --config "{BASE / "config.json"}"'

    # schtasks: HOURLY solo acepta /mo entre 1 y 23 (24 horas = un día,
    # eso ya es DAILY). MINUTE se usa para intervalos menores a una hora.
    if interval_minutes >= 1440 and interval_minutes % 1440 == 0:
        sc, mo = "DAILY", str(interval_minutes // 1440)
    elif interval_minutes >= 60 and interval_minutes % 60 == 0 and interval_minutes // 60 <= 23:
        sc, mo = "HOURLY", str(interval_minutes // 60)
    else:
        sc, mo = "MINUTE", str(max(interval_minutes, 1))

    args = [
        "schtasks", "/create", "/tn", TASK_NAME,
        "/tr", tr,
        "/sc", sc, "/mo", mo,
        "/f",
    ]
    result = subprocess.run(args, capture_output=True, text=True)
    ok = result.returncode == 0
    msg = result.stdout.strip() if ok else result.stderr.strip()
    return ok, msg


def remove() -> tuple[bool, str]:
    result = subprocess.run(
        ["schtasks", "/delete", "/tn", TASK_NAME, "/f"],
        capture_output=True, text=True,
    )
    ok = result.returncode == 0
    msg = result.stdout.strip() if ok else result.stderr.strip()
    return ok, msg


def status() -> tuple[bool, str]:
    result = subprocess.run(
        ["schtasks", "/query", "/tn", TASK_NAME, "/fo", "LIST"],
        capture_output=True, text=True,
    )
    ok = result.returncode == 0
    msg = result.stdout.strip() if ok else "No configurada"
    return ok, msg


def main():
    if sys.platform != "win32":
        print("Este script es para Windows. En Linux/macOS usá systemd/music-sync.timer.")
        raise SystemExit(1)

    parser = argparse.ArgumentParser(
        description="Configura auto-sync en el Programador de tareas de Windows"
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--register", action="store_true", help="Crea/actualiza la tarea")
    group.add_argument("--remove", action="store_true", help="Elimina la tarea")
    group.add_argument("--status", action="store_true", help="Muestra el estado actual")
    parser.add_argument("--config", default=str(BASE / "config.json"))
    parser.add_argument(
        "--interval-minutes", type=int, default=None,
        help="Si se omite, se toma de config.json (soundcloud.sync_interval_minutes)"
    )
    args = parser.parse_args()

    if args.register:
        interval = args.interval_minutes or _load_interval_from_config(args.config)
        ok, msg = register(interval)
        if ok:
            print(f"✅ Tarea '{TASK_NAME}' registrada (cada {interval} min)")
        print(msg)
    elif args.remove:
        ok, msg = remove()
        print("✅ Tarea eliminada" if ok else "❌ No se pudo eliminar")
        print(msg)
    else:
        ok, msg = status()
        print(msg)

    raise SystemExit(0 if ok else 1)


if __name__ == "__main__":
    main()
