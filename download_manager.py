"""
DownloadManager: gestiona el pool de hilos de descarga.
Orquesta handlers + post-procesado + callbacks de progreso al GUI.
"""
import logging
import os
import re
import threading
from concurrent.futures import Future, ThreadPoolExecutor
from typing import Callable, Optional

from handlers.base_handler import BaseHandler
from models import TrackInfo, STATUS_DOWNLOADING, STATUS_DONE, STATUS_ERROR, STATUS_SKIP, STATUS_CANCELLED
from quality.post_processor import PostProcessor

logger = logging.getLogger(__name__)


def sanitize_filename(name: str) -> str:
    """Elimina caracteres inválidos en nombres de archivo Windows."""
    name = re.sub(r'[\\/:*?"<>|]', "_", name)
    return name.strip(". ") or "Unknown"


class DownloadManager:
    """
    ThreadPoolExecutor con soporte de pausa/cancelación individual y global.
    Todas las callbacks se invocan desde hilos secundarios — el GUI debe
    redirigirlas al hilo principal via widget.after().
    """

    def __init__(self):
        self._max_workers: int = 3
        self._executor: Optional[ThreadPoolExecutor] = None
        self._paused: bool = False
        self._pause_event = threading.Event()
        self._pause_event.set()  # set = no bloqueado; clear = pausado
        self._cancel_events: dict[str, threading.Event] = {}
        self._lock = threading.Lock()

    # ── Ciclo de vida ────────────────────────────────────────────────── #

    def start(self, max_workers: int = 3):
        self._max_workers = max_workers
        if self._executor:
            self._executor.shutdown(wait=False)
        self._executor = ThreadPoolExecutor(
            max_workers=max_workers, thread_name_prefix="dl"
        )

    def shutdown(self):
        if self._executor:
            self._executor.shutdown(wait=False)
            self._executor = None

    def set_max_workers(self, n: int):
        self._max_workers = n

    # ── Pausa / reanudación ──────────────────────────────────────────── #

    def pause_all(self):
        self._paused = True
        self._pause_event.clear()  # bloquea workers en el próximo wait()

    def resume_all(self):
        self._paused = False
        self._pause_event.set()  # desbloquea todos los workers

    @property
    def is_paused(self) -> bool:
        return self._paused

    # ── Cancelación ─────────────────────────────────────────────────── #

    def cancel_track(self, url: str):
        """Cancela descarga de una URL específica."""
        with self._lock:
            ev = self._cancel_events.get(url)
        if ev:
            ev.set()
            logger.info(f"Cancelación solicitada para: {url}")

    def cancel_all(self):
        """Cancela todas las descargas en progreso."""
        with self._lock:
            for ev in self._cancel_events.values():
                ev.set()
        logger.info("Cancelación solicitada para todas las descargas")

    # ── Envío de descarga ────────────────────────────────────────────── #

    def submit_download(
        self,
        track: TrackInfo,
        handler: BaseHandler,
        dest_folder: str,
        filename_pattern: str,
        subfolder_by_artist: bool,
        quality_preset: dict,
        post_config: dict,
        delay: float,
        on_progress: Callable[[float], None],
        on_status: Callable[[str, str], None],
        # Opcional: token OAuth para SoundCloud
        oauth_token: str = "",
    ) -> Future:
        if not self._executor:
            self.start(self._max_workers)

        cancel_event = threading.Event()
        with self._lock:
            self._cancel_events[track.url] = cancel_event

        return self._executor.submit(
            self._worker,
            track,
            handler,
            dest_folder,
            filename_pattern,
            subfolder_by_artist,
            quality_preset,
            post_config,
            delay,
            on_progress,
            on_status,
            cancel_event,
            oauth_token,
        )

    # ── Hilo de descarga ─────────────────────────────────────────────── #

    def _worker(
        self,
        track: TrackInfo,
        handler: BaseHandler,
        dest_folder: str,
        filename_pattern: str,
        subfolder_by_artist: bool,
        quality_preset: dict,
        post_config: dict,
        delay: float,
        on_progress: Callable[[float], None],
        on_status: Callable[[str, str], None],
        cancel_event: threading.Event,
        oauth_token: str,
    ):
        import time

        try:
            # Esperar si está en pausa
            self._pause_event.wait()
            if cancel_event.is_set():
                on_status(STATUS_CANCELLED, "")
                return

            # Construir ruta de salida
            safe_artist = sanitize_filename(track.artist)
            safe_title = sanitize_filename(track.title)

            folder = (
                os.path.join(dest_folder, safe_artist)
                if subfolder_by_artist
                else dest_folder
            )
            os.makedirs(folder, exist_ok=True)

            try:
                base_name = filename_pattern.format(artist=safe_artist, title=safe_title)
            except KeyError:
                base_name = f"{safe_artist} - {safe_title}"
            base_name = sanitize_filename(base_name)

            # Detectar extensión esperada según preset
            convert_to = quality_preset.get("convert_to") or "mp3"
            final_path = os.path.join(folder, base_name + f".{convert_to}")

            if os.path.exists(final_path):
                track.local_path = final_path
                on_status(STATUS_SKIP, "")
                return

            on_status(STATUS_DOWNLOADING, "")

            def cancel_check() -> bool:
                return cancel_event.is_set()

            def progress_cb(v: float):
                if not self._paused:
                    on_progress(v)

            output_path = os.path.join(folder, base_name)

            # Llamar al handler con kwargs extra según tipo
            from handlers.soundcloud_handler import SoundCloudHandler
            if isinstance(handler, SoundCloudHandler) and oauth_token:
                downloaded = handler.download(
                    track.url, output_path, quality_preset, progress_cb, cancel_check,
                    oauth_token=oauth_token,
                )
            else:
                downloaded = handler.download(
                    track.url, output_path, quality_preset, progress_cb, cancel_check
                )

            # Post-procesado (normalización, silencios)
            if downloaded and os.path.exists(downloaded):
                pp = PostProcessor(post_config)
                metadata = {
                    "title": track.title,
                    "artist": track.artist,
                    "album": track.album,
                    "year": track.year,
                }
                pp.process(downloaded, metadata, track.thumbnail_url)
                track.local_path = downloaded
                on_status(STATUS_DONE, "")
                logger.info("Descargado: %s", downloaded)
            else:
                on_status(STATUS_ERROR, "Archivo no encontrado tras descarga")

        except RuntimeError as exc:
            err = str(exc)
            if err == "cancelled":
                on_status(STATUS_CANCELLED, "")
                self._cleanup_partial_files(folder, base_name)
            else:
                on_status(STATUS_ERROR, err)
            logger.warning("Error descargando %s: %s", track.url, err)

        except Exception as exc:
            logger.exception("Error inesperado descargando %s", track.url)
            on_status(STATUS_ERROR, str(exc)[:200])
            # Intentar cleanup de archivos parciales
            try:
                self._cleanup_partial_files(folder, base_name)
            except Exception:
                pass

        finally:
            with self._lock:
                self._cancel_events.pop(track.url, None)
            if delay > 0:
                import time as _t
                _t.sleep(delay)

    def _cleanup_partial_files(self, folder: str, base_name: str) -> None:
        """Limpia archivos parciales después de cancelación o error."""
        import glob

        try:
            # Buscar archivos parciales comunes
            patterns = [
                os.path.join(folder, f"{base_name}.*"),
                os.path.join(folder, f"{base_name}.pp_temp.*"),
                os.path.join(folder, f"{base_name}.ytdl.*"),
                os.path.join(folder, f"{base_name}.part"),
            ]

            for pattern in patterns:
                for file_path in glob.glob(pattern):
                    try:
                        if os.path.exists(file_path) and os.path.getsize(file_path) > 0:
                            os.remove(file_path)
                            logger.debug(f"Archivo parcial limpiado: {file_path}")
                    except OSError as e:
                        logger.warning(f"No se pudo limpiar {file_path}: {e}")
        except Exception as e:
            logger.warning(f"Error en cleanup de archivos parciales: {e}")
