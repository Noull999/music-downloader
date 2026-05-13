"""
Utilidades de imagenes/thumbnails para la GUI.
La logica de embebido de tags esta en quality/post_processor.py.
"""
import io
import logging
from typing import Optional

import requests

logger = logging.getLogger(__name__)


def load_thumbnail_image(url: str, size: tuple[int, int] = (48, 48)):
    """
    Descarga una thumbnail y retorna un objeto PIL Image redimensionado.
    Retorna None si falla o Pillow no esta disponible.
    """
    try:
        from PIL import Image
    except ImportError:
        return None

    data = _fetch_bytes(url)
    if not data:
        return None

    try:
        img = Image.open(io.BytesIO(data)).convert("RGB")
        img = img.resize(size, Image.LANCZOS)
        return img
    except Exception as exc:
        logger.debug("Error procesando thumbnail: %s", exc)
        return None


def _fetch_bytes(url: str, timeout: int = 8) -> Optional[bytes]:
    if not url:
        return None
    try:
        resp = requests.get(url, timeout=timeout)
        resp.raise_for_status()
        return resp.content
    except Exception as exc:
        logger.debug("No se pudo descargar thumbnail %s: %s", url, exc)
        return None
