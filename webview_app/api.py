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
import re
import subprocess
import sys
import threading
import unicodedata
from dataclasses import asdict
from pathlib import Path
from typing import Optional

from thefuzz import fuzz

from download_manager import DownloadManager
from gui.ui_controller import UIController
from handlers.soundcloud_handler import SoundCloudHandler
from models import (
    TrackInfo, STATUS_PENDING, STATUS_FETCHING, STATUS_DOWNLOADING,
    STATUS_DONE, STATUS_ERROR, STATUS_SKIP, STATUS_CANCELLED,
)
from quality.presets import get_preset
from sync.soundcloud_api import SoundCloudAPIClient
from sync.sync_manager import SyncManager
from url_detector import detect_handler, detect_platform_name
from utils.validators import parse_urls_from_text

_AUDIO_EXTENSIONS = {'.mp3', '.m4a', '.flac', '.wav', '.ogg', '.opus', '.aac'}

# Ruido de promo/versionado que aparece tanto en los títulos de SoundCloud
# como en los nombres de archivo, y que infla la similitud entre canciones
# que no tienen nada que ver ("X [FREE DL]" vs "Y [FREE DL]"). Quitarlo
# sube el score de las coincidencias reales y baja el de las falsas.
_MATCH_NOISE = re.compile(
    r"\b(free\s*(dl|download)|full\s*length|out\s*now|premiere|preview|"
    r"extended(\s*(mix|version))?|original\s*mix|radio\s*edit|"
    r"master(ed|ing)?|mstr|final|v\d+(\.\d+)?|hq|clip|temporary)\b",
    re.I,
)
_MATCH_BRACKETS = re.compile(r"[\[\(\{][^\]\)\}]*[\]\)\}]")

# Umbral propio para la reconciliación: las cadenas ya vienen limpias de
# ruido, así que puntúan distinto que en sync/duplicate_checker. 80 se
# eligió midiendo contra la biblioteca real: por encima no aparecían
# falsos positivos, por debajo sí (p.ej. "No Good" vs "Raise The Roof").
_RECONCILE_THRESHOLD = 80
_MIN_MATCH_LEN = 4


def _clean_for_match(text: str) -> str:
    """Normaliza y quita ruido de promo/versionado para comparar títulos."""
    if not text:
        return ""
    t = _MATCH_BRACKETS.sub(" ", text)
    t = _MATCH_NOISE.sub(" ", t)
    t = unicodedata.normalize("NFD", t)
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    t = re.sub(r"[^\w\s]", " ", t.lower())
    return " ".join(t.split())

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

        # SoundCloud sync (se inicializa al verificar credenciales, igual
        # que gui/sync_window.py). None hasta la primera verificación OK.
        self._sync_manager: Optional[SyncManager] = None
        self._sc_user_info: Optional[dict] = None

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

    def browse_any_folder(self, initial: str = "") -> Optional[str]:
        """Diálogo nativo de carpeta que NO toca dest_folder (para escanear otra ubicación)."""
        if not self.window:
            return None
        try:
            import webview
            kwargs = {"directory": initial} if initial and os.path.isdir(initial) else {}
            result = self.window.create_file_dialog(webview.FOLDER_DIALOG, **kwargs)
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
        Re-registra la tarea programada de Windows (o el timer de
        systemd/launchd) con el nuevo intervalo, llamando al mismo script
        que usa el flujo manual (scripts/setup_task_scheduler.py).
        """
        try:
            minutes = max(5, min(1440, int(minutes)))
            self.save_settings({"soundcloud": {"sync_interval_minutes": minutes}})
            script = os.path.join(self._base_dir, "scripts", "setup_task_scheduler.py")
            result = subprocess.run(
                [sys.executable, script, "--register", "--interval-minutes", str(minutes)],
                capture_output=True, text=True, timeout=30,
            )
            ok = result.returncode == 0
            msg = result.stdout.strip() if ok else (result.stderr.strip() or result.stdout.strip())
            return {"ok": ok, "message": msg, "minutes": minutes}
        except Exception as e:
            logger.exception("Error registrando tarea programada")
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

        threshold = self.controller.get_config_value("duplicate_checker", {}).get("similarity_threshold", 85)
        self._sync_manager = SyncManager(
            oauth_token, client_id,
            self.controller.get_config_value("dest_folder", ""),
            SoundCloudHandler(),
            similarity_threshold=threshold,
            filename_pattern=self.controller.get_config_value("filename_pattern", "{artist} - {title}"),
            subfolder_by_artist=self.controller.get_config_value("subfolder_by_artist", False),
        )
        try:
            self._sync_manager.validate_credentials()
        except Exception:
            pass  # ya validamos arriba con el mismo token; no bloquear por esto

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

    def _match_candidates_like(self, like: dict) -> set[str]:
        """
        Variantes normalizadas de un like para comparar. Incluye el título
        SOLO además de "artista + título" porque en SoundCloud el campo
        artista es el uploader (sello/canal, p.ej. "GEWOONRAVES") mientras
        que el artista real vive dentro del título; el archivo en disco casi
        siempre está nombrado "ArtistaReal - Título".
        """
        artist = like.get("artist") or ""
        title = like.get("title") or ""
        cands = {_clean_for_match(f"{artist} {title}"), _clean_for_match(title)}
        return {c for c in cands if len(c) >= _MIN_MATCH_LEN}

    def _do_reconcile(self, folder: str, progress_cb) -> dict:
        history = self._sync_manager.history

        progress_cb(0, f"Escaneando {folder}…")
        files: list[tuple[Path, set[str]]] = []
        for p in Path(folder).rglob("*"):
            if p.is_file() and p.suffix.lower() in _AUDIO_EXTENSIONS:
                cands = {_clean_for_match(p.stem)}
                cands = {c for c in cands if len(c) >= _MIN_MATCH_LEN}
                if cands:
                    files.append((p, cands))
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
                like_cands = self._match_candidates_like(like)
                best_score, best_file = 0, None
                for file_path, file_cands in files:
                    for a in like_cands:
                        for b in file_cands:
                            score = max(fuzz.token_sort_ratio(a, b), fuzz.ratio(a, b))
                            if score > best_score:
                                best_score, best_file = score, file_path
                if best_file and best_score >= _RECONCILE_THRESHOLD:
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
