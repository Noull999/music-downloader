"""
Ventana principal del Music Downloader.
Panel izquierdo: controles | Panel derecho: tabs Descargas / Logs
"""
import json
import logging
import os
import threading
from tkinter import filedialog, messagebox

import customtkinter as ctk

from download_manager import DownloadManager
from gui.settings import SettingsDialog
from gui.track_list import TrackListFrame
from gui.sync_window import SyncWindow
from models import TrackInfo, STATUS_PENDING, STATUS_DONE, STATUS_SKIP, STATUS_DOWNLOADING, STATUS_FETCHING, STATUS_ERROR
from quality.presets import get_preset, effective_extension
from url_detector import detect_handler, detect_platform_name
from utils.validators import parse_urls_from_text
from handlers.soundcloud_handler import SoundCloudHandler

logger = logging.getLogger(__name__)

_BASE = os.path.dirname(os.path.dirname(__file__))
CONFIG_PATH = os.path.join(_BASE, "config.json")
HISTORY_PATH = os.path.join(_BASE, "history.json")

_DEFAULT_CONFIG: dict = {
    "dest_folder": os.path.expanduser("~/Music"),
    "max_workers": 3,
    "quality_preset": "mp3_320",
    "filename_pattern": "{artist} - {title}",
    "subfolder_by_artist": False,
    "normalize_volume": False,
    "remove_silence": False,
    "embed_artwork": True,
    "embed_metadata": True,
    "oauth_token": "",
    "delay": 0.5,
}


