"""
Escaneo de biblioteca ya descargada para encontrar duplicados de AUDIO real
(mismo contenido sonoro, distinto nombre de archivo), usando fingerprinting
acústico. Complementa a `duplicate_checker.py`, que solo compara nombres
antes de descargar.

Uso típico: botón "Buscar duplicados de audio" en la ventana de historial.
"""
import logging
import os
from pathlib import Path
from typing import Callable, Optional

from utils.audio_fingerprint import is_available, fingerprint_file, similarity

logger = logging.getLogger(__name__)

AUDIO_EXTENSIONS = {".mp3", ".flac", ".m4a", ".wav", ".ogg", ".opus", ".aac"}

DEFAULT_SIMILARITY_THRESHOLD = 92.0  # % — audio prácticamente idéntico


def scan_folder_for_audio_duplicates(
    folder: str,
    threshold: float = DEFAULT_SIMILARITY_THRESHOLD,
    progress_cb: Optional[Callable[[int, int], None]] = None,
) -> list[list[str]]:
    """
    Recorre `folder` recursivamente, calcula el fingerprint de cada archivo
    de audio y agrupa los que resultan acústicamente iguales (>= threshold).

    Args:
        folder: carpeta a escanear (recursivo)
        threshold: % de similitud mínimo para considerar duplicado (0-100)
        progress_cb: callback opcional (procesados, total)

    Returns:
        Lista de grupos; cada grupo es una lista de rutas de archivo que
        son duplicados de audio entre sí. Grupos de tamaño 1 no se incluyen.

    Nota: O(n²) comparaciones — pensado para bibliotecas de cientos/pocos
    miles de archivos, no como operación en caliente durante la descarga.
    """
    if not is_available():
        logger.warning(
            "Escaneo de duplicados de audio no disponible: falta pyacoustid "
            "o el binario fpcalc (chromaprint) en PATH."
        )
        return []

    files = [
        str(p) for p in Path(folder).rglob("*")
        if p.is_file() and p.suffix.lower() in AUDIO_EXTENSIONS
    ]
    total = len(files)

    fingerprints: dict[str, tuple] = {}
    for i, file_path in enumerate(files):
        fp = fingerprint_file(file_path)
        if fp:
            fingerprints[file_path] = fp
        if progress_cb:
            try:
                progress_cb(i + 1, total)
            except Exception:
                pass

    # Agrupar por similitud (union-find simple)
    paths = list(fingerprints.keys())
    parent = {p: p for p in paths}

    def find(x: str) -> str:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a: str, b: str) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb

    for i in range(len(paths)):
        for j in range(i + 1, len(paths)):
            a, b = paths[i], paths[j]
            if similarity(fingerprints[a], fingerprints[b]) >= threshold:
                union(a, b)

    groups: dict[str, list[str]] = {}
    for p in paths:
        root = find(p)
        groups.setdefault(root, []).append(p)

    result = [g for g in groups.values() if len(g) > 1]
    logger.info(
        "Escaneo de duplicados de audio: %d archivos analizados, %d grupos duplicados encontrados.",
        total, len(result),
    )
    return result
