#!/usr/bin/env python3
"""
Registra / consulta / quita la tarea programada de Windows que corre el
auto-sync periódicamente, sin necesidad de tener la app abierta.

La lógica vive en sync/task_scheduler.py para que también viaje dentro del
.exe (que puede registrar su propia tarea desde Configuración). Este script
es solo la interfaz de línea de comandos.

El intervalo se lee de config.json (soundcloud.sync_interval_minutes), el
mismo valor que se configura desde la app.

Uso:
    python scripts/setup_task_scheduler.py --register
    python scripts/setup_task_scheduler.py --register --interval-minutes 720
    python scripts/setup_task_scheduler.py --status
    python scripts/setup_task_scheduler.py --remove
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from config.manager import DEFAULT_CONFIG_PATH
from sync import task_scheduler


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
    parser.add_argument("--config", default=str(DEFAULT_CONFIG_PATH))
    parser.add_argument(
        "--interval-minutes", type=int, default=None,
        help="Si se omite, se toma de config.json (soundcloud.sync_interval_minutes)"
    )
    args = parser.parse_args()

    if args.register:
        interval = args.interval_minutes or task_scheduler.load_interval_from_config(args.config)
        ok, msg = task_scheduler.register(interval, args.config)
        if ok:
            print(f"✅ Tarea '{task_scheduler.TASK_NAME}' registrada (cada {interval} min)")
        print(msg)
        raise SystemExit(0 if ok else 1)

    if args.remove:
        ok, msg = task_scheduler.remove()
        print("✅ Tarea eliminada" if ok else f"❌ {msg}")
        raise SystemExit(0 if ok else 1)

    ok, msg = task_scheduler.status()
    print(msg)
    raise SystemExit(0 if ok else 1)


if __name__ == "__main__":
    main()
