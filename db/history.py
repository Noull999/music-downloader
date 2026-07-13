"""
Historial de descargas en SQLite.
Registra: qué se descargó, cuándo, de dónde, dónde está el archivo.
También guarda likes de SoundCloud y el log de sincronizaciones.
Usado para evitar re-descargar lo mismo y mostrar estadísticas.
"""
import csv
import sqlite3
import threading
import logging
from pathlib import Path
from typing import Optional

from utils.exceptions import DatabaseError

logger = logging.getLogger(__name__)

# DB ubicada en ~/.music_downloader/history.db
DB_PATH = Path.home() / ".music_downloader" / "history.db"
DB_PATH.parent.mkdir(exist_ok=True, parents=True)


class DownloadHistory:
    """
    Almacena historial de descargas, likes de SoundCloud y log de syncs en SQLite.
    Thread-safe: conexión compartida + RLock, usable desde múltiples threads.
    """

    def __init__(self, db_path: str = str(DB_PATH)):
        """
        Args:
            db_path: Ruta a la base de datos SQLite
        """
        self.db_path = db_path
        self.lock = threading.RLock()
        self.conn: Optional[sqlite3.Connection] = None
        self._init_db()

    def _init_db(self):
        """Crea tablas si no existen."""
        try:
            self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
            self.conn.row_factory = sqlite3.Row
            self.conn.executescript("""
                CREATE TABLE IF NOT EXISTS downloads (
                    id            INTEGER PRIMARY KEY AUTOINCREMENT,
                    url           TEXT UNIQUE NOT NULL,
                    title         TEXT,
                    artist        TEXT,
                    album         TEXT,
                    platform      TEXT DEFAULT 'soundcloud',
                    local_path    TEXT,
                    download_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    file_size     INTEGER,
                    duration      INTEGER
                );

                CREATE TABLE IF NOT EXISTS soundcloud_likes (
                    id          INTEGER PRIMARY KEY,
                    url         TEXT UNIQUE NOT NULL,
                    title       TEXT NOT NULL,
                    artist      TEXT,
                    duration_ms INTEGER,
                    artwork_url TEXT,
                    genre       TEXT,
                    created_at  TEXT,
                    liked_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS sync_log (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    synced_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    new_tracks  INTEGER DEFAULT 0,
                    skipped     INTEGER DEFAULT 0,
                    errors      INTEGER DEFAULT 0
                );

                CREATE INDEX IF NOT EXISTS idx_downloads_url
                    ON downloads(url);
                CREATE INDEX IF NOT EXISTS idx_downloads_platform
                    ON downloads(platform);
                CREATE INDEX IF NOT EXISTS idx_downloads_artist
                    ON downloads(artist);
                CREATE INDEX IF NOT EXISTS idx_downloads_date
                    ON downloads(download_date);
                CREATE INDEX IF NOT EXISTS idx_likes_url
                    ON soundcloud_likes(url);
            """)
            self.conn.commit()
            logger.info(f"✅ Base de datos inicializada en {self.db_path}")
        except sqlite3.Error as e:
            logger.error(f"Error inicializando DB: {e}")
            raise DatabaseError(f"Error inicializando BD: {e}")

    # ────────────────────────────────────────────────────────────────── #
    # Descargas                                                            #
    # ────────────────────────────────────────────────────────────────── #

    def is_downloaded(self, url: str) -> bool:
        """
        Verifica si una canción ya fue descargada.

        Args:
            url: URL del track

        Returns:
            True si el URL está en el historial
        """
        with self.lock:
            try:
                cursor = self.conn.execute(
                    "SELECT 1 FROM downloads WHERE url = ?", (url,)
                )
                return cursor.fetchone() is not None
            except sqlite3.Error as e:
                logger.error(f"Error verificando descarga: {e}")
                return False

    def mark_downloaded(
        self,
        url: str,
        title: str,
        artist: str,
        file_path: str,
        platform: str = "soundcloud"
    ):
        """
        Registra (o actualiza) una descarga en el historial.
        Usado por el flujo de sincronización de likes.

        Args:
            url: URL de la canción
            title: Título de la canción
            artist: Nombre del artista
            file_path: Ruta local donde se guardó el archivo
            platform: Plataforma ('soundcloud', 'youtube', etc)
        """
        with self.lock:
            try:
                self.conn.execute(
                    """
                    INSERT INTO downloads (url, title, artist, local_path, platform)
                    VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(url) DO UPDATE SET
                        title=excluded.title,
                        artist=excluded.artist,
                        local_path=excluded.local_path,
                        platform=excluded.platform,
                        download_date=CURRENT_TIMESTAMP
                    """,
                    (url, title, artist, file_path, platform)
                )
                self.conn.commit()
                logger.debug(f"✓ Registrada descarga: {artist} - {title}")
            except sqlite3.Error as e:
                logger.error(f"Error registrando descarga: {e}")

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
        """
        Agrega una descarga al historial. Usado por el flujo principal
        (descargas manuales); ignora si el URL ya existe.
        """
        with self.lock:
            try:
                self.conn.execute(
                    """
                    INSERT OR IGNORE INTO downloads
                    (url, title, artist, album, platform, local_path, file_size, duration)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (url, title, artist, album, platform, local_path, file_size, duration)
                )
                self.conn.commit()
                logger.debug(f"Descarga agregada al historial: {url}")
            except sqlite3.Error as e:
                logger.error(f"Error agregando al historial: {e}")
                raise DatabaseError(f"Error en historial: {e}")

    def get_all_urls(self) -> set[str]:
        """Retorna set de todas las URLs descargadas (lookup O(1))."""
        with self.lock:
            try:
                cursor = self.conn.execute("SELECT url FROM downloads")
                return {row[0] for row in cursor.fetchall()}
            except sqlite3.Error as e:
                logger.error(f"Error obteniendo URLs: {e}")
                return set()

    def get_all_downloads(self) -> list[dict]:
        """
        Obtiene la lista completa de descargas (formato compacto).

        Returns:
            Lista de {url, title, artist, file_path, platform, downloaded_at}
        """
        with self.lock:
            try:
                cursor = self.conn.execute(
                    "SELECT url, title, artist, local_path, platform, download_date "
                    "FROM downloads ORDER BY download_date DESC"
                )
                return [
                    {
                        "url": row["url"],
                        "title": row["title"],
                        "artist": row["artist"],
                        "file_path": row["local_path"],
                        "platform": row["platform"],
                        "downloaded_at": row["download_date"],
                    }
                    for row in cursor.fetchall()
                ]
            except sqlite3.Error as e:
                logger.error(f"Error obteniendo descargas: {e}")
                return []

    def get_recent_downloads(self, limit: Optional[int] = 50) -> list[dict]:
        """Obtiene descargas recientes (todas las columnas). limit=None trae todo."""
        with self.lock:
            try:
                if limit is None:
                    cursor = self.conn.execute(
                        "SELECT * FROM downloads ORDER BY download_date DESC"
                    )
                else:
                    cursor = self.conn.execute(
                        "SELECT * FROM downloads ORDER BY download_date DESC LIMIT ?",
                        (limit,)
                    )
                return [dict(row) for row in cursor.fetchall()]
            except sqlite3.Error as e:
                logger.error(f"Error obteniendo recientes: {e}")
                return []

    def get_download_count(self) -> int:
        """Retorna el total de descargas registradas."""
        with self.lock:
            try:
                cursor = self.conn.execute("SELECT COUNT(*) FROM downloads")
                return cursor.fetchone()[0]
            except sqlite3.Error as e:
                logger.error(f"Error contando descargas: {e}")
                return 0

    def search_downloads(self, query: str) -> list[dict]:
        """Busca descargas por título, artista o URL."""
        with self.lock:
            try:
                term = f"%{query}%"
                cursor = self.conn.execute(
                    """
                    SELECT * FROM downloads
                    WHERE title LIKE ? OR artist LIKE ? OR url LIKE ?
                    ORDER BY download_date DESC
                    """,
                    (term, term, term)
                )
                return [dict(row) for row in cursor.fetchall()]
            except sqlite3.Error as e:
                logger.error(f"Error buscando: {e}")
                return []

    def delete_download(self, url: str) -> bool:
        """Elimina una descarga del historial. Retorna True si existía."""
        with self.lock:
            try:
                cursor = self.conn.execute("DELETE FROM downloads WHERE url = ?", (url,))
                self.conn.commit()
                return cursor.rowcount > 0
            except sqlite3.Error as e:
                logger.error(f"Error eliminando descarga: {e}")
                return False

    def clear_history(self) -> None:
        """Elimina TODO el historial de descargas (cuidado!)."""
        with self.lock:
            try:
                self.conn.execute("DELETE FROM downloads")
                self.conn.commit()
                logger.warning("✓ Historial completamente borrado")
            except sqlite3.Error as e:
                raise DatabaseError(f"Error borrando historial: {e}")

    def export_to_csv(self, output_path: str) -> None:
        """Exporta el historial completo a CSV."""
        try:
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

    # ────────────────────────────────────────────────────────────────── #
    # SoundCloud likes                                                     #
    # ────────────────────────────────────────────────────────────────── #

    def mark_like_downloaded(
        self,
        url: str,
        title: str,
        artist: str,
        track_id: int = None,
        duration_ms: int = None,
        artwork_url: str = None,
        genre: str = None,
        created_at: str = None
    ):
        """
        Registra una canción de SoundCloud Likes cuando es descargada.
        Añade a soundcloud_likes si no existe.
        """
        with self.lock:
            try:
                self.conn.execute(
                    """
                    INSERT OR IGNORE INTO soundcloud_likes
                    (id, url, title, artist, duration_ms, artwork_url, genre, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (track_id, url, title, artist, duration_ms, artwork_url, genre, created_at)
                )
                self.conn.commit()
                logger.debug(f"✓ Registrada en soundcloud_likes: {artist} - {title}")
            except sqlite3.Error as e:
                logger.error(f"Error registrando en soundcloud_likes: {e}")

    def save_likes(self, tracks: list):
        """Guarda likes obtenidos de SoundCloud en la DB (reemplaza los anteriores)."""
        with self.lock:
            try:
                self.conn.execute("DELETE FROM soundcloud_likes")
                for track in tracks:
                    self.conn.execute(
                        """
                        INSERT OR REPLACE INTO soundcloud_likes
                        (id, url, title, artist, duration_ms, artwork_url, genre, created_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            track.id,
                            track.url,
                            track.title,
                            track.artist,
                            track.duration_ms,
                            track.artwork_url,
                            track.genre,
                            track.created_at
                        )
                    )
                self.conn.commit()
                logger.info(f"✓ {len(tracks)} likes guardados en DB")
            except sqlite3.Error as e:
                logger.error(f"Error guardando likes: {e}")

    def load_likes(self) -> list:
        """Carga los likes guardados en la DB."""
        with self.lock:
            try:
                cursor = self.conn.execute(
                    """
                    SELECT id, url, title, artist, duration_ms, artwork_url, genre, created_at
                    FROM soundcloud_likes ORDER BY liked_at DESC
                    """
                )
                likes = [
                    {
                        "id": row["id"],
                        "url": row["url"],
                        "title": row["title"],
                        "artist": row["artist"],
                        "duration_ms": row["duration_ms"],
                        "artwork_url": row["artwork_url"],
                        "genre": row["genre"],
                        "created_at": row["created_at"],
                    }
                    for row in cursor.fetchall()
                ]
                logger.info(f"✓ {len(likes)} likes cargados de DB")
                return likes
            except sqlite3.Error as e:
                logger.error(f"Error cargando likes: {e}")
                return []

    # ────────────────────────────────────────────────────────────────── #
    # Log de sincronizaciones                                              #
    # ────────────────────────────────────────────────────────────────── #

    def log_sync(self, new: int, skipped: int, errors: int):
        """Registra un evento de sincronización."""
        with self.lock:
            try:
                self.conn.execute(
                    "INSERT INTO sync_log (new_tracks, skipped, errors) VALUES (?, ?, ?)",
                    (new, skipped, errors)
                )
                self.conn.commit()
                logger.info(f"Sync log: +{new} | -{skipped} | ⚠️{errors}")
            except sqlite3.Error as e:
                logger.error(f"Error logging sync: {e}")

    def get_last_sync(self) -> dict | None:
        """Obtiene info de la última sincronización, o None si no hay ninguna."""
        with self.lock:
            try:
                cursor = self.conn.execute(
                    "SELECT synced_at, new_tracks, skipped, errors "
                    "FROM sync_log ORDER BY id DESC LIMIT 1"
                )
                row = cursor.fetchone()
                if not row:
                    return None
                return {
                    "synced_at": row["synced_at"],
                    "new_tracks": row["new_tracks"],
                    "skipped": row["skipped"],
                    "errors": row["errors"],
                }
            except sqlite3.Error as e:
                logger.error(f"Error obteniendo último sync: {e}")
                return None

    # ────────────────────────────────────────────────────────────────── #
    # Stats                                                                #
    # ────────────────────────────────────────────────────────────────── #

    def get_stats(self) -> dict:
        """
        Obtiene estadísticas globales del historial.

        Returns:
            {
                'total_tracks' / 'total_downloads': int (alias, mismo valor),
                'total_artists': int,
                'by_platform': {'soundcloud': int, 'youtube': int, ...},
                'total_size_bytes': int,
                'total_duration_seconds': int,
                'db_file': str,
            }
        """
        with self.lock:
            try:
                cursor = self.conn.execute(
                    "SELECT COUNT(*), COUNT(DISTINCT artist) FROM downloads"
                )
                total, artists = cursor.fetchone()

                cursor = self.conn.execute(
                    "SELECT platform, COUNT(*) FROM downloads GROUP BY platform"
                )
                by_platform = {row[0]: row[1] for row in cursor.fetchall()}

                cursor = self.conn.execute(
                    "SELECT SUM(file_size), SUM(duration) FROM downloads"
                )
                total_size, total_duration = cursor.fetchone()

                return {
                    "total_tracks": total,
                    "total_downloads": total,
                    "total_artists": artists,
                    "by_platform": by_platform,
                    "total_size_bytes": total_size or 0,
                    "total_duration_seconds": total_duration or 0,
                    "db_file": str(self.db_path),
                }
            except sqlite3.Error as e:
                logger.error(f"Error obteniendo stats: {e}")
                return {
                    "total_tracks": 0,
                    "total_downloads": 0,
                    "total_artists": 0,
                    "by_platform": {},
                    "total_size_bytes": 0,
                    "total_duration_seconds": 0,
                    "db_file": str(self.db_path),
                }

    def close(self):
        """Cierra la conexión a la DB."""
        if self.conn:
            self.conn.close()
