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
import subprocess
import sys
import threading
from dataclasses import asdict
from pathlib import Path
from typing import Optional

from download_manager import DownloadManager
from gui.ui_controller import UIController
from handlers.soundcloud_handler import SoundCloudHandler
from models import (
    TrackInfo, STATUS_PENDING, STATUS_FETCHING, STATUS_DOWNLOADING,
    STATUS_DONE, STATUS_ERROR, STATUS_SKIP, STATUS_CANCELLED,
)
from quality.presets import get_preset
from sync import match_utils, task_scheduler
from sync.soundcloud_api import SoundCloudAPIClient
from sync.sync_manager import SyncManager
from url_detector import detect_handler, detect_platform_name
from utils.validators import parse_urls_from_text

_AUDIO_EXTENSIONS = match_utils.AUDIO_EXTENSIONS

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

    def __init__(self, base_dir: Optional[str] = None, config_path: Optional[str] = None):
        self._base_dir = base_dir or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self._window = None  # se setea vía attach_window()

        # config_path explícito (lo usa el .exe empaquetado, que no puede
        # guardar junto al ejecutable); si no, se deriva de base_dir.
        self.controller = UIController(base_dir=self._base_dir, config_path=config_path)

        # Igual que gui/main_window.py: DownloadManager propio, independiente
        # del que crea UIController internamente (ese no se usa en la GUI real).
        self.download_manager = DownloadManager()
        self.download_manager.start(self.controller.get_config_value("max_workers", 3))

        self._tracks: dict[str, TrackInfo] = {}
        self._lock = threading.Lock()

        # SoundCloud sync (se inicializa al verificar credenciales, igual
        # que gui/sync_window.py). None hasta la primera verificación OK.
        self._sync_manager: Optional[SyncManager] = None
        self._sc_user_info: Optional[dict] = None

    def attach_window(self, window) -> None:
        self._window = window

    # ------------------------------------------------------------------ #
    # Push de eventos al frontend                                          #
    # ------------------------------------------------------------------ #

    def _push(self, event: str, payload: dict) -> None:
        if not self._window:
            return
        try:
            js = f"window.__bridgeEvent && window.__bridgeEvent({json.dumps(event)}, {json.dumps(payload)})"
            self._window.evaluate_js(js)
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
        if not self._window:
            return None
        try:
            import webview
            result = self._window.create_file_dialog(webview.FOLDER_DIALOG)
        except Exception:
            logger.exception("Error abriendo diálogo de carpeta")
            return None
        if not result:
            return None
        folder = result[0] if isinstance(result, (list, tuple)) else result
        self.controller.set_config_value("dest_folder", folder)
        return folder

    def browse_any_folder(self, initial: str = "") -> Optional[str]:
        """Diálogo nativo de carpeta que NO toca dest_folder (para escanear otra ubicación)."""
        if not self._window:
            return None
        try:
            import webview
            kwargs = {"directory": initial} if initial and os.path.isdir(initial) else {}
            result = self._window.create_file_dialog(webview.FOLDER_DIALOG, **kwargs)
        except Exception:
            logger.exception("Error abriendo diálogo de carpeta")
            return None
        if not result:
            return None
        return result[0] if isinstance(result, (list, tuple)) else result

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
            "analyze_audio": self.controller.get_config_value("analyze_audio", False),
            "key_format": self.controller.get_config_value("key_format", "camelot"),
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

    # ------------------------------------------------------------------ #
    # Historial / estadísticas                                            #
    # ------------------------------------------------------------------ #

    def get_recent_downloads(self, limit: int = 50) -> list[dict]:
        return self.controller.get_recent_downloads(limit)

    def get_recent_activity(self, limit: int = 30) -> list[dict]:
        """
        Historial unificado para el panel principal: descargas manuales
        (pegando URL) + descargas por sync de SoundCloud, en un solo orden
        cronológico. Excluye las entradas de reconciliación de biblioteca
        (url "local://..."): esas son archivos que YA tenías, no descargas
        hechas por la app, y no tiene sentido mostrarlas como actividad.
        """
        items = []
        for d in self.controller.get_recent_downloads(1000):
            if str(d.get("url", "")).startswith("local://"):
                continue
            items.append({
                "title": d.get("title"),
                "artist": d.get("artist"),
                "platform": d.get("platform"),
                "local_path": d.get("local_path"),
                "date": d.get("download_date"),
                "source": "manual",
            })
        if self._sync_manager:
            for d in self._sync_manager.history.get_all_downloads():
                items.append({
                    "title": d.get("title"),
                    "artist": d.get("artist"),
                    "platform": d.get("platform"),
                    "local_path": d.get("file_path"),
                    "date": d.get("downloaded_at"),
                    "source": "sync",
                })
        items.sort(key=lambda d: d.get("date") or "", reverse=True)
        return items[:limit]

    def get_stats(self) -> dict:
        return self.controller.get_stats()

    def import_soundcloud_likes(self) -> dict:
        return self.controller.import_soundcloud_likes()

    def search_downloads(self, query: str) -> list[dict]:
        return self.controller.history.search_downloads(query)

    def delete_download(self, url: str) -> dict:
        ok = self.controller.history.delete_download(url)
        return {"ok": ok}

    # ------------------------------------------------------------------ #
    # Configuración (Settings)                                             #
    # ------------------------------------------------------------------ #

    def save_settings(self, updates: dict) -> dict:
        """
        Guarda un lote de ajustes (calidad, post-proceso, patrón de nombre,
        etc). Igual que gui/settings.py: el sub-dict 'soundcloud' se
        mergea (no reemplaza) para no perder oauth_token/client_id si el
        caller solo mandó, por ejemplo, sync_interval_minutes.
        """
        try:
            updates = dict(updates or {})
            sc_updates = updates.pop("soundcloud", None)
            if sc_updates:
                sc = dict(self.controller.get_config_value("soundcloud", {}) or {})
                sc.update(sc_updates)
                self.controller.set_config_value("soundcloud", sc)
            for key, value in updates.items():
                self.controller.set_config_value(key, value)
            return {"ok": True}
        except Exception as e:
            logger.exception("Error guardando ajustes")
            return {"ok": False, "error": str(e)}

    def register_autosync_task(self, minutes: int) -> dict:
        """
        Registra la tarea programada de Windows con el intervalo dado.
        Funciona igual desde el .exe que desde el código fuente: la propia
        tarea apunta al ejecutable (`--auto-sync`) o al script, según el caso.
        """
        try:
            minutes = max(5, min(1440, int(minutes)))
            self.save_settings({"soundcloud": {"sync_interval_minutes": minutes}})
            ok, msg = task_scheduler.register(minutes, self.controller.config.config_path)
            return {"ok": ok, "message": msg, "minutes": minutes,
                    **({} if ok else {"error": msg})}
        except Exception as e:
            logger.exception("Error registrando tarea programada")
            return {"ok": False, "error": str(e)}

    def get_autosync_status(self) -> dict:
        """Estado de la tarea programada, para mostrarlo en Configuración."""
        try:
            ok, msg = task_scheduler.status()
            return {"registered": ok, "detail": msg,
                    "command": task_scheduler.build_command(self.controller.config.config_path)}
        except Exception as e:
            return {"registered": False, "detail": str(e), "command": ""}

    def remove_autosync_task(self) -> dict:
        try:
            ok, msg = task_scheduler.remove()
            return {"ok": ok, "message": msg}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    # ------------------------------------------------------------------ #
    # SoundCloud: conexión y sincronización                                #
    # ------------------------------------------------------------------ #

    def get_soundcloud_status(self) -> dict:
        """Estado actual sin golpear la red: credenciales guardadas + última verificación."""
        sc = self.controller.get_config_value("soundcloud", {}) or {}
        stats = self._sync_manager.get_history_stats() if self._sync_manager else {}
        last_sync = self._sync_manager.get_last_sync_info() if self._sync_manager else None
        return {
            "has_credentials": bool(sc.get("oauth_token") and sc.get("client_id")),
            "connected": self._sync_manager is not None,
            "user_info": self._sc_user_info,
            "sync_interval_minutes": sc.get("sync_interval_minutes", 1440),
            "history_stats": stats,
            "last_sync": last_sync,
        }

    def connect_with_saved_credentials(self) -> dict:
        """
        Auto-conecta con las credenciales que ya están en config.json (p.ej.
        restauradas de un respaldo), sin que el usuario tenga que volver a
        pegarlas en el modal. No hace nada si ya está conectado o no hay
        credenciales guardadas.
        """
        if self._sync_manager is not None:
            return {"ok": True, "user_info": self._sc_user_info, "already_connected": True}
        sc = self.controller.get_config_value("soundcloud", {}) or {}
        oauth_token = sc.get("oauth_token", "")
        client_id = sc.get("client_id", "")
        if not oauth_token or not client_id:
            return {"ok": False, "error": "No hay credenciales guardadas"}
        return self.verify_soundcloud_credentials(oauth_token, client_id)

    def verify_soundcloud_credentials(self, oauth_token: str, client_id: str) -> dict:
        """
        Valida credenciales contra la API real, las guarda si son válidas,
        e inicializa self._sync_manager. Se corre sincrónico (la llamada ya
        viene de un click de botón en el frontend, que puede mostrar su
        propio estado de "verificando...").
        """
        oauth_token = (oauth_token or "").strip()
        client_id = (client_id or "").strip()
        if not oauth_token or not client_id:
            return {"ok": False, "error": "Completa OAuth Token y Client ID"}

        try:
            api_client = SoundCloudAPIClient(oauth_token, client_id)
            user_info = api_client.validate_credentials()
        except Exception as e:
            return {"ok": False, "error": str(e)}

        self.save_settings({"soundcloud": {"oauth_token": oauth_token, "client_id": client_id}})
        self._sc_user_info = user_info

        threshold = self.controller.get_config_value("duplicate_checker", {}).get(
            "similarity_threshold", match_utils.MATCH_THRESHOLD
        )
        self._sync_manager = SyncManager(
            oauth_token, client_id,
            self.controller.get_config_value("dest_folder", ""),
            SoundCloudHandler(),
            similarity_threshold=threshold,
            filename_pattern=self.controller.get_config_value("filename_pattern", "{artist} - {title}"),
            subfolder_by_artist=self.controller.get_config_value("subfolder_by_artist", False),
            library_folders=self._library_folders(),
            track_event_callback=self._on_sync_track_event,
            analyze_audio=self.controller.get_config_value("analyze_audio", False),
            key_format=self.controller.get_config_value("key_format", "camelot"),
            fingerprint_check=self.controller.get_config_value("fingerprint_check", True),
        )
        # SyncManager arma su PROPIO SoundCloudAPIClient (self._sync_manager.api),
        # un objeto distinto al que se usó arriba para el chequeo inicial.
        # validate_credentials() no solo verifica: guarda self.api.user_id,
        # que get_likes()/get_recent_likes() exigen tener seteado o tiran
        # "Necesitas validar credenciales primero". No es una request
        # redundante aunque use el mismo token — sin esto, cualquier sync
        # falla siempre, incluso recién conectado.
        try:
            self._sync_manager.validate_credentials()
        except Exception as e:
            return {"ok": False, "error": str(e)}

        # Sincroniza filesystem -> DB en background (recupera archivos previos)
        threading.Thread(target=self._sync_filesystem_bg, daemon=True).start()

        return {"ok": True, "user_info": user_info}

    def _sync_filesystem_bg(self) -> None:
        try:
            self._sync_manager.sync_filesystem_to_db()
        except Exception:
            logger.exception("Error sincronizando filesystem -> DB")

    def _require_sync_manager(self) -> dict:
        if not self._sync_manager:
            return {"ok": False, "error": "Verificá tus credenciales de SoundCloud primero"}
        return {"ok": True}

    def _on_sync_track_event(self, event: str, track, detail: str = "") -> None:
        """
        Refleja en la cola de la UI cada canción que baja la sincronización.
        Sin esto, la sync descarga en su propio bucle interno y la cola se
        queda en 0 aunque haya descargas en curso.
        """
        url = getattr(track, "url", "") or ""
        if not url:
            return

        with self._lock:
            info = self._tracks.get(url)
            if info is None:
                info = TrackInfo(
                    url=url,
                    title=getattr(track, "title", "") or url,
                    artist=getattr(track, "artist", "") or "",
                    platform="soundcloud",
                    thumbnail_url=getattr(track, "artwork_url", "") or "",
                )
                self._tracks[url] = info
                is_new = True
            else:
                is_new = False

            status = {
                "start": STATUS_DOWNLOADING,
                "done": STATUS_DONE,
                "error": STATUS_ERROR,
                "cancelled": STATUS_CANCELLED,
            }.get(event, STATUS_PENDING)
            info.status = status
            if event == "done":
                info.progress = 1.0
                info.local_path = detail or ""
            elif event == "error":
                info.error_msg = detail or ""

        if is_new:
            self._push("track_added", _track_to_dict(info))
        self._push("track_status", {
            "url": url,
            "status": status,
            "error_msg": detail if event == "error" else "",
            "emoji": _STATUS_EMOJI.get(status, "•"),
        })

    def start_sync(self, mode: str = "full", count: int = 10) -> dict:
        """
        Sincronización manual completa ('full', descarga todo lo pendiente)
        o rápida ('recent', solo revisa las últimas `count`). No bloquea:
        corre en background y empuja progreso vía evento 'sync_progress' y
        el resultado final vía 'sync_complete'.
        """
        guard = self._require_sync_manager()
        if not guard["ok"]:
            return guard

        def progress_cb(pct: int, msg: str):
            self._push("sync_progress", {"pct": pct, "msg": msg})

        def run():
            try:
                if mode == "recent":
                    results = self._sync_manager.sync_recent(count=count, progress_callback=progress_cb)
                else:
                    results = self._sync_manager.sync_once(progress_callback=progress_cb)
                self._push("sync_complete", {
                    "ok": True,
                    "new": results.get("new", 0),
                    "skipped": results.get("skipped", 0),
                    "errors": results.get("errors", 0),
                })
            except Exception as e:
                logger.exception("Error en sincronización")
                self._push("sync_complete", {"ok": False, "error": str(e)})

        threading.Thread(target=run, daemon=True).start()
        return {"ok": True}

    def stop_sync(self) -> dict:
        if self._sync_manager:
            self._sync_manager.stop()
        return {"ok": True}

    def scan_likes(self) -> dict:
        """
        Trae tus likes actuales de SoundCloud y los guarda en la DB (sin
        descargar nada). Alimenta a get_likes(). Corre en background;
        el frontend debe esperar el evento 'likes_scanned' y luego pedir
        get_likes() de nuevo.
        """
        guard = self._require_sync_manager()
        if not guard["ok"]:
            return guard

        def progress_cb(pct: int, msg: str):
            self._push("sync_progress", {"pct": pct, "msg": msg})

        def run():
            try:
                results = self._sync_manager.scan_only(progress_callback=progress_cb)
                self._push("likes_scanned", {
                    "ok": True, "new": len(results.get("tracks", [])),
                    "skipped": len(results.get("duplicates", [])),
                })
            except Exception as e:
                logger.exception("Error escaneando likes")
                self._push("likes_scanned", {"ok": False, "error": str(e)})

        threading.Thread(target=run, daemon=True).start()
        return {"ok": True}

    def get_failed_downloads(self) -> list[dict]:
        """Canciones que fallaron al descargar, con el motivo."""
        if not self._sync_manager:
            return []
        try:
            return self._sync_manager.history.get_failed()
        except Exception:
            logger.exception("Error obteniendo descargas fallidas")
            return []

    def retry_failed_downloads(self, url: str = "") -> dict:
        """
        Olvida los fallos registrados para que la próxima sincronización los
        vuelva a intentar. Sin `url`, olvida todos. Útil cuando el motivo era
        temporal (caída de red) o si el track dejó de estar bloqueado.
        """
        guard = self._require_sync_manager()
        if not guard["ok"]:
            return guard
        try:
            n = self._sync_manager.history.clear_failed(url or None)
            return {"ok": True, "cleared": n}
        except Exception as e:
            logger.exception("Error reintentando fallidas")
            return {"ok": False, "error": str(e)}

    def get_likes(self) -> list[dict]:
        """Likes guardados en DB con su estado de descarga (sin red, instantáneo)."""
        if not self._sync_manager:
            return []
        try:
            return self._sync_manager.get_likes_with_status()
        except Exception:
            logger.exception("Error obteniendo likes")
            return []

    def download_selected_likes(self, urls: list[str]) -> dict:
        """
        Descarga likes puntuales elegidos en "Ver Mis Likes". Reusa la
        misma cola visual que las URLs pegadas a mano (aparecen en
        'Cola'), pero al completarse registran en el historial del
        SyncManager (tabla sync_downloads), no en el de HistoryManager,
        igual que hace gui/likes_preview_window.py.
        """
        guard = self._require_sync_manager()
        if not guard["ok"]:
            return guard

        dest = self.controller.get_config_value("dest_folder", "")
        if not dest:
            return {"ok": False, "error": "Selecciona una carpeta de destino primero."}

        likes_by_url = {l["url"]: l for l in self.get_likes()}
        submitted = 0
        for url in urls or []:
            like = likes_by_url.get(url)
            if not like:
                continue
            track = TrackInfo(
                url=like["url"], title=like["title"], artist=like["artist"] or "",
                platform="soundcloud", thumbnail_url=like.get("artwork_url") or "",
            )
            track.status = STATUS_PENDING
            with self._lock:
                if url not in self._tracks:
                    self._tracks[url] = track
                    self._push("track_added", _track_to_dict(track))
            self._submit_like_download(like, dest)
            submitted += 1
        return {"ok": True, "submitted": submitted}

    def _submit_like_download(self, like: dict, dest_folder: str) -> None:
        url = like["url"]
        with self._lock:
            track = self._tracks.get(url)
        if not track:
            return

        preset = get_preset(self.controller.get_config_value("quality_preset", "mp3_320"))
        post_config = {
            "normalize_volume": self.controller.get_config_value("normalize_volume", False),
            "remove_silence": self.controller.get_config_value("remove_silence", False),
            "embed_artwork": self.controller.get_config_value("embed_artwork", True),
            "embed_metadata": self.controller.get_config_value("embed_metadata", True),
            "analyze_audio": self.controller.get_config_value("analyze_audio", False),
            "key_format": self.controller.get_config_value("key_format", "camelot"),
        }
        oauth_token = self.controller.get_config_value("soundcloud", {}).get("oauth_token", "")

        def on_progress(v: float):
            with self._lock:
                track.progress = v
            self._push("track_progress", {"url": url, "progress": v})

        def on_status(status: str, err: str):
            self._push_status(url, status, err)
            if status == STATUS_DONE:
                try:
                    self._sync_manager.history.mark_downloaded(
                        url, like["title"], like["artist"] or "", track.local_path,
                        platform="soundcloud",
                    )
                    self._sync_manager.history.mark_like_downloaded(
                        url=url, title=like["title"], artist=like["artist"] or "",
                        track_id=like.get("id"), duration_ms=like.get("duration_ms"),
                        artwork_url=like.get("artwork_url"), genre=like.get("genre"),
                        created_at=like.get("created_at"),
                    )
                except Exception:
                    logger.exception("Error registrando like descargado en historial")

        self.download_manager.submit_download(
            track=track,
            handler=SoundCloudHandler(),
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

    def get_default_scan_folder(self) -> str:
        """Carpeta padre de dest_folder (p. ej. D:\\Musik si dest_folder es D:\\Musik\\prueba)."""
        dest = self.controller.get_config_value("dest_folder", "")
        parent = os.path.dirname(dest.rstrip("\\/")) if dest else ""
        return parent or dest

    def _library_folders(self) -> list[str]:
        """
        Carpetas donde ya tenés música, para que la detección de duplicados
        no se limite a dest_folder. Si no hay ninguna configurada se asume
        la carpeta padre del destino, que es donde suelen convivir las
        carpetas por género.
        """
        configured = self.controller.get_config_value("library_folders", []) or []
        if configured:
            return [f for f in configured if f]
        default = self.get_default_scan_folder()
        return [default] if default else []

    def get_library_folders(self) -> list[str]:
        return self._library_folders()

    def set_library_folders(self, folders: list[str]) -> dict:
        """Fija las carpetas de biblioteca y reconstruye el índice de duplicados."""
        folders = [f for f in (folders or []) if f]
        self.controller.set_config_value("library_folders", folders)
        if self._sync_manager:
            self._sync_manager.checker.library_folders = list(folders)
            self._sync_manager.checker.invalidate_index()
        return {"ok": True, "library_folders": folders}

    def reconcile_library(self, folder: str) -> dict:
        """
        Escanea `folder` COMPLETO (todas las subcarpetas) buscando archivos
        de audio que correspondan a likes guardados pero que la app no
        tiene registrados como descargados — típicamente música bajada
        antes de usar esta app, o guardada en otras carpetas de género en
        vez de dest_folder. Usa el mismo matching difuso (artista+título)
        que el resto de la app (sync.duplicate_checker), pero a diferencia
        de sync_filesystem_to_db() SÍ vincula cada archivo al URL real del
        like (no un local:// falso), así que get_likes_with_status() y
        las estadísticas reflejan correctamente qué likes ya tenés.
        No bloquea: corre en background y reporta progreso por
        'sync_progress' y el resultado final por 'reconcile_complete'.
        """
        guard = self._require_sync_manager()
        if not guard["ok"]:
            return guard
        if not folder or not os.path.isdir(folder):
            return {"ok": False, "error": f"Carpeta no encontrada: {folder}"}

        def progress_cb(pct: int, msg: str):
            self._push("sync_progress", {"pct": pct, "msg": msg})

        def run():
            try:
                result = self._do_reconcile(folder, progress_cb)
                self._push("reconcile_complete", {"ok": True, **result})
            except Exception as e:
                logger.exception("Error reconciliando biblioteca")
                self._push("reconcile_complete", {"ok": False, "error": str(e)})

        threading.Thread(target=run, daemon=True).start()
        return {"ok": True}

    def _do_reconcile(self, folder: str, progress_cb) -> dict:
        history = self._sync_manager.history
        threshold = self.controller.get_config_value("duplicate_checker", {}).get(
            "similarity_threshold", match_utils.MATCH_THRESHOLD
        )

        progress_cb(0, f"Escaneando {folder}…")
        files = match_utils.index_audio_files([folder])
        progress_cb(8, f"{len(files)} archivos de audio encontrados")

        likes = history.load_likes()
        existing_urls = {d["url"] for d in history.get_all_downloads()}

        # Primera pasada: mejor archivo por like (sin escribir todavía).
        pending: list[tuple[int, dict, Path]] = []
        already = 0
        total = len(likes)
        for i, like in enumerate(likes):
            if like["url"] in existing_urls:
                already += 1
            else:
                candidates = match_utils.like_candidates(
                    like.get("artist") or "", like.get("title") or ""
                )
                best_file, best_score = match_utils.find_best_match(
                    candidates, files, threshold
                )
                if best_file is not None:
                    pending.append((best_score, like, best_file))

            if total and i % 10 == 0:
                progress_cb(8 + int(85 * i / total), f"Comparando likes… {i}/{total}")

        # Un archivo no puede ser la descarga de dos likes distintos: si dos
        # likes apuntan al mismo archivo, gana el de mayor similitud.
        pending.sort(key=lambda t: t[0], reverse=True)
        claimed: set[str] = set()
        matched = 0
        for score, like, file_path in pending:
            key = str(file_path)
            if key in claimed:
                continue
            claimed.add(key)
            history.mark_downloaded(
                like["url"], like["title"], like["artist"], key, platform="soundcloud",
            )
            history.mark_like_downloaded(
                url=like["url"], title=like["title"], artist=like["artist"],
                track_id=like.get("id"), duration_ms=like.get("duration_ms"),
                artwork_url=like.get("artwork_url"), genre=like.get("genre"),
                created_at=like.get("created_at"),
            )
            matched += 1

        progress_cb(100, f"✓ {matched} coincidencias nuevas · {already} ya registradas")
        return {
            "matched": matched, "already_registered": already,
            "total_likes": total, "files_scanned": len(files),
        }

    # ------------------------------------------------------------------ #
    # Ciclo de vida                                                       #
    # ------------------------------------------------------------------ #

    def shutdown(self) -> None:
        self.download_manager.cancel_all()
        self.download_manager.shutdown()
