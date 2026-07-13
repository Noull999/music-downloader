#!/usr/bin/env python3
"""
Auto-sync standalone: valida credenciales y ejecuta una sincronización real
de likes de SoundCloud sin necesidad de abrir la GUI.

Pensado para correr periódicamente vía Programador de tareas de Windows
(ver scripts/setup_task_scheduler.py) o cron/systemd en Linux/macOS.

Uso:
    python scripts/auto_sync.py [--config config.json] [--validate]
"""
import argparse
import io
import json
import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

# Corre vía Task Scheduler con pythonw.exe (sin consola): sys.stdout/stderr
# son None ahí, y cualquier print()/log a consola tira AttributeError.
for _name in ("stdout", "stderr"):
    if getattr(sys, _name) is None:
        setattr(sys, _name, io.StringIO())

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sync.sync_manager import SyncManager
from handlers.soundcloud_handler import SoundCloudHandler


LOG_FMT = "%(asctime)s %(levelname)s %(name)s - %(message)s"
LOG_FILE = Path.home() / ".music_downloader" / "auto_sync.log"


def load_config(path: str) -> dict:
    p = Path(path)
    if not p.exists():
        print(f"ERROR: No se encontró {p.resolve()}")
        raise SystemExit(1)
    with open(p, "r", encoding="utf-8") as f:
        return json.load(f)


def setup_logging(level: str = "INFO"):
    # Log a archivo además de stdout: cuando corre vía Task Scheduler no hay
    # consola visible, y sin archivo no queda rastro de si la sync funcionó.
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    file_handler = RotatingFileHandler(
        LOG_FILE, maxBytes=2 * 1024 * 1024, backupCount=3, encoding="utf-8"
    )
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format=LOG_FMT,
        handlers=[logging.StreamHandler(sys.stdout), file_handler],
    )


def main():
    parser = argparse.ArgumentParser(description="Auto-sync SoundCloud (CLI)")
    parser.add_argument("--config", default="config.json", help="Ruta a config.json")
    parser.add_argument("--once", action="store_true", help="(No usado, se admite por compatibilidad)")
    parser.add_argument("--validate", action="store_true", help="Solo valida credenciales y sale (no descarga)")
    args = parser.parse_args()

    setup_logging()
    config = load_config(args.config)

    sc_cfg = config.get("soundcloud", {})
    oauth_token = sc_cfg.get("oauth_token", "")
    client_id = sc_cfg.get("client_id", "")
    download_folder = config.get("dest_folder", str(Path.home() / "Music"))
    threshold = config.get("duplicate_checker", {}).get("similarity_threshold", 85)

    if not oauth_token or not client_id:
        print("ERROR: Configurá soundcloud.oauth_token y soundcloud.client_id en config.json")
        raise SystemExit(1)

    manager = SyncManager(
        oauth_token, client_id,
        download_folder,
        SoundCloudHandler(),
        similarity_threshold=threshold,
        filename_pattern=config.get("filename_pattern", "{artist} - {title}"),
        subfolder_by_artist=config.get("subfolder_by_artist", False),
    )

    try:
        manager.validate_credentials()
    except Exception as e:
        logging.getLogger("auto_sync").error(f"❌ Credenciales inválidas: {e}")
        raise SystemExit(1)

    if args.validate:
        print("✅ Credenciales válidas, no se descarga nada (--validate)")
        raise SystemExit(0)

    log = logging.getLogger("auto_sync")
    try:
        results = manager.sync_once()
    except Exception as e:
        log.error(f"❌ Error durante la sincronización: {e}")
        raise SystemExit(1)

    log.info(
        f"✅ Sync completa: +{results['new']} nuevas | "
        f"{results['skipped']} ya tenías | {results['errors']} errores"
    )
    raise SystemExit(0 if results["errors"] == 0 else 1)


if __name__ == "__main__":
    main()
