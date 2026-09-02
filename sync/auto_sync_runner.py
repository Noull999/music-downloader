"""
Sincronización sin interfaz, reutilizable.

Vive en sync/ (no en scripts/) a propósito: así viaja dentro del .exe
empaquetado y el ejecutable puede correr la sincronización programada por
sí mismo, sin depender de que la carpeta del proyecto siga existiendo.

Lo usan:
  - scripts/auto_sync.py          (CLI, desarrollo)
  - main_webview.py --auto-sync   (el .exe, tarea programada)
"""
import io
import json
import logging
import os
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

from config.manager import DEFAULT_CONFIG_PATH
from handlers.soundcloud_handler import SoundCloudHandler
from sync import match_utils
from sync.sync_manager import SyncManager

LOG_FMT = "%(asctime)s %(levelname)s %(name)s - %(message)s"
LOG_FILE = Path.home() / ".music_downloader" / "auto_sync.log"

logger = logging.getLogger("auto_sync")


def fix_std_streams() -> None:
    """
    Corre vía Task Scheduler con pythonw.exe / .exe sin consola: sys.stdout
    y sys.stderr pueden ser None (-> AttributeError en el primer print) o
    tener encoding cp1252 (-> UnicodeEncodeError con los emojis del log).
    """
    for name in ("stdout", "stderr"):
        stream = getattr(sys, name)
        if stream is None:
            setattr(sys, name, io.StringIO())
        elif hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass


def setup_logging(level: str = "INFO") -> None:
    """
    Log a archivo además de stdout: sin consola visible no queda rastro de
    si la sincronización programada funcionó.
    """
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    file_handler = RotatingFileHandler(
        LOG_FILE, maxBytes=2 * 1024 * 1024, backupCount=3, encoding="utf-8"
    )
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format=LOG_FMT,
        handlers=[logging.StreamHandler(sys.stdout), file_handler],
    )


def load_config(path: str) -> dict:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"No se encontró {p}")
    with open(p, "r", encoding="utf-8") as f:
        return json.load(f)


def build_manager(config: dict) -> SyncManager:
    """Arma un SyncManager con la misma configuración que usa la GUI."""
    sc_cfg = config.get("soundcloud", {})
    oauth_token = sc_cfg.get("oauth_token", "")
    client_id = sc_cfg.get("client_id", "")
    if not oauth_token or not client_id:
        raise ValueError(
            "Faltan credenciales: configurá soundcloud.oauth_token y "
            "soundcloud.client_id (se hace desde la app, en 'Conectar cuenta')"
        )

    download_folder = config.get("dest_folder", str(Path.home() / "Music"))
    threshold = config.get("duplicate_checker", {}).get(
        "similarity_threshold", match_utils.MATCH_THRESHOLD
    )
    # Mismas carpetas de biblioteca que la GUI, para no re-descargar lo que
    # ya existe fuera de dest_folder.
    library_folders = config.get("library_folders") or []
    if not library_folders and download_folder:
        parent = os.path.dirname(str(download_folder).rstrip("\\/"))
        library_folders = [parent] if parent else []

    return SyncManager(
        oauth_token, client_id,
        download_folder,
        SoundCloudHandler(),
        similarity_threshold=threshold,
        filename_pattern=config.get("filename_pattern", "{artist} - {title}"),
        subfolder_by_artist=config.get("subfolder_by_artist", False),
        library_folders=library_folders,
        analyze_audio=config.get("analyze_audio", False),
        key_format=config.get("key_format", "camelot"),
        fingerprint_check=config.get("fingerprint_check", True),
        quality_preset=config.get("quality_preset", "mp3_320"),
        post_options={
            "normalize_volume": config.get("normalize_volume", False),
            "remove_silence": config.get("remove_silence", False),
            "embed_artwork": config.get("embed_artwork", True),
            "embed_metadata": config.get("embed_metadata", True),
        },
    )


def run(config_path: str = None, validate_only: bool = False) -> int:
    """
    Ejecuta una sincronización completa. Devuelve el código de salida
    (0 = OK, 1 = error), pensado para usarse como exit code de la tarea
    programada.
    """
    fix_std_streams()
    setup_logging()

    try:
        config = load_config(config_path or str(DEFAULT_CONFIG_PATH))
    except Exception as e:
        logger.error(f"❌ No se pudo leer la configuración: {e}")
        return 1

    try:
        manager = build_manager(config)
    except Exception as e:
        logger.error(f"❌ {e}")
        return 1

    try:
        manager.validate_credentials()
    except Exception as e:
        logger.error(f"❌ Credenciales inválidas o expiradas: {e}")
        return 1

    if validate_only:
        logger.info("✅ Credenciales válidas (no se descargó nada)")
        return 0

    try:
        results = manager.sync_once()
    except Exception as e:
        logger.error(f"❌ Error durante la sincronización: {e}")
        return 1

    logger.info(
        f"✅ Sync completa: +{results['new']} nuevas | "
        f"{results['skipped']} ya tenías | {results['errors']} errores"
    )
    return 0 if results["errors"] == 0 else 1
