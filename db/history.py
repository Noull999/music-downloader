"""
Historial de descargas en SQLite, usado por el flujo de Sincronizar
(SyncManager) para saber qué likes de SoundCloud ya se bajaron y para
reconciliar archivos locales existentes (sync_filesystem_to_db).

Vive en el mismo archivo .db que db/history_manager.py (HistoryManager,
usado por el flujo principal de "pegar link"), pero en tablas con
nombres propios: ambas clases usaban antes una tabla "downloads" con
esquemas distintos, y como comparten el mismo archivo SQLite, la que
se inicializaba primero "ganaba" el esquema y dejaba a la otra
escribiendo en columnas que no existían (fallaba en silencio, o
lanzaba sqlite3.OperationalError en las consultas crudas). Por eso
esta clase usa "sync_downloads", no "downloads".
"""
import sqlite3
import threading
import logging
from pathlib import Path
from datetime import datetime
from typing import Optional

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
                CREATE TABLE IF NOT EXISTS sync_downloads (
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
                    tags        TEXT,
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

                -- Descargas que fallaron. Sin esto, una canción con DRM o
                -- bloqueo geográfico se reintenta en cada sincronización,
                -- para siempre, y ensucia el conteo de errores.
                CREATE TABLE IF NOT EXISTS failed_downloads (
                    url          TEXT PRIMARY KEY,
                    title        TEXT,
                    artist       TEXT,
                    error        TEXT,
                    permanent    INTEGER DEFAULT 0,
                    attempts     INTEGER DEFAULT 1,
                    last_attempt TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );

                CREATE INDEX IF NOT EXISTS idx_sync_downloads_platform
                    ON sync_downloads(platform);
                CREATE INDEX IF NOT EXISTS idx_sync_downloads_artist
                    ON sync_downloads(artist);
                CREATE INDEX IF NOT EXISTS idx_likes_url
                    ON soundcloud_likes(url);
            """)
            # Migración: CREATE TABLE IF NOT EXISTS no agrega columnas a una
            # tabla que ya existe, así que las bases anteriores a `tags` se
            # quedarían sin ella.
            cols = {r[1] for r in self.conn.execute(
                "PRAGMA table_info(soundcloud_likes)"
            )}
            if "tags" not in cols:
                self.conn.execute("ALTER TABLE soundcloud_likes ADD COLUMN tags TEXT")
                logger.info("Migración: columna 'tags' agregada a soundcloud_likes")
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
                    "SELECT 1 FROM sync_downloads WHERE url = ?", (url,)
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
                self.conn.execute(
                    """
                    INSERT OR REPLACE INTO sync_downloads
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

    # ────────────────────────────────────────────────────────────────── #
    # Descargas fallidas                                                   #
    # ────────────────────────────────────────────────────────────────── #

    def mark_failed(
        self,
        url: str,
        title: str,
        artist: str,
        error: str,
        permanent: bool = False,
    ) -> None:
        """
        Registra (o actualiza) una descarga fallida, acumulando el número de
        intentos para poder dejar de reintentar lo que nunca va a funcionar.
        """
        with self.lock:
            try:
                self.conn.execute(
                    """
                    INSERT INTO failed_downloads
                        (url, title, artist, error, permanent, attempts, last_attempt)
                    VALUES (?, ?, ?, ?, ?, 1, CURRENT_TIMESTAMP)
                    ON CONFLICT(url) DO UPDATE SET
                        error        = excluded.error,
                        permanent    = excluded.permanent,
                        attempts     = failed_downloads.attempts + 1,
                        last_attempt = CURRENT_TIMESTAMP
                    """,
                    (url, title, artist, error[:500], 1 if permanent else 0),
                )
                self.conn.commit()
            except sqlite3.Error as e:
                logger.error(f"Error registrando descarga fallida: {e}")

    def clear_failed(self, url: Optional[str] = None) -> int:
        """
        Olvida fallos para que se vuelvan a intentar. Sin `url`, los borra
        todos. Devuelve cuántos se borraron.
        """
        with self.lock:
            try:
                if url:
                    cur = self.conn.execute(
                        "DELETE FROM failed_downloads WHERE url = ?", (url,)
                    )
                else:
                    cur = self.conn.execute("DELETE FROM failed_downloads")
                self.conn.commit()
                return cur.rowcount
            except sqlite3.Error as e:
                logger.error(f"Error limpiando fallidas: {e}")
                return 0

    def get_failed(self) -> list[dict]:
        """Lista de descargas fallidas, las permanentes primero."""
        with self.lock:
            try:
                cursor = self.conn.execute(
                    """
                    SELECT url, title, artist, error, permanent, attempts, last_attempt
                    FROM failed_downloads
                    ORDER BY permanent DESC, last_attempt DESC
                    """
                )
                return [
                    {
                        "url": row[0],
                        "title": row[1],
                        "artist": row[2],
                        "error": row[3],
                        "permanent": bool(row[4]),
                        "attempts": row[5],
                        "last_attempt": row[6],
                    }
                    for row in cursor.fetchall()
                ]
            except sqlite3.Error as e:
                logger.error(f"Error obteniendo fallidas: {e}")
                return []

    def get_skippable_failures(self, max_attempts: int = 3) -> dict[str, str]:
        """
        URLs que no vale la pena reintentar: las de error permanente (DRM,
        bloqueo geográfico, track borrado) y las que ya se intentaron
        `max_attempts` veces sin éxito.

        Returns:
            {url: motivo_legible}
        """
        with self.lock:
            try:
                cursor = self.conn.execute(
                    """
                    SELECT url, error, permanent, attempts FROM failed_downloads
                    WHERE permanent = 1 OR attempts >= ?
                    """,
                    (max_attempts,),
                )
                out = {}
                for url, error, permanent, attempts in cursor.fetchall():
                    if permanent:
                        out[url] = f"No descargable: {error}"
                    else:
                        out[url] = f"Falló {attempts} veces: {error}"
                return out
            except sqlite3.Error as e:
                logger.error(f"Error obteniendo fallidas a omitir: {e}")
                return {}

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
                    "SELECT COUNT(*), COUNT(DISTINCT artist) FROM sync_downloads"
                )
                total, artists = cursor.fetchone()

                # Desglose por plataforma
                cursor = self.conn.execute(
                    "SELECT platform, COUNT(*) FROM sync_downloads GROUP BY platform"
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
                cursor = self.conn.execute(
                    "SELECT url, title, artist, file_path, platform, downloaded_at "
                    "FROM sync_downloads ORDER BY downloaded_at DESC"
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
                        (id, url, title, artist, duration_ms, artwork_url, genre, tags, created_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            track.id,
                            track.url,
                            track.title,
                            track.artist,
                            track.duration_ms,
                            track.artwork_url,
                            track.genre,
                            getattr(track, "tags", "") or "",
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
            Lista de {id, url, title, artist, duration_ms, artwork_url, genre,
                      tags, created_at}
            O lista vacía si no hay likes guardados
        """
        with self.lock:
            try:
                cursor = self.conn.execute(
                    """
                    SELECT id, url, title, artist, duration_ms, artwork_url, genre,
                           tags, created_at
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
                        "tags": row[7] or "",
                        "created_at": row[8]
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
