"""
Orquestador principal de sincronización.
Conecta: API de SoundCloud + detector de duplicados + descargador + historial + notificaciones.
"""
import threading
import logging
import os
import re
import shutil
from pathlib import Path
from typing import Callable, Optional

from .soundcloud_api import SoundCloudAPIClient, SoundCloudTrack
from .duplicate_checker import DuplicateChecker
from . import match_utils
from analysis import fingerprint as audio_fingerprint
from db.history import DownloadHistory
from notifications.notifier import Notifier
from quality.post_processor import PostProcessor
from quality.presets import DEFAULT_PRESET, get_preset

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
        similarity_threshold: int = match_utils.MATCH_THRESHOLD,
        filename_pattern: str = "{artist} - {title}",
        subfolder_by_artist: bool = False,
        activity_log_callback: Optional[Callable[[str], None]] = None,
        library_folders: Optional[list] = None,
        track_event_callback: Optional[Callable[[str, object, str], None]] = None,
        analyze_audio: bool = False,
        key_format: str = "camelot",
        fingerprint_check: bool = True,
        quality_preset: str = DEFAULT_PRESET,
        post_options: Optional[dict] = None,
    ):
        """
        Args:
            oauth_token: Token OAuth de SoundCloud (formato "OAuth 2-XXXXX...")
            client_id: Client ID de la API de SoundCloud
            download_folder: Carpeta donde guardar archivos
            downloader: Handler existente (SoundCloudHandler o similar)
                       Debe tener método: download(url, output_path, quality_preset, progress_cb)
            similarity_threshold: % de similitud para detectar duplicados,
                       sobre títulos ya normalizados (ver sync/match_utils.py)
            filename_pattern: Patrón de nombre con {artist} y {title}
            subfolder_by_artist: Si crear subcarpeta por artista
            activity_log_callback: Función(mensaje: str) para logging en tiempo real a ActivityPanel
            library_folders: Carpetas extra donde ya tenés música, además de
                       download_folder, para no re-descargar lo que ya existe
            track_event_callback: Función(evento, track, detalle) llamada por
                       cada canción de la sincronización, con evento en
                       ('start', 'done', 'error'). Permite a la GUI mostrar
                       la cola real; sin ella la sync solo reporta un
                       porcentaje global.
            analyze_audio: Si detectar BPM y tonalidad (Camelot) de cada
                       canción descargada, vía librosa (opcional, ~2s/track)
            key_format: "camelot" (9A, 5B...) o "musical" (Gm, D#...)
            fingerprint_check: Si comparar audio real (Chromaprint) antes de
                       descargar una canción que el matching por nombre NO
                       marcó como duplicada. Atrapa casos que el nombre solo
                       no puede: mismo tema con nombre de archivo muy
                       distinto. Ver analysis/fingerprint.py.
            quality_preset: Clave del preset de calidad (ver quality/presets.py).
                       Antes la sync ignoraba la elección del usuario y bajaba
                       siempre MP3 320.
            post_options: Opciones de post-proceso (normalize_volume,
                       remove_silence, embed_artwork, embed_metadata). Antes
                       estaban hardcodeadas, así que "normalizar volumen" y
                       "eliminar silencios" no tenían efecto en la sync.
        """
        self.api = SoundCloudAPIClient(oauth_token, client_id)
        self.history = DownloadHistory()
        self.checker = DuplicateChecker(
            self.history, similarity_threshold, library_folders=library_folders
        )
        self.notifier = Notifier()
        self.download_folder = download_folder
        self.downloader = downloader
        self.filename_pattern = filename_pattern
        self.subfolder_by_artist = subfolder_by_artist
        self.activity_log_callback = activity_log_callback
        self.track_event_callback = track_event_callback
        self.analyze_audio = analyze_audio
        self.key_format = key_format
        self.fingerprint_check = fingerprint_check
        self.quality_preset = quality_preset
        self.post_options = dict(post_options or {})
        self.library_folders = list(library_folders or [])
        self.oauth_token = oauth_token
        self._fingerprint_index: Optional[audio_fingerprint.LibraryFingerprintIndex] = None

        self._stop_event = threading.Event()
        self._is_syncing = False

    def _emit_track(self, event: str, track, detail: str = "") -> None:
        """Notifica el estado de una canción concreta a la GUI, si hay callback."""
        if not self.track_event_callback:
            return
        try:
            self.track_event_callback(event, track, detail)
        except Exception:
            logger.exception("Error en track_event_callback (%s)", event)

    @staticmethod
    def _is_permanent_error(error: str) -> bool:
        """
        Distingue fallos que nunca van a funcionar (no tiene sentido
        reintentarlos en cada sync) de los transitorios de red.
        """
        e = (error or "").lower()
        return any(s in e for s in (
            "drm",
            "geo restriction",
            "not available from your location",
            "video unavailable",
            "track not found",
            "410",
            "404",
            "private",
            "removed",
            "copyright",
        ))

    def _record_failure(self, track, error: str) -> None:
        """Guarda el fallo para no reintentarlo indefinidamente."""
        permanent = self._is_permanent_error(error)
        try:
            self.history.mark_failed(
                track.url, track.title, track.artist, error, permanent=permanent
            )
        except Exception:
            logger.exception("No se pudo registrar la descarga fallida")

    def _filter_unrecoverable(self, tracks: list) -> tuple[list, list]:
        """
        Aparta las canciones que ya sabemos que no se pueden bajar (DRM,
        bloqueo geográfico, o demasiados intentos fallidos).

        Returns:
            (tracks_a_intentar, [(track, motivo), ...])
        """
        try:
            skippable = self.history.get_skippable_failures()
        except Exception:
            logger.exception("No se pudieron leer las descargas fallidas")
            return tracks, []

        if not skippable:
            return tracks, []

        pending, skipped = [], []
        for t in tracks:
            reason = skippable.get(t.url)
            if reason:
                skipped.append((t, reason))
            else:
                pending.append(t)

        if skipped:
            logger.info("Omitidas %d canciones que fallaron antes", len(skipped))
        return pending, skipped

    def _ensure_fingerprint_index(self) -> audio_fingerprint.LibraryFingerprintIndex:
        if self._fingerprint_index is None:
            self._fingerprint_index = audio_fingerprint.LibraryFingerprintIndex()
            folders = [self.download_folder, *self.library_folders]
            self._fingerprint_index.build(folders)
        return self._fingerprint_index

    def _fingerprint_precheck(self, track: "SoundCloudTrack") -> Optional[tuple[str, float]]:
        """
        Última red de seguridad antes de descargar: si el matching por
        nombre no encontró nada, compara el audio real (huella Chromaprint
        de un preview de 30s) contra toda la biblioteca. Atrapa el caso
        que el nombre solo no puede: mismo tema, nombre de archivo muy
        distinto. Nunca bloquea la descarga si algo falla (fpcalc ausente,
        preview no disponible, etc): simplemente no encuentra nada.

        Returns:
            (ruta_local, similitud) si encontró coincidencia, si no None.
        """
        index = self._ensure_fingerprint_index()
        if len(index) == 0:
            return None

        import tempfile
        tmp_dir = tempfile.mkdtemp(prefix="mdl_fp_")
        preview_base = os.path.join(tmp_dir, "preview")
        try:
            preview_path = audio_fingerprint.download_preview(
                track.url, preview_base, oauth_token=self.oauth_token
            )
            if not preview_path:
                return None
            fp = audio_fingerprint.fingerprint_file(preview_path)
            if not fp:
                return None
            return index.find_best_match(fp)
        except Exception:
            logger.exception("Error en pre-chequeo de huella de audio (%s)", track.url)
            return None
        finally:
            try:
                shutil.rmtree(tmp_dir, ignore_errors=True)
            except Exception:
                pass

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

    def _post_process(self, file_path: str, track: "SoundCloudTrack") -> None:
        """Embebe carátula y metadatos en el archivo descargado vía mutagen."""
        if not file_path or not os.path.exists(file_path):
            return
        try:
            pp = PostProcessor({
                "embed_artwork": self.post_options.get("embed_artwork", True),
                "embed_metadata": self.post_options.get("embed_metadata", True),
                "normalize_volume": self.post_options.get("normalize_volume", False),
                "remove_silence": self.post_options.get("remove_silence", False),
                "analyze_audio": self.analyze_audio, "key_format": self.key_format,
            })
            pp.process(file_path, {"title": track.title, "artist": track.artist,
                                   "album": "", "year": ""}, track.artwork_url or "")
        except Exception as e:
            logger.warning("Error en post-proceso de %s: %s", track.title, e)

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

            # Apartar lo que ya sabemos que no se puede bajar (DRM, geo,
            # reintentos agotados) para no chocar con lo mismo cada vez.
            new_tracks, unrecoverable = self._filter_unrecoverable(new_tracks)
            duplicates = duplicates + unrecoverable

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

                if self.fingerprint_check:
                    match = self._fingerprint_precheck(track)
                    if match:
                        local_path, score = match
                        reason = f"Duplicado por audio ({score:.0%} de similitud): {Path(local_path).name}"
                        logger.info("✓ %s: %s", reason, track.url)
                        self.history.mark_downloaded(
                            track.url, track.title, track.artist, local_path,
                            platform="soundcloud",
                        )
                        self.history.mark_like_downloaded(
                            url=track.url, title=track.title, artist=track.artist,
                            track_id=track.id, duration_ms=track.duration_ms,
                        )
                        results['skipped'] += 1
                        results['duplicates'].append((track, reason))
                        self._emit_track("done", track, reason)
                        continue

                self._emit_track("start", track)

                try:
                    output_path = self._build_output_path(track.artist, track.title)
                    file_path = self.downloader.download(
                        track.url,
                        output_path,
                        quality_preset=get_preset(self.quality_preset),
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
                    # Also register in soundcloud_likes table
                    self.history.mark_like_downloaded(
                        url=track.url,
                        title=track.title,
                        artist=track.artist,
                        track_id=track.id,
                        duration_ms=track.duration_ms,
                        artwork_url=track.artwork_url,
                        genre=track.genre,
                        created_at=track.created_at
                    )
                    self._post_process(file_path, track)

                    results['new'] += 1
                    results['tracks'].append(track)
                    msg = f"✓ Descargada: {track.artist} - {track.title}"
                    logger.info(msg)
                    if self.activity_log_callback:
                        self.activity_log_callback(msg)
                    self._emit_track("done", track, file_path)

                except Exception as e:
                    # Si fue cancelado por el usuario, detener loop sin contar como error
                    if "cancelled" in str(e).lower():
                        logger.info(f"Descarga cancelada por el usuario")
                        self._emit_track("cancelled", track)
                        break
                    results['errors'] += 1
                    logger.error(
                        f"Error descargando {track.artist} - {track.title}: {e}"
                    )
                    self._record_failure(track, str(e))
                    self._emit_track("error", track, str(e))

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
            # Los archivos recién bajados deben contar como duplicados en la
            # próxima verificación.
            self.checker.invalidate_index()

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

            new_tracks, unrecoverable = self._filter_unrecoverable(new_tracks)
            duplicates = duplicates + unrecoverable

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
                self._emit_track("start", track)

                try:
                    output_path = self._build_output_path(track.artist, track.title)
                    file_path = self.downloader.download(
                        track.url,
                        output_path,
                        quality_preset=get_preset(self.quality_preset),
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
                    self._post_process(file_path, track)

                    results['new'] += 1
                    results['tracks'].append(track)
                    logger.info(f"✓ Descargada: {track.artist} - {track.title}")
                    self._emit_track("done", track, file_path)

                except Exception as e:
                    # Si fue cancelado por el usuario, detener loop sin contar como error
                    if "cancelled" in str(e).lower():
                        logger.info(f"Descarga cancelada por el usuario")
                        self._emit_track("cancelled", track)
                        break
                    results['errors'] += 1
                    logger.error(f"Error descargando {track.artist} - {track.title}: {e}")
                    self._record_failure(track, str(e))
                    self._emit_track("error", track, str(e))

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
            self.checker.invalidate_index()

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

            new_tracks, unrecoverable = self._filter_unrecoverable(new_tracks)
            duplicates = duplicates + unrecoverable

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
                self._emit_track("start", track)

                try:
                    output_path = self._build_output_path(track.artist, track.title)
                    file_path = self.downloader.download(
                        track.url,
                        output_path,
                        quality_preset=get_preset(self.quality_preset),
                        progress_callback=None
                    )
                    self.history.mark_downloaded(
                        track.url, track.title, track.artist, file_path
                    )
                    # Also register in soundcloud_likes table
                    self.history.mark_like_downloaded(
                        url=track.url,
                        title=track.title,
                        artist=track.artist,
                        track_id=track.id,
                        duration_ms=track.duration_ms,
                        artwork_url=track.artwork_url,
                        genre=track.genre,
                        created_at=track.created_at
                    )
                    self._post_process(file_path, track)
                    results['new'] += 1
                    results['tracks'].append(track)
                    msg = f"⬇ Descargando: {track.artist} - {track.title}"
                    if self.activity_log_callback:
                        self.activity_log_callback(msg)
                    self._emit_track("done", track, file_path)
                except Exception as e:
                    results['errors'] += 1
                    msg = f"✗ Error: {track.artist} - {track.title}"
                    if self.activity_log_callback:
                        self.activity_log_callback(msg)
                    logger.error(f"Error en sync_recent: {e}")
                    self._record_failure(track, str(e))
                    self._emit_track("error", track, str(e))

            # Log final con resultados precisos
            logger.info(
                f"✓ Sincronización reciente completada: "
                f"+{results['new']} descargadas | "
                f"-{results['skipped']} duplicadas | "
                f"!{results['errors']} errores"
            )
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
            # Usar glob en lugar de rglob para evitar cuelgues (buscar solo 2 niveles)
            all_files = list(Path(self.download_folder).glob('*'))
            all_files.extend(Path(self.download_folder).glob('*/*'))

            for file_path in all_files:
                if not file_path.is_file():
                    continue
                if file_path.suffix.lower() not in audio_extensions:
                    continue

                total += 1
                filename = file_path.stem
                artist_dir = file_path.parent.name

                # Verificar si ya está en historial (con lock)
                try:
                    with self.history.lock:
                        existing = self.history.conn.execute(
                            "SELECT 1 FROM sync_downloads WHERE file_path = ?",
                            (str(file_path),)
                        ).fetchone()
                except Exception as e:
                    logger.warning(f"Error consultando historial para {filename}: {e}")
                    continue

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
                'downloaded_at': str | None,
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
                'downloaded_at': download_info['downloaded_at'] if download_info else None,
                'created_at': like['created_at'],
                'genre': like['genre'],
                'duration_ms': like['duration_ms'],
                'artwork_url': like['artwork_url']
            })

        return result
