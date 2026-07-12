#!/usr/bin/env python3
"""
Auto-sync standalone: ejecuta una sincronización de likes de SoundCloud
sin necesidad de abrir la GUI.

Uso:
    python scripts/auto_sync.py [--once] [--validate]
"""
import argparse
import json
import logging
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sync.soundcloud_api import SoundCloudAPIClient


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
    parser.add_argument("--config", default="config.json", help="Ruta a config.json")
    parser.add_argument("--once", action="store_true", help="(No usado, se admite por compatibilidad)")
    parser.add_argument("--validate", action="store_true", help="Solo valida credenciales y sale")
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

    try:
        api = SoundCloudAPIClient(oauth_token, client_id)
        user = api.validate_credentials()
        print(f"✅ Credenciales válidas: {user.get('username')} | {user.get('likes_count')} likes")
        raise SystemExit(0)
    except Exception as e:
        print(f"❌ Credenciales inválidas: {e}")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
