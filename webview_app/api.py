"""
WebViewAPI: puente JS <-> Python para la vista pywebview.

No reemplaza gui/ (CustomTkinter sigue intacto y funcional).
Reutiliza exactamente la misma lógica de negocio que gui/main_window.py:
UIController, DownloadManager, url_detector, quality/presets.

Cada método público de esta clase queda expuesto en el frontend como
`window.pywebview.api.<nombre>(...)` y devuelve una Promise en JS.

Los eventos que ocurren fuera de una llamada JS directa (progreso de
descarga, estado de un track) se empujan al frontend con
`window.evaluate_js(...)`, invocando `window.__bridgeEvent(nombre, payload)`
en el HTML. Ese callback debe registrarse en el HTML antes de usarse.
"""
import json
import logging
import os
import threading
from dataclasses import asdict
from typing import Optional

from download_manager import DownloadManager
from gui.ui_controller import UIController
from models import (
    TrackInfo, STATUS_PENDING, STATUS_FETCHING, STATUS_DOWNLOADING,
    STATUS_DONE, STATUS_ERROR, STATUS_SKIP, STATUS_CANCELLED,
)
from quality.presets import get_preset
from url_detector import detect_handler, detect_platform_name
from utils.validators import parse_urls_from_text

logger = logging.getLogger(__name__)

_STATUS_EMOJI = {
    STATUS_DOWNLOADING: "⬇",
    STATUS_DONE: "✓",
    STATUS_ERROR: "✗",
    STATUS_SKIP: "⊘",
    STATUS_FETCHING: "🔍",
    STATUS_CANCELLED: "⊗",
}


def _track_to_dict(track: TrackInfo) -> dict:
    d = asdict(track)
    d["duration_str"] = track.duration_str()
    return d


