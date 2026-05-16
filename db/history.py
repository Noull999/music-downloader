"""
Historial de descargas en SQLite.
Registra: qué se descargó, cuándo, de dónde, dónde está el archivo.
Usado para evitar re-descargar lo mismo.
"""
import sqlite3
import threading
import logging
from pathlib import Path
from datetime import datetime

logger = logging.getLogger(__name__)

# DB ubicada en ~/.music_downloader/history.db
DB_PATH = Path.home() / ".music_downloader" / "history.db"
DB_PATH.parent.mkdir(exist_ok=True, parents=True)


class DownloadHistory:
    """
    Almacena historial de descargas en SQLite.
    Thread-safe para uso desde múltiples threads.
    """

    def __init__(self, db_path: str = str(DB_PATH)):
        """
        Args:
            db_path: Ruta a la base de datos SQLite
        """
        self.db_path = db_path
        self.lock = threading.RLock()
        self.conn = None
        self._init_db()

    def _init_db(self):
        """Crea tablas si no existen."""
        try:
            self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
            self.conn.executescript("""
                CREATE TABLE IF NOT EXISTS downloads (
                    url         TEXT PRIMARY KEY,
                    title       TEXT NOT NULL,
                    artist      TEXT,
                    file_path   TEXT,
                    platform    TEXT DEFAULT 'soundcloud',
                    downloaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
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

                CREATE INDEX IF NOT EXISTS idx_downloads_platform
                    ON downloads(platform);
                CREATE INDEX IF NOT EXISTS idx_downloads_artist
                    ON downloads(artist);
                CREATE INDEX IF NOT EXISTS idx_likes_url
                    ON soundcloud_likes(url);
            """)
            self.conn.commit()
            logger.info(f"✅ Base de datos inicializada en {self.db_path}")
        except sqlite3.Error as e:
            logger.error(f"Error inicializando DB: {e}")
            raise

    def is_downloaded(self, url: str) -> bool:
        """
        Verifica si una canción ya fue descargada.

        Args:
            url: URL de SoundCloud (permalink_url)

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
        Registra una descarga en el historial.

        Args:
            url: URL de SoundCloud
            title: Título de la canción
            artist: Nombre del artista
            file_path: Ruta local donde se guardó el archivo
            platform: Plataforma ('soundcloud', 'youtube', etc)
        """
        with self.lock:
            try:
                # Intenta con esquema nuevo (local_path)
                try:
                    self.conn.execute(
                        """
                        INSERT OR REPLACE INTO downloads
                        (url, title, artist, local_path, platform, download_date)
                        VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                        """,
                        (url, title, artist, file_path, platform)
                    )
                except sqlite3.OperationalError:
                    # Fallback a esquema viejo (file_path)
                    self.conn.execute(
                        """
                        INSERT OR REPLACE INTO downloads
                        (url, title, artist, file_path, platform)
                        VALUES (?, ?, ?, ?, ?)
                        """,
                        (url, title, artist, file_path, platform)
                    )
                self.conn.commit()
                logger.debug(f"✓ Registrada descarga: {artist} - {title}")
            except sqlite3.Error as e:
                logger.error(f"Error registrando descarga: {e}")

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

        Args:
            url: URL de SoundCloud
            title: Título de la canción
            artist: Nombre del artista
            track_id: ID del track en SoundCloud
            duration_ms: Duración en milisegundos
            artwork_url: URL de la portada
            genre: Género
            created_at: Fecha de creación
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

    def log_sync(self, new: int, skipped: int, errors: int):
        """
        Registra un evento de sincronización.

        Args:
            new: Cantidad de canciones descargadas
            skipped: Cantidad de canciones omitidas (duplicados)
            errors: Cantidad de errores en descarga
        """
        with self.lock:
            try:
                self.conn.execute(
                    """
                    INSERT INTO sync_log (new_tracks, skipped, errors)
                    VALUES (?, ?, ?)
                    """,
                    (new, skipped, errors)
                )
                self.conn.commit()
                logger.info(f"Sync log: +{new} | -{skipped} | ⚠️{errors}")
            except sqlite3.Error as e:
                logger.error(f"Error logging sync: {e}")

    def get_last_sync(self) -> dict | None:
        """
        Obtiene info de la última sincronización.

        Returns:
            {
                'synced_at': timestamp,
                'new_tracks': int,
                'skipped': int,
                'errors': int
            }
            O None si no hay sincronizaciones registradas
        """
        with self.lock:
            try:
                cursor = self.conn.execute(
                    """
                    SELECT synced_at, new_tracks, skipped, errors
                    FROM sync_log ORDER BY id DESC LIMIT 1
                    """
                )
                row = cursor.fetchone()
                if not row:
                    return None
                return {
                    "synced_at": row[0],
                    "new_tracks": row[1],
                    "skipped": row[2],
                    "errors": row[3]
                }
            except sqlite3.Error as e:
                logger.error(f"Error obteniendo último sync: {e}")
                return None

    def get_stats(self) -> dict:
        """
        Obtiene estadísticas globales del historial.

        Returns:
            {
                'total_tracks': int,
                'total_artists': int,
                'by_platform': {'soundcloud': int, 'youtube': int, ...}
            }
        """
        with self.lock:
            try:
                # Total de tracks y artistas únicos
                cursor = self.conn.execute(
                    "SELECT COUNT(*), COUNT(DISTINCT artist) FROM downloads"
                )
                total, artists = cursor.fetchone()

                # Desglose por plataforma
                cursor = self.conn.execute(
                    "SELECT platform, COUNT(*) FROM downloads GROUP BY platform"
                )
                by_platform = {row[0]: row[1] for row in cursor.fetchall()}

                return {
                    "total_tracks": total,
                    "total_artists": artists,
                    "by_platform": by_platform
                }
            except sqlite3.Error as e:
                logger.error(f"Error obteniendo stats: {e}")
                return {
                    "total_tracks": 0,
                    "total_artists": 0,
                    "by_platform": {}
                }

    def get_all_downloads(self) -> list[dict]:
        """
        Obtiene la lista completa de descargas.

        Returns:
            Lista de {url, title, artist, file_path, platform, downloaded_at}
        """
        with self.lock:
            try:
                # Intenta con local_path (esquema nuevo), fallback a file_path (viejo)
                try:
                    cursor = self.conn.execute(
                        "SELECT url, title, artist, local_path, platform, download_date "
                        "FROM downloads ORDER BY download_date DESC"
                    )
                except sqlite3.OperationalError:
                    cursor = self.conn.execute(
                        "SELECT url, title, artist, file_path, platform, downloaded_at "
                        "FROM downloads ORDER BY downloaded_at DESC"
                    )

                return [
                    {
                        "url": row[0],
                        "title": row[1],
                        "artist": row[2],
                        "file_path": row[3],
                        "platform": row[4],
                        "downloaded_at": row[5]
                    }
                    for row in cursor.fetchall()
                ]
            except sqlite3.Error as e:
                logger.error(f"Error obteniendo descargas: {e}")
                return []

    def save_likes(self, tracks: list):
        """
        Guarda likes obtenidos de SoundCloud en la DB.

        Args:
            tracks: Lista de SoundCloudTrack
        """
        with self.lock:
            try:
                # Limpiar likes antiguos primero
                self.conn.execute("DELETE FROM soundcloud_likes")

                # Guardar todos los likes nuevos
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
        """
        Carga los likes guardados en la DB.

        Returns:
            Lista de {id, url, title, artist, duration_ms, artwork_url, genre, created_at}
            O lista vacía si no hay likes guardados
        """
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
                        "id": row[0],
                        "url": row[1],
                        "title": row[2],
                        "artist": row[3],
                        "duration_ms": row[4],
                        "artwork_url": row[5],
                        "genre": row[6],
                        "created_at": row[7]
                    }
                    for row in cursor.fetchall()
                ]
                logger.info(f"✓ {len(likes)} likes cargados de DB")
                return likes
            except sqlite3.Error as e:
                logger.error(f"Error cargando likes: {e}")
                return []

    def close(self):
        """Cierra la conexión a la DB."""
        if self.conn:
            self.conn.close()
