#!/usr/bin/env python3
"""
Auto-sync standalone: ejecuta una sincronización de likes de SoundCloud
sin necesidad de abrir la GUI.

Uso:
    python scripts/auto_sync.py [--once]

Opciones:
    --once    Ejecuta una sola sincronización y sale (útil para cron/systemd)
"""
import argparse
import json
import logging
import os
import sys
from pathlib import Path

# Asegurar imports del paquete
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sync.sync_manager import SyncManager
from sync.soundcloud_api import SoundCloudAPIClient
from handlers.soundcloud_handler import SoundCloudHandler


LOG_FMT = "%(asctime)s %(levelname)s %(name)s - %(message)s"


def load_config(path: str = "config.json") -> dict:
    p = Path(path)
    if not p.exists():
        print(f"ERROR: No se encontró {p.resolve()}")
        raise SystemExit(1)
    with open(p, "r", encoding="utf-8") as f:
        return json.load(f)


def setup_logging(level: str = "INFO"):
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format=LOG_FMT,
        handlers=[logging.StreamHandler(sys.stdout)],
    )


def main():
    parser = argparse.ArgumentParser(description="Auto-sync SoundCloud (CLI)")
    parser.add_argument(
        "--once",
        action="store_true",
        help="Ejecuta una sincronización completa y sale",
    )
    parser.add_argument(
        "--config",
        default="config.json",
        help="Ruta a config.json (default: ./config.json)",
    )
    args = parser.parse_args()

    setup_logging()
    config = load_config(args.config)

    sc_cfg = config.get("soundcloud", {})
    oauth_token = sc_cfg.get("oauth_token", "")
    client_id = sc_cfg.get("client_id", "")
    download_folder = config.get("dest_folder", os.path.expanduser("~/Music"))

    if not oauth_token or not client_id:
        print("ERROR: Configurá oauth_token y client_id en config.json")
        raise SystemExit(1)

    # Instanciar componentes
    try:
        api = SoundCloudAPIClient(oauth_token, client_id)
        api.validate_credentials()
    except Exception as e:
        print(f"ERROR: Credenciales inválidas - {e}")
        raise SystemExit(1)

    handler = SoundCloudHandler()
    manager = SyncManager(
        oauth_token=oauth_token,
        client_id=client_id,
        download_folder=download_folder,
        downloader=handler,
        similarity_threshold=sc_cfg.get("duplicate_checker", {}).get("similarity_threshold", 85),
        filename_pattern=config.get("filename_pattern", "{artist} - {title}"),
        subfolder_by_artist=config.get("subfolder_by_artist", False),
    )

    print(f"📁 Destino: {download_folder}")

    if args.once:
        print("🔄 Ejecutando sincronización única...")
        results = manager.sync_once()
        print(
            f"✅ Completado: +{results.get('new', 0)} nuevas, "
            f"⊘ {results.get('skipped', 0)} omitidas, "
            f"⚠ {results.get('errors', 0)} errores"
        )
        raise SystemExit(0 if results.get("errors", 0) == 0 else 2)

    # Si no es --once, comportarse como daemon scheduler cada 24h
    print("⏳ Iniciando scheduler cada 24 horas (Ctrl+C para salir)")
    import time

    try:
        while True:
            print(f"\n[{time.strftime('%Y-%m-%d %H:%M:%S')}] Sincronizando...")
            try:
                results = manager.sync_once()
                print(
                    f"  Resultado: +{results.get('new', 0)} | "
                    f"⊘ {results.get('skipped', 0)} | "
                    f"⚠ {results.get('errors', 0)}"
                )
            except Exception as e:
                print(f"  ERROR en sync: {e}")

            print("  Esperando 24 horas para la próxima sincronización...")
            try:
                time.sleep(24 * 60 * 60)
            except KeyboardInterrupt:
                raise
    except KeyboardInterrupt:
        print("\n👋 Scheduler detenido por usuario")
        raise SystemExit(0)


if __name__ == "__main__":
    main()