class MainWindow(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("Music Downloader — YouTube & SoundCloud")
        self.geometry("1150x720")
        self.minsize(820, 560)

        self._config = self._load_config()
        self._history: set[str] = self._load_history()
        self._manager = DownloadManager()
        self._manager.start(self._config["max_workers"])

        self._build_ui()
        self._apply_config_to_ui()
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    # ------------------------------------------------------------------ #
    # UI                                                                   #
    # ------------------------------------------------------------------ #

    def _build_ui(self):
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(1, weight=1)

        # ── Panel izquierdo ──────────────────────────────────────────── #
        left = ctk.CTkFrame(self, width=300, corner_radius=0)
        left.grid(row=0, column=0, sticky="nsew")
        left.grid_propagate(False)
        left.grid_columnconfigure(0, weight=1)

        # Titulo
        ctk.CTkLabel(
            left, text="Music Downloader",
            font=ctk.CTkFont(size=18, weight="bold"),
        ).grid(row=0, column=0, padx=18, pady=(18, 2), sticky="w")

        ctk.CTkLabel(
            left, text="YouTube  &  SoundCloud",
            font=ctk.CTkFont(size=11), text_color="#6b7280",
        ).grid(row=1, column=0, padx=18, pady=(0, 14), sticky="w")

        # Entrada de URLs
        ctk.CTkLabel(left, text="Pegar links (uno por linea):").grid(
            row=2, column=0, padx=18, pady=(0, 2), sticky="w"
        )
        self._url_box = ctk.CTkTextbox(left, height=150)
        self._url_box.grid(row=3, column=0, padx=18, pady=(0, 8), sticky="ew")

        ctk.CTkButton(
            left, text="Procesar enlaces",
            command=self._on_process_urls,
        ).grid(row=4, column=0, padx=18, pady=(0, 4), sticky="ew")

        # Separador
        ctk.CTkFrame(left, height=1, fg_color="#374151").grid(
            row=5, column=0, padx=14, pady=10, sticky="ew"
        )

        # Carpeta destino
        ctk.CTkLabel(left, text="Carpeta de destino:").grid(
            row=6, column=0, padx=18, pady=(0, 2), sticky="w"
        )
        dest_row = ctk.CTkFrame(left, fg_color="transparent")
        dest_row.grid(row=7, column=0, padx=18, pady=(0, 8), sticky="ew")
        dest_row.grid_columnconfigure(0, weight=1)

        self._dest_lbl = ctk.CTkLabel(
            dest_row, text="", anchor="w",
            font=ctk.CTkFont(size=11), text_color="#9ca3af",
        )
        self._dest_lbl.grid(row=0, column=0, sticky="ew")
        ctk.CTkButton(
            dest_row, text="Examinar", width=80,
            command=self._on_browse,
        ).grid(row=0, column=1, padx=(6, 0))

        # Descargas paralelas
        ctk.CTkLabel(left, text="Descargas en paralelo:").grid(
            row=8, column=0, padx=18, pady=(0, 2), sticky="w"
        )
        par_row = ctk.CTkFrame(left, fg_color="transparent")
        par_row.grid(row=9, column=0, padx=18, pady=(0, 10), sticky="ew")
        par_row.grid_columnconfigure(0, weight=1)

        self._par_lbl = ctk.CTkLabel(par_row, text="3", width=24)
        self._par_lbl.grid(row=0, column=1, padx=(6, 0))
        self._par_slider = ctk.CTkSlider(
            par_row, from_=1, to=10, number_of_steps=9,
            command=self._on_parallel_change,
        )
        self._par_slider.grid(row=0, column=0, sticky="ew")

        # Botones de accion
        actions = [
            ("Descargar todo",         "#2563eb", "#1d4ed8", self._on_download_all),
            ("Descargar seleccionados","#374151", "#4b5563", self._on_download_selected),
        ]
        for r, (label, fg, hv, cmd) in enumerate(actions, start=10):
            ctk.CTkButton(
                left, text=label, fg_color=fg, hover_color=hv, command=cmd,
            ).grid(row=r, column=0, padx=18, pady=3, sticky="ew")

        self._pause_btn = ctk.CTkButton(
            left, text="Pausar",
            fg_color="#374151", hover_color="#4b5563",
            command=self._on_pause_resume,
        )
        self._pause_btn.grid(row=12, column=0, padx=18, pady=3, sticky="ew")

        ctk.CTkButton(
            left, text="Cancelar todo",
            fg_color="#7f1d1d", hover_color="#991b1b",
            command=self._on_cancel_all,
        ).grid(row=13, column=0, padx=18, pady=3, sticky="ew")

        ctk.CTkFrame(left, height=1, fg_color="#374151").grid(
            row=14, column=0, padx=14, pady=10, sticky="ew"
        )

        ctk.CTkButton(
            left, text="Configuracion",
            fg_color="transparent", border_width=1,
            command=self._on_settings,
        ).grid(row=15, column=0, padx=18, pady=(0, 8), sticky="ew")

        # Preset activo label
        self._preset_lbl = ctk.CTkLabel(
            left, text="", font=ctk.CTkFont(size=11), text_color="#6b7280",
        )
        self._preset_lbl.grid(row=16, column=0, padx=18, pady=(0, 4), sticky="w")

        # Status bar
        self._status_bar = ctk.CTkLabel(
            left, text="Listo.", anchor="w",
            font=ctk.CTkFont(size=11), text_color="#9ca3af",
        )
        self._status_bar.grid(row=17, column=0, padx=18, pady=(4, 18), sticky="ew")

        # ── Panel derecho ────────────────────────────────────────────── #
        right = ctk.CTkFrame(self, corner_radius=0)
        right.grid(row=0, column=1, sticky="nsew")
        right.grid_rowconfigure(0, weight=1)
        right.grid_columnconfigure(0, weight=1)

        self._tabs = ctk.CTkTabview(right)
        self._tabs.grid(row=0, column=0, sticky="nsew", padx=8, pady=8)
        self._tabs.grid_rowconfigure(0, weight=1)

        tab_dl = self._tabs.add("Descargas")
        tab_dl.grid_rowconfigure(0, weight=1)
        tab_dl.grid_columnconfigure(0, weight=1)

        self._track_list = TrackListFrame(
            tab_dl,
            on_download=self._on_single_download,
            on_cancel=self._on_single_cancel,
            fg_color="transparent",
        )
        self._track_list.grid(row=0, column=0, sticky="nsew")

        tab_log = self._tabs.add("Logs")
        tab_log.grid_rowconfigure(0, weight=1)
        tab_log.grid_columnconfigure(0, weight=1)

        self._log_box = ctk.CTkTextbox(tab_log, state="disabled")
        self._log_box.grid(row=0, column=0, sticky="nsew")

        tab_sync = self._tabs.add("Sincronizar")
        tab_sync.grid_rowconfigure(0, weight=1)
        tab_sync.grid_columnconfigure(0, weight=1)

        downloader = SoundCloudHandler()
        self._sync_window = SyncWindow(
            tab_sync,
            config_path=CONFIG_PATH,
            download_folder=self._config.get("dest_folder", ""),
            downloader=downloader,
        )
        self._sync_window.grid(row=0, column=0, sticky="nsew")

        self._install_log_handler()

    def _apply_config_to_ui(self):
        self._dest_lbl.configure(text=_shorten(self._config.get("dest_folder", "")))
        workers = int(self._config.get("max_workers", 3))
        self._par_slider.set(workers)
        self._par_lbl.configure(text=str(workers))
        self._update_preset_label()

    def _update_preset_label(self):
        preset = get_preset(self._config.get("quality_preset", "mp3_320"))
        self._preset_lbl.configure(text=f"Calidad: {preset['label']}")

    # ------------------------------------------------------------------ #
    # Handlers de eventos                                                  #
    # ------------------------------------------------------------------ #

    def _on_process_urls(self):
        text = self._url_box.get("1.0", "end")
        urls = parse_urls_from_text(text)
        if not urls:
            self._set_status("No se encontraron URLs validas de YouTube o SoundCloud.")
            return

        new_urls = [u for u in urls if not self._track_list.get_row(u)]
        if not new_urls:
            self._set_status("Todos los enlaces ya estan en la lista.")
            return

        self._set_status(f"Procesando {len(new_urls)} enlace(s)...")
        for url in new_urls:
            placeholder = TrackInfo(url=url, title="Cargando...", platform=detect_platform_name(url))
            self._track_list.add_track(placeholder)
            self._track_list.update_status(url, STATUS_FETCHING)
            threading.Thread(target=self._fetch_worker, args=(url,), daemon=True).start()

    def _fetch_worker(self, url: str):
        try:
            handler = detect_handler(url)
            tracks = handler.get_metadata(url)
        except (ValueError, RuntimeError) as exc:
            self.after(0, lambda e=str(exc): self._track_list.update_status(url, STATUS_ERROR, e))
            return
        except Exception as exc:
            logger.exception("fetch_worker error")
            self.after(0, lambda e=str(exc)[:120]: self._track_list.update_status(url, STATUS_ERROR, e))
            return

        if not tracks:
            self.after(0, lambda: self._track_list.update_status(url, STATUS_ERROR, "Sin resultados"))
            return

        first_meta = tracks[0]
        # Si la URL tenia playlist anidada, verificar si handler soporta playlist completa
        has_nested = hasattr(first_meta, "_playlist_url")

        self.after(0, lambda: self._on_fetched(url, tracks, has_nested))

    def _on_fetched(self, original_url: str, tracks, has_nested: bool):
        first = tracks[0]
        first_info = TrackInfo.from_metadata(first)
        first_info.status = STATUS_PENDING

        # Actualizar la fila del URL original
        row = self._track_list.get_row(original_url)
        if row:
            # Re-indexar si la URL canónica de la plataforma difiere de la URL pegada
            self._track_list.reindex_row(original_url, first_info.url)
            row.update_track_info(first_info)
            row.update_status(STATUS_PENDING)

        # Agregar tracks adicionales (playlist)
        for meta in tracks[1:]:
            if not self._track_list.get_row(meta.url):
                self._track_list.add_track(TrackInfo.from_metadata(meta))

        # Preguntar por playlist anidada (video + list=)
        if has_nested:
            self._ask_nested_playlist(original_url, first)

        total = len(self._track_list.get_all())
        self._set_status(f"{total} track(s) en la lista.")

    def _ask_nested_playlist(self, video_url: str, first_meta):
        """Pregunta al usuario si quiere agregar toda la playlist ademas del video."""
        playlist_url = getattr(first_meta, "_playlist_url", None)
        if not playlist_url:
            return

        answer = messagebox.askyesno(
            "Playlist detectada",
            f"Este video forma parte de una playlist.\n\n"
            f"¿Deseas agregar todos los tracks de la playlist a la lista?",
            parent=self,
        )
        if answer:
            threading.Thread(
                target=self._fetch_playlist_worker, args=(playlist_url,), daemon=True
            ).start()

    def _fetch_playlist_worker(self, playlist_url: str):
        try:
            handler = detect_handler(playlist_url)
            from handlers.youtube_handler import YouTubeHandler
            if isinstance(handler, YouTubeHandler):
                tracks = handler.get_playlist_tracks(playlist_url)
            else:
                tracks = handler.get_metadata(playlist_url)
        except Exception as exc:
            logger.warning("Error cargando playlist: %s", exc)
            return

        self.after(0, lambda: self._add_playlist_tracks(tracks))

    def _add_playlist_tracks(self, tracks):
        for meta in tracks:
            if not self._track_list.get_row(meta.url):
                self._track_list.add_track(TrackInfo.from_metadata(meta))
        self._set_status(f"{len(self._track_list.get_all())} track(s) en la lista.")

    def _on_browse(self):
        folder = filedialog.askdirectory(
            initialdir=self._config.get("dest_folder", ""),
            title="Seleccionar carpeta de destino",
        )
        if folder:
            self._config["dest_folder"] = folder
            self._dest_lbl.configure(text=_shorten(folder))
            self._sync_window.download_folder = folder
            self._save_config()

    def _on_parallel_change(self, value: float):
        n = int(value)
        self._par_lbl.configure(text=str(n))
        self._config["max_workers"] = n
        self._manager.set_max_workers(n)
        self._save_config()

    def _on_download_all(self):
        self._start_downloads(self._track_list.get_all())

    def _on_download_selected(self):
        selected = self._track_list.get_selected()
        if not selected:
            self._set_status("No hay tracks seleccionados.")
            return
        self._start_downloads(selected)

    def _on_single_download(self, track: TrackInfo):
        self._start_downloads([track])

    def _on_single_cancel(self, track: TrackInfo):
        self._manager.cancel_track(track.url)

    def _on_pause_resume(self):
        if self._manager.is_paused:
            self._manager.resume_all()
            self._pause_btn.configure(text="Pausar")
            self._set_status("Descargas reanudadas.")
        else:
            self._manager.pause_all()
            self._pause_btn.configure(text="Reanudar")
            self._set_status("Descargas pausadas.")

    def _on_cancel_all(self):
        self._manager.cancel_all()
        self._set_status("Cancelando todas las descargas...")

    def _on_settings(self):
        dlg = SettingsDialog(self, self._config)
        self.wait_window(dlg)
        self._save_config()
        self._update_preset_label()
        self._manager.start(self._config.get("max_workers", 3))

    def _on_close(self):
        self._manager.cancel_all()
        self._manager.shutdown()
        if self._sync_window.scheduler:
            self._sync_window.scheduler.stop()
        self._save_config()
        self.destroy()

    # ------------------------------------------------------------------ #
    # Descarga                                                             #
    # ------------------------------------------------------------------ #

    def _start_downloads(self, tracks: list[TrackInfo]):
        eligible = [
            t for t in tracks
            if t.status not in (STATUS_DOWNLOADING, STATUS_FETCHING, STATUS_DONE, STATUS_SKIP)
        ]
        if not eligible:
            self._set_status("Ningun track pendiente para descargar.")
            return

        dest = self._config.get("dest_folder", "")
        if not dest:
            self._set_status("Selecciona una carpeta de destino primero.")
            return

        self._set_status(f"Iniciando {len(eligible)} descarga(s)...")
        for track in eligible:
            self._submit_one(track, dest)

    def _submit_one(self, track: TrackInfo, dest_folder: str):
        url = track.url
        try:
            handler = detect_handler(url)
        except ValueError as exc:
            self._track_list.update_status(url, STATUS_ERROR, str(exc)[:80])
            return

        preset = get_preset(self._config.get("quality_preset", "mp3_320"))
        post_config = {
            "normalize_volume": self._config.get("normalize_volume", False),
            "remove_silence": self._config.get("remove_silence", False),
            "embed_artwork": self._config.get("embed_artwork", True),
            "embed_metadata": self._config.get("embed_metadata", True),
        }

        def on_progress(v: float):
            self.after(0, lambda: self._track_list.update_progress(url, v))

        def on_status(status: str, err: str):
            self.after(0, lambda s=status, e=err: self._handle_status(url, s, e))

        self._manager.submit_download(
            track=track,
            handler=handler,
            dest_folder=dest_folder,
            filename_pattern=self._config.get("filename_pattern", "{artist} - {title}"),
            subfolder_by_artist=self._config.get("subfolder_by_artist", False),
            quality_preset=preset,
            post_config=post_config,
            delay=float(self._config.get("delay", 0.5)),
            on_progress=on_progress,
            on_status=on_status,
            oauth_token=self._config.get("oauth_token", ""),
        )

    def _handle_status(self, url: str, status: str, error_msg: str):
        self._track_list.update_status(url, status, error_msg)

        if status == STATUS_DONE:
            row = self._track_list.get_row(url)
            if row and row.track.track_id:
                self._history.add(row.track.track_id)
                self._save_history()

        if status in (STATUS_DONE, STATUS_ERROR):
            self._refresh_status_bar()

    def _refresh_status_bar(self):
        tracks = self._track_list.get_all()
        done = sum(1 for t in tracks if t.status == STATUS_DONE)
        errors = sum(1 for t in tracks if t.status == STATUS_ERROR)
        total = len(tracks)
        parts = [f"Completados: {done}/{total}"]
        if errors:
            parts.append(f"Errores: {errors}")
        self._set_status("  |  ".join(parts))

    # ------------------------------------------------------------------ #
    # Config y persistencia                                                #
    # ------------------------------------------------------------------ #

    def _load_config(self) -> dict:
        if os.path.exists(CONFIG_PATH):
            try:
                with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                    return {**_DEFAULT_CONFIG, **json.load(f)}
            except Exception:
                pass
        return dict(_DEFAULT_CONFIG)

    def _save_config(self):
        try:
            # Preservar la sección soundcloud que maneja SyncWindow
            config_to_save = self._config.copy()

            # Si existe un config.json actual, preservar su sección soundcloud
            if os.path.exists(CONFIG_PATH):
                try:
                    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                        existing = json.load(f)
                        if "soundcloud" in existing:
                            config_to_save["soundcloud"] = existing["soundcloud"]
                        if "duplicate_checker" in existing:
                            config_to_save["duplicate_checker"] = existing["duplicate_checker"]
                except Exception:
                    pass

            with open(CONFIG_PATH, "w", encoding="utf-8") as f:
                json.dump(config_to_save, f, indent=2, ensure_ascii=False)
        except Exception as exc:
            logger.warning("No se pudo guardar config: %s", exc)

    def _load_history(self) -> set[str]:
        if os.path.exists(HISTORY_PATH):
            try:
                with open(HISTORY_PATH, "r", encoding="utf-8") as f:
                    return set(json.load(f))
            except Exception:
                pass
        return set()

    def _save_history(self):
        try:
            with open(HISTORY_PATH, "w", encoding="utf-8") as f:
                json.dump(list(self._history), f, ensure_ascii=False)
        except Exception as exc:
            logger.warning("No se pudo guardar historial: %s", exc)

    # ------------------------------------------------------------------ #
    # Helpers UI                                                           #
    # ------------------------------------------------------------------ #

    def _set_status(self, msg: str):
        self._status_bar.configure(text=msg)

    def _install_log_handler(self):
        handler = _TextboxLogHandler(self._log_box, self)
        handler.setFormatter(
            logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", "%H:%M:%S")
        )
        logging.getLogger().addHandler(handler)


class _TextboxLogHandler(logging.Handler):
    def __init__(self, box: ctk.CTkTextbox, win: ctk.CTk):
        super().__init__()
        self._box = box
        self._win = win

    def emit(self, record: logging.LogRecord):
        msg = self.format(record) + "\n"
        self._win.after(0, lambda m=msg: self._write(m))

    def _write(self, msg: str):
        self._box.configure(state="normal")
        self._box.insert("end", msg)
        self._box.see("end")
        self._box.configure(state="disabled")


def _shorten(path: str, n: int = 36) -> str:
    return ("..." + path[-(n - 3):]) if len(path) > n else path
