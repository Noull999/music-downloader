"""
Orquestador principal de sincronización.
Conecta: API de SoundCloud + detector de duplicados + descargador + historial + notificaciones.
"""
import threading
import logging
import os
import re
from pathlib import Path
from typing import Callable, Optional

from .soundcloud_api import SoundCloudAPIClient, SoundCloudTrack
from .duplicate_checker import DuplicateChecker
from db.history import DownloadHistory
from notifications.notifier import Notifier

logger = logging.getLogger(__name__)


def sanitize_filename(name: str) -> str:
    """Elimina caracteres inválidos en nombres de archivo Windows."""
    name = re.sub(r'[\\/:*?"<>|]', "_", name)
    return name.strip(". ") or "Unknown"


class SyncManager:
    """
    Orquesta el proceso completo de sincronización de likes de SoundCloud.

    Workflow:
    1. Obtener likes desde API de SoundCloud
    2. Verificar cuáles son nuevos (no en historial ni carpeta local)
    3. Descargar los nuevos usando el handler existente
    4. Registrar en historial + log
    5. Notificar resultado
    """

    def __init__(
        self,
        oauth_token: str,
        client_id: str,
        download_folder: str,
        downloader,  # handler de soundcloud o youtube (con método download())
        similarity_threshold: int = 85,  # threshold para detectar duplicados (0-100)
        filename_pattern: str = "{artist} - {title}",
        subfolder_by_artist: bool = False,
    ):
        """
        Args:
            oauth_token: Token OAuth de SoundCloud (formato "OAuth 2-XXXXX...")
            client_id: Client ID de la API de SoundCloud
            download_folder: Carpeta donde guardar archivos
            downloader: Handler existente (SoundCloudHandler o similar)
                       Debe tener método: download(url, output_path, quality_preset, progress_cb)
            similarity_threshold: % de similitud para detectar duplicados (default 85)
            filename_pattern: Patrón de nombre con {artist} y {title}
            subfolder_by_artist: Si crear subcarpeta por artista
        """
        self.api = SoundCloudAPIClient(oauth_token, client_id)
        self.history = DownloadHistory()
        self.checker = DuplicateChecker(self.history, similarity_threshold)
        self.notifier = Notifier()
        self.download_folder = download_folder
        self.downloader = downloader
        self.filename_pattern = filename_pattern
        self.subfolder_by_artist = subfolder_by_artist

        self._stop_event = threading.Event()
        self._is_syncing = False

    def _build_output_path(self, artist: str, title: str) -> str:
        """Construye el output_path con patrón de nombre y artista."""
        safe_artist = sanitize_filename(artist)
        safe_title = sanitize_filename(title)

        folder = (
            os.path.join(self.download_folder, safe_artist)
            if self.subfolder_by_artist
            else self.download_folder
        )
        os.makedirs(folder, exist_ok=True)

        try:
            base_name = self.filename_pattern.format(artist=safe_artist, title=safe_title)
        except KeyError:
            base_name = f"{safe_artist} - {safe_title}"
        base_name = sanitize_filename(base_name)

        return os.path.join(folder, base_name)

    # ────────────────────────────────────────────────────────────────── #
    # Sincronización principal                                            #
    # ────────────────────────────────────────────────────────────────── #

    def validate_credentials(self) -> bool:
        """
        Verifica que las credenciales son válidas.

        Returns:
            True si credenciales OK, False si no

        Raises:
            ValueError si token inválido/expirado
            ConnectionError si error de API
        """
        try:
            user_info = self.api.validate_credentials()
            logger.info(f"✅ Credenciales válidas para: {user_info['username']}")
            return True
        except (ValueError, ConnectionError) as e:
            logger.error(f"Error validando credenciales: {e}")
            self.notifier.notify_error("Error de autenticación", str(e))
            raise

    def get_new_tracks_fast(self, all_likes: list) -> tuple[list, list]:
        """
        Versión rápida: filtra nuevos usando SOLO el historial de URLs.
        No busca en carpeta (no hace fuzzy matching).
        Útil para cuando ya has verificado antes.

        Args:
            all_likes: Lista de SoundCloudTrack

        Returns:
            (tracks_nuevos, tracks_duplicados)
        """
        new_tracks = []
        duplicates = []

        for track in all_likes:
            if self.history.is_downloaded(track.url):
                duplicates.append((track, "En historial de descargas"))
            else:
                new_tracks.append(track)

        logger.info(f"Filtrado rápido: {len(new_tracks)} nuevas | {len(duplicates)} descargadas")
        return new_tracks, duplicates

    def load_saved_likes(self) -> list:
        """
        Carga los likes guardados en la DB (sin necesidad de verificar en SoundCloud).
        Útil para mostrar likes guardados al iniciar sin esperar a la API.

        Returns:
            Lista de SoundCloudTrack o lista vacía si no hay guardados
        """
        likes_data = self.history.load_likes()
        if not likes_data:
            logger.info("No hay likes guardados en la DB")
            return []

        # Convertir dicts a SoundCloudTrack
        tracks = [
            SoundCloudTrack(
                id=like["id"],
                url=like["url"],
                title=like["title"],
                artist=like["artist"],
                duration_ms=like["duration_ms"],
                artwork_url=like["artwork_url"],
                genre=like["genre"],
                created_at=like["created_at"]
            )
            for like in likes_data
        ]
        logger.info(f"✓ Cargados {len(tracks)} likes guardados de la DB")
        return tracks

    def scan_only(
        self,
        progress_callback: Optional[Callable[[int, str], None]] = None
    ) -> dict:
        """
        Solo verifica cuáles son duplicados SIN descargar nada.
        Útil para revisar qué tienes vs qué hay nuevo.

        Returns:
            {
                'new': int,          # Canciones nuevas para descargar
                'skipped': int,      # Duplicados encontrados
                'tracks': list,      # SoundCloudTrack nuevas
                'duplicates': list,  # (track, reason) de duplicados
            }
        """
        if self._is_syncing:
            logger.warning("Sincronización ya en progreso")
            return {'new': 0, 'skipped': 0, 'tracks': [], 'duplicates': []}

        self._is_syncing = True
        self._stop_event.clear()

        results = {
            'new': 0,
            'skipped': 0,
            'tracks': [],
            'duplicates': []
        }

        try:
            if progress_callback:
                progress_callback(0, "Obteniendo tus likes de SoundCloud...")

            logger.info("Descargando lista de likes...")
            all_likes = self.api.get_likes()

            if not all_likes:
                logger.warning("No se encontraron likes")
                if progress_callback:
                    progress_callback(100, "No hay likes en tu cuenta")
                return results

            if progress_callback:
                progress_callback(50, f"Verificando {len(all_likes)} canciones...")

            logger.info(f"Verificando {len(all_likes)} canciones...")
            new_tracks, duplicates = self.checker.get_new_tracks(
                all_likes, self.download_folder
            )

            results['new'] = len(new_tracks)
            results['skipped'] = len(duplicates)
            results['tracks'] = new_tracks
            results['duplicates'] = duplicates

            # Guardar todos los likes en la DB para no tener que verificar de nuevo
            self.history.save_likes(all_likes)

            if progress_callback:
                progress_callback(
                    100,
                    f"✓ Verificación completa: {len(new_tracks)} nuevas, "
                    f"{len(duplicates)} ya tienes"
                )

            logger.info(
                f"Resultado: {len(new_tracks)} nuevas | {len(duplicates)} duplicadas"
            )

            return results

        finally:
            self._is_syncing = False

    def sync_once(
        self,
        progress_callback: Optional[Callable[[int, str], None]] = None
    ) -> dict:
        """
        Ejecuta una sincronización completa.

        Args:
            progress_callback: Función(porcentaje: int, mensaje: str)
                             Para actualizar la GUI durante el proceso

        Returns:
            {
                'new': int,          # Canciones descargadas
                'skipped': int,      # Duplicados omitidos
                'errors': int,       # Errores en descarga
                'tracks': list,      # SoundCloudTrack descargadas
                'duplicates': list,  # (track, reason) de duplicados
            }
        """
        if self._is_syncing:
            logger.warning("Sincronización ya en progreso")
            return {
                'new': 0, 'skipped': 0, 'errors': 0,
                'tracks': [], 'duplicates': []
            }

        self._is_syncing = True
        self._stop_event.clear()

        results = {
            'new': 0,
            'skipped': 0,
            'errors': 0,
            'tracks': [],
            'duplicates': []
        }

        try:
            # PASO 1: Obtener todos los likes de SoundCloud
            if progress_callback:
                progress_callback(0, "Obteniendo tus likes de SoundCloud...")

            logger.info("Descargando lista de likes...")
            all_likes = self.api.get_likes()

            if not all_likes:
                logger.warning("No se encontraron likes")
                if progress_callback:
                    progress_callback(100, "No hay likes en tu cuenta")
                return results

            if progress_callback:
                progress_callback(
                    10,
                    f"Encontrados {len(all_likes)} likes. "
                    f"Verificando duplicados..."
                )

            # Guardar todos los likes en la DB para no tener que verificar de nuevo
            self.history.save_likes(all_likes)

            # PASO 2: Separar nuevos de duplicados
            logger.info(f"Verificando {len(all_likes)} canciones...")
            new_tracks, duplicates = self.checker.get_new_tracks(
                all_likes, self.download_folder
            )

            results['skipped'] = len(duplicates)
            results['duplicates'] = duplicates

            if not new_tracks:
                logger.info("No hay canciones nuevas para descargar")
                if progress_callback:
                    progress_callback(
                        100,
                        f"✓ Completado: {len(duplicates)} ya descargadas"
                    )
                self.notifier.notify_sync_complete(0, results['skipped'], 0)
                return results

            if progress_callback:
                progress_callback(
                    15,
                    f"Listas para descargar: {len(new_tracks)} nuevas, "
                    f"{len(duplicates)} omitidas"
                )

            # PASO 3: Descargar las nuevas
            logger.info(f"Descargando {len(new_tracks)} canciones nuevas...")
            total = len(new_tracks)

            for i, track in enumerate(new_tracks):
                if self._stop_event.is_set():
                    logger.info("Sincronización cancelada por el usuario")
                    break

                if progress_callback:
                    pct = 15 + int((i / total) * 80)
                    progress_callback(
                        pct,
                        f"Descargando: {track.artist} - {track.title}"
                    )

                try:
                    output_path = self._build_output_path(track.artist, track.title)
                    file_path = self.downloader.download(
                        track.url,
                        output_path,
                        quality_preset={
                            "sc_format": "bestaudio/best",
                            "yt_format": "bestaudio/best",
                            "convert_to": "mp3",
                            "bitrate": "320"
                        },
                        progress_callback=lambda p: None,  # No mostrar progreso individual
                        cancel_check=lambda: self._stop_event.is_set()
                    )

                    # Registrar en historial
                    self.history.mark_downloaded(
                        track.url,
                        track.title,
                        track.artist,
                        file_path,
                        platform="soundcloud"
                    )

                    results['new'] += 1
                    results['tracks'].append(track)
                    logger.info(f"✓ Descargada: {track.artist} - {track.title}")

                except Exception as e:
                    # Si fue cancelado por el usuario, detener loop sin contar como error
                    if "cancelled" in str(e).lower():
                        logger.info(f"Descarga cancelada por el usuario")
                        break
                    results['errors'] += 1
                    logger.error(
                        f"Error descargando {track.artist} - {track.title}: {e}"
                    )

            # PASO 4: Log y notificación final
            if progress_callback:
                progress_callback(
                    95,
                    f"Finalizando: +{results['new']} ✓ "
                    f"{results['skipped']} ⏭️ {results['errors']} ⚠️"
                )

            self.history.log_sync(
                results['new'],
                results['skipped'],
                results['errors']
            )

            self.notifier.notify_sync_complete(
                results['new'],
                results['skipped'],
                results['errors']
            )

            logger.info(
                f"Sincronización completada: "
                f"+{results['new']} | "
                f"-{results['skipped']} | "
                f"⚠️{results['errors']}"
            )

            if progress_callback:
                progress_callback(100, "✓ Sincronización completada")

            return results

        except Exception as e:
            logger.error(f"Error durante sincronización: {e}")
            self.notifier.notify_error("Error de sincronización", str(e))
            raise

        finally:
            self._is_syncing = False

    def sync_from_index(
        self,
        start_index: int = 0,
        progress_callback: Optional[Callable[[int, str], None]] = None
    ) -> dict:
        """
        Descarga las canciones nuevas comenzando desde un índice específico.
        Útil para reanudar descargas interrumpidas.

        Args:
            start_index: Índice (0-based) desde donde comenzar.
                        0 = desde el principio, 1 = desde la segunda, etc.
            progress_callback: Función(porcentaje, mensaje)

        Returns:
            Mismo formato que sync_once()
        """
        if self._is_syncing:
            logger.warning("Sincronización ya en progreso")
            return {'new': 0, 'skipped': 0, 'errors': 0,
                    'tracks': [], 'duplicates': []}

        self._is_syncing = True
        self._stop_event.clear()

        results = {
            'new': 0,
            'skipped': 0,
            'errors': 0,
            'tracks': [],
            'duplicates': []
        }

        try:
            # Intentar cargar likes guardados de la DB para evitar re-verificar
            if progress_callback:
                progress_callback(0, "Cargando likes guardados...")

            logger.info("Intentando cargar likes de la DB...")
            saved_likes = self.load_saved_likes()

            if saved_likes:
                all_likes = saved_likes
                logger.info(f"✓ Usando {len(all_likes)} likes guardados de la DB (sin re-verificar)")
            else:
                logger.info("No hay likes en DB, obteniendo de SoundCloud...")
                if progress_callback:
                    progress_callback(0, "Obteniendo tus likes de SoundCloud...")

                all_likes = self.api.get_likes()

            if not all_likes:
                logger.warning("No se encontraron likes")
                return results

            # Usar filtrado rápido (solo historial) en lugar de búsqueda fuzzy en carpeta
            if progress_callback:
                progress_callback(10, f"Filtrando {len(all_likes)} canciones...")

            logger.info(f"Filtrando {len(all_likes)} canciones (rápido, sin búsqueda en carpeta)...")
            new_tracks, duplicates = self.get_new_tracks_fast(all_likes)

            results['duplicates'] = duplicates
            results['skipped'] = len(duplicates)

            if not new_tracks:
                logger.info("No hay canciones nuevas")
                if progress_callback:
                    progress_callback(100, f"Sin canciones nuevas ({len(duplicates)} ya tienes)")
                return results

            # Ajustar índice de inicio
            if start_index < 0:
                start_index = 0
            if start_index >= len(new_tracks):
                logger.warning(f"Índice {start_index} fuera de rango (total: {len(new_tracks)})")
                if progress_callback:
                    progress_callback(100, f"Índice inválido (máx: {len(new_tracks)-1})")
                return results

            if start_index > 0:
                logger.info(f"Comenzando desde canción #{start_index + 1}")
                if progress_callback:
                    progress_callback(
                        15,
                        f"Saltando primeras {start_index}. Comenzando desde #{start_index + 1}"
                    )

            # Descargar desde el índice especificado
            total_to_download = len(new_tracks) - start_index

            if total_to_download <= 0:
                logger.info("No hay canciones para descargar desde este índice")
                if progress_callback:
                    progress_callback(100, "No hay canciones para descargar")
                return results

            for i in range(start_index, len(new_tracks)):
                if self._stop_event.is_set():
                    logger.info("Sincronización cancelada por el usuario")
                    break

                track = new_tracks[i]
                progress_idx = i - start_index

                if progress_callback:
                    pct = 15 + int((progress_idx / total_to_download) * 80)
                    progress_callback(
                        pct,
                        f"[{progress_idx + 1}/{total_to_download}] "
                        f"Descargando: {track.artist} - {track.title}"
                    )

                try:
                    output_path = self._build_output_path(track.artist, track.title)
                    file_path = self.downloader.download(
                        track.url,
                        output_path,
                        quality_preset={"format": "best"},
                        progress_callback=lambda p: None,
                        cancel_check=lambda: self._stop_event.is_set()
                    )

                    self.history.mark_downloaded(
                        track.url,
                        track.title,
                        track.artist,
                        file_path,
                        platform="soundcloud"
                    )

                    results['new'] += 1
                    results['tracks'].append(track)
                    logger.info(f"✓ Descargada: {track.artist} - {track.title}")

                except Exception as e:
                    # Si fue cancelado por el usuario, detener loop sin contar como error
                    if "cancelled" in str(e).lower():
                        logger.info(f"Descarga cancelada por el usuario")
                        break
                    results['errors'] += 1
                    logger.error(f"Error descargando {track.artist} - {track.title}: {e}")

            if progress_callback:
                progress_callback(
                    95,
                    f"Finalizando: +{results['new']} ✓ "
                    f"{results['skipped']} ⏭️ {results['errors']} ⚠️"
                )

            self.history.log_sync(
                results['new'],
                results['skipped'],
                results['errors']
            )

            self.notifier.notify_sync_complete(
                results['new'],
                results['skipped'],
                results['errors']
            )

            logger.info(
                f"Sincronización desde índice {start_index} completada: "
                f"+{results['new']} | -{results['skipped']} | ⚠️{results['errors']}"
            )

            if progress_callback:
                progress_callback(100, "✓ Descarga completada")

            return results

        finally:
            self._is_syncing = False

    def sync_recent(
        self,
        count: int = 10,
        progress_callback: Optional[Callable[[int, str], None]] = None
    ) -> dict:
        """
        Sincronización rápida: obtiene solo los N likes más recientes.
        Útil para polling periódico.

        Args:
            count: Cantidad de likes recientes a verificar
            progress_callback: Función(porcentaje, mensaje)

        Returns:
            Mismo formato que sync_once()
        """
        if self._is_syncing:
            return {
                'new': 0, 'skipped': 0, 'errors': 0,
                'tracks': [], 'duplicates': []
            }

        self._is_syncing = True
        self._stop_event.clear()

        results = {
            'new': 0, 'skipped': 0, 'errors': 0,
            'tracks': [], 'duplicates': []
        }

        try:
            if progress_callback:
                progress_callback(0, f"Obteniendo últimos {count} likes...")

            recent_likes = self.api.get_recent_likes(count)

            if not recent_likes:
                return results

            new_tracks, duplicates = self.checker.get_new_tracks(
                recent_likes, self.download_folder
            )

            results['skipped'] = len(duplicates)
            results['duplicates'] = duplicates

            # Descargar los nuevos (mismo proceso que sync_once)
            total = len(new_tracks)
            for i, track in enumerate(new_tracks):
                if self._stop_event.is_set():
                    break

                if progress_callback:
                    pct = int((i / total) * 100) if total > 0 else 0
                    progress_callback(pct, f"Descargando: {track.title}")

                try:
                    output_path = self._build_output_path(track.artist, track.title)
                    file_path = self.downloader.download(
                        track.url,
                        output_path,
                        quality_preset={
                            "sc_format": "bestaudio/best",
                            "yt_format": "bestaudio/best",
                            "convert_to": "mp3",
                            "bitrate": "320"
                        },
                        progress_callback=None
                    )
                    self.history.mark_downloaded(
                        track.url, track.title, track.artist, file_path
                    )
                    results['new'] += 1
                    results['tracks'].append(track)
                except Exception as e:
                    results['errors'] += 1
                    logger.error(f"Error en sync_recent: {e}")

            return results

        finally:
            self._is_syncing = False

    def stop(self):
        """Detiene la sincronización en curso."""
        logger.info("Deteniendo sincronización...")
        self._stop_event.set()

    def is_syncing(self) -> bool:
        """Retorna True si hay sincronización en progreso."""
        return self._is_syncing

    # ────────────────────────────────────────────────────────────────── #
    # Stats y estado                                                      #
    # ────────────────────────────────────────────────────────────────── #

    def get_history_stats(self) -> dict:
        """Obtiene estadísticas del historial de descargas."""
        return self.history.get_stats()

    def get_last_sync_info(self) -> dict | None:
        """Obtiene info de la última sincronización."""
        return self.history.get_last_sync()

    def sync_filesystem_to_db(self) -> dict:
        """
        Sincroniza archivos locales con la BD.
        Busca archivos de audio que NO están en el historial y los agrega.
        Útil para recuperar archivos descargados antes de usar la app.

        Returns:
            {
                'added': int,       # Archivos agregados al historial
                'already_tracked': int,  # Archivos ya en el historial
                'total_found': int  # Total de archivos de audio encontrados
            }
        """
        if not os.path.exists(self.download_folder):
            logger.warning(f"Carpeta no existe: {self.download_folder}")
            return {'added': 0, 'already_tracked': 0, 'total_found': 0}

        logger.info("Sincronizando filesystem con BD...")
        audio_extensions = {'.mp3', '.m4a', '.flac', '.wav', '.ogg', '.opus', '.aac'}
        added = 0
        already_tracked = 0
        total = 0

        try:
            for file_path in Path(self.download_folder).rglob('*'):
                if not file_path.is_file():
                    continue
                if file_path.suffix.lower() not in audio_extensions:
                    continue

                total += 1
                filename = file_path.stem
                artist_dir = file_path.parent.name

                # Verificar si ya está en historial
                existing = self.history.conn.execute(
                    "SELECT 1 FROM downloads WHERE file_path = ?",
                    (str(file_path),)
                ).fetchone()

                if existing:
                    already_tracked += 1
                    continue

                # Agregar a historial
                try:
                    self.history.mark_downloaded(
                        url=f"local://{file_path}",
                        title=filename,
                        artist=artist_dir,
                        file_path=str(file_path),
                        platform="local"
                    )
                    added += 1
                    logger.debug(f"Agregado al historial: {filename}")
                except Exception as e:
                    logger.warning(f"Error agregando {filename} al historial: {e}")

        except (OSError, PermissionError) as e:
            logger.error(f"Error explorando carpeta: {e}")

        logger.info(
            f"Sync filesystem: +{added} archivos agregados, "
            f"{already_tracked} ya rastreados, {total} total encontrados"
        )

        return {
            'added': added,
            'already_tracked': already_tracked,
            'total_found': total
        }

    def get_likes_with_status(self) -> list[dict]:
        """
        Obtiene todos los likes guardados con su estado de descarga.

        Returns:
            Lista de {
                'id': int,
                'url': str,
                'title': str,
                'artist': str,
                'downloaded': bool,
                'file_path': str | None,
                'created_at': str,
                'genre': str | None
            }
        """
        likes = self.history.load_likes()
        downloads = {d['url']: d for d in self.history.get_all_downloads()}

        result = []
        for like in likes:
            download_info = downloads.get(like['url'])
            result.append({
                'id': like['id'],
                'url': like['url'],
                'title': like['title'],
                'artist': like['artist'],
                'downloaded': download_info is not None,
                'file_path': download_info['file_path'] if download_info else None,
                'created_at': like['created_at'],
                'genre': like['genre'],
                'duration_ms': like['duration_ms'],
                'artwork_url': like['artwork_url']
            })

        return result
