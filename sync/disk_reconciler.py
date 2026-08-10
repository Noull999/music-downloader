"""
Reconecta el historial de descargas con archivos que el usuario movió a mano
a su biblioteca real (ej. organizándolos por género él mismo, fuera de la
carpeta de destino configurada).

No mueve, renombra ni borra NINGÚN archivo — solo corrige `local_path` en la
base de datos cuando encuentra, por similitud de nombre, el archivo real que
le corresponde a una URL ya registrada.
"""
import logging
import os
import re
import unicodedata
from pathlib import Path
from typing import Callable, Optional

from thefuzz import fuzz

logger = logging.getLogger(__name__)

AUDIO_EXTENSIONS = {".mp3", ".m4a", ".flac", ".wav", ".ogg", ".opus", ".aac"}
DEFAULT_THRESHOLD = 75


def _normalize(text: str) -> str:
    """Sin tildes, minúsculas, sin puntuación — mismo criterio que duplicate_checker."""
    text = unicodedata.normalize("NFD", text)
    text = "".join(c for c in text if unicodedata.category(c) != "Mn")
    text = text.lower()
    text = re.sub(r"[^\w\s]", " ", text)
    return " ".join(text.split())


def _index_audio_files(root_folder: str) -> list[tuple[str, str]]:
    """[(nombre_normalizado, ruta_completa), ...] de todo el audio bajo root_folder."""
    index = []
    try:
        for path in Path(root_folder).rglob("*"):
            if path.is_file() and path.suffix.lower() in AUDIO_EXTENSIONS:
                index.append((_normalize(path.stem), str(path)))
    except OSError as e:
        logger.warning("Error escaneando %s: %s", root_folder, e)
    return index


def reconcile_library(
    root_folder: str,
    history,
    threshold: int = DEFAULT_THRESHOLD,
    progress_cb: Optional[Callable[[int, int], None]] = None,
) -> dict:
    """
    Escanea `root_folder` y reconecta cada descarga ya registrada (por URL)
    con el archivo real en disco, si lo encuentra por similitud de nombre
    (artista + título vs. nombre de archivo).

    La mayoría de los archivos de una biblioteca real no van a matchear
    contra el historial de esta app — vienen de otras fuentes (Beatport,
    packs gratis, etc). Eso es esperable, no un error.

    Returns:
        dict con conteos: reconnected, already_ok, still_missing, scanned_files.
    """
    downloads = history.get_all_downloads()
    total = len(downloads)
    index = _index_audio_files(root_folder)

    result = {
        "reconnected": 0,
        "already_ok": 0,
        "still_missing": 0,
        "scanned_files": len(index),
    }
    claimed: set[str] = set()

    for i, d in enumerate(downloads):
        if progress_cb:
            try:
                progress_cb(i + 1, total)
            except Exception:
                pass

        current_path = d.get("file_path") or ""
        if current_path and os.path.isfile(current_path):
            result["already_ok"] += 1
            claimed.add(current_path)
            continue

        search = _normalize(f"{d.get('artist','')} {d.get('title','')}")
        if not search:
            result["still_missing"] += 1
            continue

        best_score = 0
        best_path = None
        for name, path in index:
            if path in claimed:
                continue
            score = max(
                fuzz.token_sort_ratio(search, name),
                fuzz.partial_token_sort_ratio(search, name),
            )
            if score > best_score:
                best_score = score
                best_path = path

        if best_path and best_score >= threshold:
            try:
                history.mark_downloaded(
                    d["url"], d["title"], d["artist"], best_path,
                    platform=d.get("platform") or "soundcloud",
                )
                claimed.add(best_path)
                result["reconnected"] += 1
            except Exception as e:
                logger.warning("No se pudo reconectar %s: %s", d.get("url"), e)
                result["still_missing"] += 1
        else:
            result["still_missing"] += 1

    return result
