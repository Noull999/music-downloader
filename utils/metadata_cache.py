"""
Caché de metadatos para evitar re-procesar URLs.
TTL automático: 7 días por defecto.
Uso: MetadataCache.get(url) / MetadataCache.set(url, data)
"""
import json
import logging
import os
import time
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

CACHE_DIR = Path.home() / ".cache" / "music_downloader"
CACHE_FILE = CACHE_DIR / "metadata.json"
CACHE_TTL_DAYS = 7


class MetadataCache:
    """Singleton cache para metadatos de URLs."""

    _instance: Optional["MetadataCache"] = None
    _data: dict = {}

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._init()
        return cls._instance

    def _init(self):
        """Carga caché desde disco."""
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        if CACHE_FILE.exists():
            try:
                with open(CACHE_FILE) as f:
                    self._data = json.load(f)
                self._cleanup_expired()
                logger.debug(f"✓ Caché de metadatos cargado ({len(self._data)} items)")
            except Exception as e:
                logger.warning(f"Error cargando caché: {e}")
                self._data = {}

    def get(self, url: str) -> Optional[dict]:
        """Obtiene metadatos del caché si existen y no han expirado."""
        if url not in self._data:
            return None

        item = self._data[url]
        if self._is_expired(item["timestamp"]):
            del self._data[url]
            self._save()
            return None

        logger.debug(f"✓ Caché hit: {url[:50]}...")
        return item.get("data")

    def set(self, url: str, data: dict) -> None:
        """Almacena metadatos en caché."""
        self._data[url] = {
            "data": data,
            "timestamp": time.time(),
        }
        self._save()

    def _is_expired(self, timestamp: float) -> bool:
        """Verifica si un item ha expirado."""
        age_days = (time.time() - timestamp) / 86400
        return age_days > CACHE_TTL_DAYS

    def _cleanup_expired(self) -> None:
        """Limpia items expirados."""
        initial = len(self._data)
        self._data = {
            k: v for k, v in self._data.items()
            if not self._is_expired(v["timestamp"])
        }
        if len(self._data) < initial:
            logger.debug(f"🧹 Caché limpiado: {initial - len(self._data)} items expirados")
            self._save()

    def _save(self) -> None:
        """Persiste caché a disco."""
        try:
            with open(CACHE_FILE, "w") as f:
                json.dump(self._data, f, indent=2)
        except Exception as e:
            logger.warning(f"Error guardando caché: {e}")

    def clear(self) -> None:
        """Limpia todo el caché."""
        self._data = {}
        self._save()
        logger.info("✓ Caché limpiado")