class WebViewAPI:
    """
    Instanciar UNA vez por ventana. `window` se inyecta después de
    crear la ventana pywebview (ver main_webview.py) porque
    webview.create_window() necesita la instancia de la API antes
    de devolver el objeto window.
    """

    def __init__(self, base_dir: Optional[str] = None):
        self._base_dir = base_dir or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.window = None  # se setea vía attach_window()

        self.controller = UIController(base_dir=self._base_dir)

        # Igual que gui/main_window.py: DownloadManager propio, independiente
        # del que crea UIController internamente (ese no se usa en la GUI real).
        self.download_manager = DownloadManager()
        self.download_manager.start(self.controller.get_config_value("max_workers", 3))

        self._tracks: dict[str, TrackInfo] = {}
        self._lock = threading.Lock()

    def attach_window(self, window) -> None:
        self.window = window

    # ------------------------------------------------------------------ #
    # Push de eventos al frontend                                          #
    # ------------------------------------------------------------------ #

    def _push(self, event: str, payload: dict) -> None:
        if not self.window:
            return
        try:
            js = f"window.__bridgeEvent && window.__bridgeEvent({json.dumps(event)}, {json.dumps(payload)})"
            self.window.evaluate_js(js)
        except Exception:
            logger.exception("Error empujando evento '%s' al frontend", event)

    # ------------------------------------------------------------------ #
    # Config                                                               #
    # ------------------------------------------------------------------ #

    def get_config(self) -> dict:
        return self.controller.get_config()

    def set_config_value(self, key: str, value) -> dict:
        self.controller.set_config_value(key, value)
        return {"ok": True, "key": key, "value": value}

    def browse_folder(self) -> Optional[str]:
        """Abre el diálogo NATIVO de carpeta (no HTML) via pywebview."""
        if not self.window:
            return None
        try:
            import webview
            result = self.window.create_file_dialog(webview.FOLDER_DIALOG)
        except Exception:
            logger.exception("Error abriendo diálogo de carpeta")
            return None
        if not result:
            return None
        folder = result[0] if isinstance(result, (list, tuple)) else result
        self.controller.set_config_value("dest_folder", folder)
        return folder

    # ------------------------------------------------------------------ #
    # Cola de tracks                                                       #
    # ------------------------------------------------------------------ #

    def get_tracks(self) -> list[dict]:
        with self._lock:
            return [_track_to_dict(t) for t in self._tracks.values()]

    def add_urls(self, text: str) -> dict:
        """
        Encola URLs para fetch de metadatos en background.
        Devuelve de inmediato; los resultados llegan por eventos
        'track_added' (placeholder) y 'track_updated' (metadatos listos).
        """
        urls = parse_urls_from_text(text or "")
        if not urls:
            return {"ok": False, "error": "No se encontraron URLs válidas de YouTube o SoundCloud."}

        new_urls = []
        with self._lock:
            for url in urls:
                if url in self._tracks:
                    continue
                placeholder = TrackInfo(url=url, title="Cargando...", platform=detect_platform_name(url))
                placeholder.status = STATUS_FETCHING
                self._tracks[url] = placeholder
                new_urls.append(url)

        for url in new_urls:
            self._push("track_added", _track_to_dict(self._tracks[url]))
            threading.Thread(target=self._fetch_worker, args=(url,), daemon=True).start()

        return {"ok": True, "queued": len(new_urls), "skipped": len(urls) - len(new_urls)}

    def _fetch_worker(self, original_url: str) -> None:
        try:
            handler = detect_handler(original_url)
            metas = handler.get_metadata(original_url)
        except (ValueError, RuntimeError) as exc:
            self._mark_fetch_error(original_url, str(exc))
            return
        except Exception as exc:
            logger.exception("Error inesperado en fetch_worker")
            self._mark_fetch_error(original_url, str(exc)[:200])
            return

        if not metas:
            self._mark_fetch_error(original_url, "Sin resultados")
            return

        first = TrackInfo.from_metadata(metas[0])
        first.status = STATUS_PENDING
        # Ya descargado antes (SQLite) -> reflejarlo en la cola
        if self.controller.is_track_downloaded(first.url):
            first.status = STATUS_SKIP

        with self._lock:
            # La URL canónica de la plataforma puede diferir de la pegada
            self._tracks.pop(original_url, None)
            self._tracks[first.url] = first

        self._push("track_replaced", {
            "old_url": original_url,
            "track": _track_to_dict(first),
        })

        # Tracks adicionales (playlist)
        extra_added = []
        with self._lock:
            for meta in metas[1:]:
                info = TrackInfo.from_metadata(meta)
                if self.controller.is_track_downloaded(info.url):
                    info.status = STATUS_SKIP
                if info.url not in self._tracks:
                    self._tracks[info.url] = info
                    extra_added.append(info)

        for info in extra_added:
            self._push("track_added", _track_to_dict(info))

    def _mark_fetch_error(self, url: str, message: str) -> None:
        with self._lock:
            track = self._tracks.get(url)
            if track:
                track.status = STATUS_ERROR
                track.error_msg = message
        self._push("track_updated", {"url": url, "status": STATUS_ERROR, "error_msg": message})

    # ------------------------------------------------------------------ #
    # Descarga                                                             #
    # ------------------------------------------------------------------ #

    def start_download(self, url: str) -> dict:
        with self._lock:
            track = self._tracks.get(url)
        if not track:
            return {"ok": False, "error": "Track no encontrado en la cola"}
        if track.status in (STATUS_DOWNLOADING, STATUS_FETCHING, STATUS_DONE, STATUS_SKIP):
            return {"ok": False, "error": f"Track ya está en estado '{track.status}'"}

        dest = self.controller.get_config_value("dest_folder", "")
        if not dest:
            return {"ok": False, "error": "Selecciona una carpeta de destino primero."}

        self._submit_one(track, dest)
        return {"ok": True}

    def start_all_pending(self) -> dict:
        with self._lock:
            pending = [
                t for t in self._tracks.values()
                if t.status not in (STATUS_DOWNLOADING, STATUS_FETCHING, STATUS_DONE, STATUS_SKIP)
            ]
        dest = self.controller.get_config_value("dest_folder", "")
        if not dest:
            return {"ok": False, "error": "Selecciona una carpeta de destino primero."}
        for track in pending:
            self._submit_one(track, dest)
        return {"ok": True, "submitted": len(pending)}

    def _submit_one(self, track: TrackInfo, dest_folder: str) -> None:
        url = track.url
        try:
            handler = detect_handler(url)
        except ValueError as exc:
            self._push_status(url, STATUS_ERROR, str(exc)[:200])
            return

        preset = get_preset(self.controller.get_config_value("quality_preset", "mp3_320"))
        post_config = {
            "normalize_volume": self.controller.get_config_value("normalize_volume", False),
            "remove_silence": self.controller.get_config_value("remove_silence", False),
            "embed_artwork": self.controller.get_config_value("embed_artwork", True),
            "embed_metadata": self.controller.get_config_value("embed_metadata", True),
        }
        # Mismo fallback que gui/main_window.py: soundcloud.oauth_token primero,
        # luego el oauth_token plano en config (legado).
        oauth_token = (
            self.controller.get_config_value("soundcloud", {}).get("oauth_token", "")
            or self.controller.get_config_value("oauth_token", "")
        )

        def on_progress(v: float):
            with self._lock:
                track.progress = v
            self._push("track_progress", {"url": url, "progress": v})

        def on_status(status: str, err: str):
            self._push_status(url, status, err)
            if status == STATUS_DONE:
                self.controller.record_download(track)

        self.download_manager.submit_download(
            track=track,
            handler=handler,
            dest_folder=dest_folder,
            filename_pattern=self.controller.get_config_value("filename_pattern", "{artist} - {title}"),
            subfolder_by_artist=self.controller.get_config_value("subfolder_by_artist", False),
            quality_preset=preset,
            post_config=post_config,
            delay=float(self.controller.get_config_value("delay", 0.5)),
            on_progress=on_progress,
            on_status=on_status,
            oauth_token=oauth_token,
        )

    def _push_status(self, url: str, status: str, error_msg: str) -> None:
        with self._lock:
            track = self._tracks.get(url)
            if track:
                track.status = status
                track.error_msg = error_msg
        self._push("track_status", {
            "url": url,
            "status": status,
            "error_msg": error_msg,
            "emoji": _STATUS_EMOJI.get(status, "•"),
        })

    def pause_downloads(self) -> dict:
        self.download_manager.pause_all()
        return {"ok": True, "paused": True}

    def resume_downloads(self) -> dict:
        self.download_manager.resume_all()
        return {"ok": True, "paused": False}

    def cancel_download(self, url: str) -> dict:
        self.download_manager.cancel_track(url)
        return {"ok": True}

    def cancel_all(self) -> dict:
        self.download_manager.cancel_all()
        return {"ok": True}

    def set_max_workers(self, n: int) -> dict:
        n = max(1, min(16, int(n)))
        self.controller.set_config_value("max_workers", n)
        self.download_manager.set_max_workers(n)
        return {"ok": True, "max_workers": n}

    # ------------------------------------------------------------------ #
    # Historial / estadísticas                                            #
    # ------------------------------------------------------------------ #

    def get_recent_downloads(self, limit: int = 50) -> list[dict]:
        return self.controller.get_recent_downloads(limit)

    def get_stats(self) -> dict:
        return self.controller.get_stats()

    def import_soundcloud_likes(self) -> dict:
        return self.controller.import_soundcloud_likes()

    # ------------------------------------------------------------------ #
    # Ciclo de vida                                                       #
    # ------------------------------------------------------------------ #

    def shutdown(self) -> None:
        self.download_manager.cancel_all()
        self.download_manager.shutdown()
