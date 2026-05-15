"""
ImageCacheManager: Caché de imágenes en SQLite para evitar re-descargas.
Almacena URL → bytes, válidas por 30 días.
"""
import sqlite3
import logging
import hashlib
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional
import threading

logger = logging.getLogger(__name__)


class ImageCacheManager:
    """Caché de imágenes para metadata (carátulas, thumbnails)."""

    def __init__(self, cache_dir: str = "~/.music_downloader"):
        self.cache_dir = Path(cache_dir).expanduser()
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.db_path = self.cache_dir / "image_cache.db"
        self._lock = threading.Lock()
        self._init_db()

    def _init_db(self) -> None:
        """Inicializa esquema de caché."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS image_cache (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        url TEXT UNIQUE NOT NULL,
                        url_hash TEXT UNIQUE,
                        image_bytes BLOB,
                        mime_type TEXT DEFAULT 'image/jpeg',
                        cached_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        expires_date TIMESTAMP,
                        size_bytes INTEGER,
                        hit_count INTEGER DEFAULT 0
                    )
                """)
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_expires ON image_cache(expires_date)
                """)
                conn.commit()
            logger.debug(f"✓ Image cache BD inicializada: {self.db_path}")
        except sqlite3.Error as e:
            logger.error(f"Error inicializando image cache: {e}")

    def get(self, url: str) -> Optional[bytes]:
        """Obtiene imagen del caché. Retorna bytes o None si no existe/expiró."""
        if not url:
            return None

        with self._lock:
            try:
                with sqlite3.connect(self.db_path) as conn:
                    cursor = conn.cursor()
                    cursor.execute("""
                        SELECT image_bytes FROM image_cache
                        WHERE url = ? AND expires_date > datetime('now')
                    """, (url,))
                    row = cursor.fetchone()

                    if row and row[0]:
                        # Incrementar hit count
                        cursor.execute(
                            "UPDATE image_cache SET hit_count = hit_count + 1 WHERE url = ?",
                            (url,)
                        )
                        conn.commit()
                        logger.debug(f"✓ Cache hit para imagen: {url[:50]}...")
                        return row[0]

                    return None
            except sqlite3.Error as e:
                logger.warning(f"Error leyendo image cache: {e}")
                return None

    def set(self, url: str, image_bytes: bytes, mime_type: str = "image/jpeg", ttl_days: int = 30) -> bool:
        """Almacena imagen en caché con TTL."""
        if not url or not image_bytes:
            return False

        url_hash = hashlib.md5(url.encode()).hexdigest()
        expires = datetime.now() + timedelta(days=ttl_days)

        with self._lock:
            try:
                with sqlite3.connect(self.db_path) as conn:
                    cursor = conn.cursor()
                    cursor.execute("""
                        INSERT OR REPLACE INTO image_cache
                        (url, url_hash, image_bytes, mime_type, expires_date, size_bytes)
                        VALUES (?, ?, ?, ?, ?, ?)
                    """, (url, url_hash, image_bytes, mime_type, expires, len(image_bytes)))
                    conn.commit()
                logger.debug(
                    f"✓ Imagen cacheada ({len(image_bytes)//1024}KB): "
                    f"{url[:50]}... (TTL: {ttl_days}d)"
                )
                return True
            except sqlite3.Error as e:
                logger.warning(f"Error escribiendo image cache: {e}")
                return False

    def cleanup_expired(self) -> int:
        """Elimina imágenes expiradas. Retorna count."""
        with self._lock:
            try:
                with sqlite3.connect(self.db_path) as conn:
                    cursor = conn.cursor()
                    cursor.execute(
                        "DELETE FROM image_cache WHERE expires_date < datetime('now')"
                    )
                    conn.commit()
                    deleted = cursor.rowcount
                    if deleted > 0:
                        logger.info(f"✓ {deleted} imágenes expiradas eliminadas del caché")
                    return deleted
            except sqlite3.Error as e:
                logger.warning(f"Error limpiando caché: {e}")
                return 0

    def get_stats(self) -> dict:
        """Retorna estadísticas del caché."""
        with self._lock:
            try:
                with sqlite3.connect(self.db_path) as conn:
                    cursor = conn.cursor()

                    # Total imágenes
                    cursor.execute("SELECT COUNT(*) FROM image_cache")
                    total = cursor.fetchone()[0]

                    # Tamaño total
                    cursor.execute("SELECT SUM(size_bytes) FROM image_cache")
                    total_size = cursor.fetchone()[0] or 0

                    # Hit rate
                    cursor.execute("SELECT SUM(hit_count) FROM image_cache")
                    total_hits = cursor.fetchone()[0] or 0

                    return {
                        "cached_images": total,
                        "total_size_bytes": total_size,
                        "total_hits": total_hits,
                        "avg_size_bytes": total_size // total if total > 0 else 0,
                    }
            except sqlite3.Error as e:
                logger.warning(f"Error obteniendo stats: {e}")
                return {}

    def clear_all(self) -> bool:
        """Limpia TODO el caché (cuidado!)."""
        with self._lock:
            try:
                with sqlite3.connect(self.db_path) as conn:
                    cursor = conn.cursor()
                    cursor.execute("DELETE FROM image_cache")
                    conn.commit()
                logger.warning("✓ Caché de imágenes completamente limpiado")
                return True
            except sqlite3.Error as e:
                logger.error(f"Error limpiando caché: {e}")
                return False
