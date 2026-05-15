"""
HistoryManager: Gestiona historial de descargas en SQLite.
Reemplaza history.json con BD más eficiente y thread-safe.
"""
import sqlite3
import logging
import threading
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Set, Dict, Any

from utils.exceptions import DatabaseError

logger = logging.getLogger(__name__)


class HistoryManager:
    """Gestiona historial de descargas con SQLite."""

    def __init__(self, db_path: str = "~/.music_downloader/history.db"):
        self.db_path = Path(db_path).expanduser()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()  # Thread-safe
        self._init_db()

    def _init_db(self) -> None:
        """Inicializa esquema de BD."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS downloads (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        url TEXT UNIQUE NOT NULL,
                        title TEXT,
                        artist TEXT,
                        album TEXT,
                        platform TEXT,
                        local_path TEXT,
                        download_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        file_size INTEGER,
                        duration INTEGER
                    )
                """)
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_url ON downloads(url)
                """)
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_date ON downloads(download_date)
                """)
                conn.commit()
            logger.info(f"✓ BD de historial inicializada: {self.db_path}")
        except sqlite3.Error as e:
            raise DatabaseError(f"Error inicializando BD: {e}")

    def add_download(
        self,
        url: str,
        title: str = "",
        artist: str = "",
        album: str = "",
        platform: str = "",
        local_path: str = "",
        file_size: int = 0,
        duration: int = 0,
    ) -> None:
        """Agrega descarga al historial."""
        with self._lock:
            try:
                with sqlite3.connect(self.db_path) as conn:
                    cursor = conn.cursor()
                    cursor.execute("""
                        INSERT OR IGNORE INTO downloads
                        (url, title, artist, album, platform, local_path,
                         file_size, duration)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """, (url, title, artist, album, platform, local_path,
                          file_size, duration))
                    conn.commit()
                    logger.debug(f"Descarga agregada al historial: {url}")
            except sqlite3.IntegrityError:
                logger.debug(f"Descarga duplicada (ya existe): {url}")
            except sqlite3.Error as e:
                logger.error(f"Error agregando al historial: {e}")
                raise DatabaseError(f"Error en historial: {e}")

    def is_downloaded(self, url: str) -> bool:
        """Verifica si URL ya fue descargada."""
        with self._lock:
            try:
                with sqlite3.connect(self.db_path) as conn:
                    cursor = conn.cursor()
                    cursor.execute("SELECT 1 FROM downloads WHERE url = ?", (url,))
                    return cursor.fetchone() is not None
            except sqlite3.Error as e:
                logger.error(f"Error verificando descarga: {e}")
                return False

    def get_all_urls(self) -> Set[str]:
        """Retorna SET de todas las URLs descargadas (O(1) lookup)."""
        with self._lock:
            try:
                with sqlite3.connect(self.db_path) as conn:
                    cursor = conn.cursor()
                    cursor.execute("SELECT url FROM downloads")
                    return {row[0] for row in cursor.fetchall()}
            except sqlite3.Error as e:
                logger.error(f"Error obteniendo URLs: {e}")
                return set()

    def get_recent_downloads(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Obtiene descargas recientes."""
        with self._lock:
            try:
                with sqlite3.connect(self.db_path) as conn:
                    conn.row_factory = sqlite3.Row
                    cursor = conn.cursor()
                    cursor.execute("""
                        SELECT * FROM downloads
                        ORDER BY download_date DESC
                        LIMIT ?
                    """, (limit,))
                    return [dict(row) for row in cursor.fetchall()]
            except sqlite3.Error as e:
                logger.error(f"Error obteniendo recientes: {e}")
                return []

    def get_download_count(self) -> int:
        """Retorna total de descargas."""
        with self._lock:
            try:
                with sqlite3.connect(self.db_path) as conn:
                    cursor = conn.cursor()
                    cursor.execute("SELECT COUNT(*) FROM downloads")
                    return cursor.fetchone()[0]
            except sqlite3.Error as e:
                logger.error(f"Error contando descargas: {e}")
                return 0

    def search_downloads(self, query: str) -> List[Dict[str, Any]]:
        """Busca descargas por título, artista o URL."""
        with self._lock:
            try:
                with sqlite3.connect(self.db_path) as conn:
                    conn.row_factory = sqlite3.Row
                    cursor = conn.cursor()
                    search_term = f"%{query}%"
                    cursor.execute("""
                        SELECT * FROM downloads
                        WHERE title LIKE ? OR artist LIKE ? OR url LIKE ?
                        ORDER BY download_date DESC
                    """, (search_term, search_term, search_term))
                    return [dict(row) for row in cursor.fetchall()]
            except sqlite3.Error as e:
                logger.error(f"Error buscando: {e}")
                return []

    def delete_download(self, url: str) -> bool:
        """Elimina un descarga del historial."""
        with self._lock:
            try:
                with sqlite3.connect(self.db_path) as conn:
                    cursor = conn.cursor()
                    cursor.execute("DELETE FROM downloads WHERE url = ?", (url,))
                    conn.commit()
                    return cursor.rowcount > 0
            except sqlite3.Error as e:
                logger.error(f"Error eliminando descarga: {e}")
                return False

    def clear_history(self) -> None:
        """Elimina TODO el historial (cuidado!)."""
        with self._lock:
            try:
                with sqlite3.connect(self.db_path) as conn:
                    cursor = conn.cursor()
                    cursor.execute("DELETE FROM downloads")
                    conn.commit()
                logger.warning("✓ Historial completamente borrado")
            except sqlite3.Error as e:
                raise DatabaseError(f"Error borrando historial: {e}")

    def export_to_csv(self, output_path: str) -> None:
        """Exporta historial a CSV."""
        try:
            import csv
            downloads = self.get_recent_downloads(limit=None)
            if not downloads:
                logger.warning("Historial vacío, nada que exportar")
                return

            with open(output_path, "w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=downloads[0].keys())
                writer.writeheader()
                writer.writerows(downloads)
            logger.info(f"✓ Historial exportado a: {output_path}")
        except Exception as e:
            logger.error(f"Error exportando CSV: {e}")
            raise DatabaseError(f"Error exportando: {e}")

    def get_stats(self) -> Dict[str, Any]:
        """Retorna estadísticas de descarga."""
        with self._lock:
            try:
                with sqlite3.connect(self.db_path) as conn:
                    cursor = conn.cursor()

                    # Total descargas
                    cursor.execute("SELECT COUNT(*) FROM downloads")
                    total = cursor.fetchone()[0]

                    # Por plataforma
                    cursor.execute("""
                        SELECT platform, COUNT(*) FROM downloads
                        GROUP BY platform
                    """)
                    by_platform = dict(cursor.fetchall())

                    # Tamaño total
                    cursor.execute("SELECT SUM(file_size) FROM downloads")
                    total_size = cursor.fetchone()[0] or 0

                    # Duración total
                    cursor.execute("SELECT SUM(duration) FROM downloads")
                    total_duration = cursor.fetchone()[0] or 0

                    return {
                        "total_downloads": total,
                        "by_platform": by_platform,
                        "total_size_bytes": total_size,
                        "total_duration_seconds": total_duration,
                        "db_file": str(self.db_path),
                    }
            except sqlite3.Error as e:
                logger.error(f"Error calculando estadísticas: {e}")
                return {}
