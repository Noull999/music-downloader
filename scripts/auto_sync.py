#!/usr/bin/env python3
"""
Auto-sync standalone: valida credenciales y ejecuta una sincronización real
de likes de SoundCloud sin abrir la GUI.

La lógica vive en sync/auto_sync_runner.py para que también viaje dentro del
.exe empaquetado (que la corre con `MusicDownloader.exe --auto-sync`). Este
script es solo la interfaz de línea de comandos para desarrollo.

Uso:
    python scripts/auto_sync.py [--config config.json] [--validate]
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from config.manager import DEFAULT_CONFIG_PATH
from sync import auto_sync_runner


def main():
    parser = argparse.ArgumentParser(description="Auto-sync SoundCloud (CLI)")
    parser.add_argument(
        "--config", default=str(DEFAULT_CONFIG_PATH),
        help="Ruta a config.json (default: la misma que usa la GUI)"
    )
    parser.add_argument("--once", action="store_true", help="(No usado, se admite por compatibilidad)")
    parser.add_argument("--validate", action="store_true", help="Solo valida credenciales y sale")
    args = parser.parse_args()

    raise SystemExit(auto_sync_runner.run(args.config, validate_only=args.validate))


if __name__ == "__main__":
    main()
