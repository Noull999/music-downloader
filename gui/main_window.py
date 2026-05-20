"""
Ventana principal del Music Downloader.
Panel izquierdo: controles | Panel derecho: tabs Descargas / Logs
Integra UIController para centralizar config/historial, StatusBar para mejor feedback.
"""
import logging
import os
import threading
from tkinter import filedialog, messagebox

import customtkinter as ctk

from download_manager import DownloadManager
from gui.activity_panel import ActivityPanel
from gui.settings import SettingsDialog
from gui.track_list import TrackListFrame
from gui.sync_window import SyncWindow
from gui.ui_controller import UIController
from gui.status_bar import StatusBar
from gui.themes import ThemeManager
from models import TrackInfo, STATUS_PENDING, STATUS_DONE, STATUS_SKIP, STATUS_DOWNLOADING, STATUS_FETCHING, STATUS_ERROR
from quality.presets import get_preset, effective_extension
from url_detector import detect_handler, detect_platform_name
from utils.validators import parse_urls_from_text
from handlers.soundcloud_handler import SoundCloudHandler

logger = logging.getLogger(__name__)

_BASE = os.path.dirname(os.path.dirname(__file__))


class MainWindow(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("Music Downloader — YouTube & SoundCloud")
        self.geometry("1150x720")
        self.minsize(820, 560)

        # Flag para evitar callbacks mientras se cierra
        self._closing = False

        # Centralizar config y historial via UIController
        self._ui_controller = UIController(base_dir=_BASE)
        self._manager = DownloadManager()
        self._manager.start(self._ui_controller.get_config_value("max_workers"))

        # Tema
        self._theme_manager = ThemeManager()
        initial_theme = self._ui_controller.get_config_value("theme", "dark")
        self._theme_manager.switch_theme(initial_theme)
        self._set_appearance_mode(initial_theme)

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
        left = ctk.CTkFrame(self, width=300, corner_radius=0, fg_color="#0a0a0a")
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
        ).grid(row=1, column=0, padx=18, pady=(0, 10), sticky="w")

        # ── Tarjeta SoundCloud (función principal) ───────────────────── #
        sc_card = ctk.CTkFrame(left, fg_color="#1a1a1a", corner_radius=8)
        sc_card.grid(row=2, column=0, padx=14, pady=(0, 6), sticky="ew")
        sc_card.grid_columnconfigure(0, weight=1)

        card_hdr = ctk.CTkFrame(sc_card, fg_color="transparent")
        card_hdr.grid(row=0, column=0, sticky="ew", padx=12, pady=(10, 4))
        card_hdr.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            card_hdr, text="SoundCloud Sync",
            font=ctk.CTkFont(size=12, weight="bold"),
        ).grid(row=0, column=0, sticky="w")

        ctk.CTkButton(
            card_hdr, text="Configurar →", width=88, height=22,
            font=ctk.CTkFont(size=10),
            fg_color="transparent", border_width=1,
            command=lambda: self._tabs.set("Sincronizar"),
        ).grid(row=0, column=1, sticky="e")

        self._sc_status_lbl = ctk.CTkLabel(
            sc_card, text="○ Sin conexión",
            text_color="#6b7280", font=ctk.CTkFont(size=10), anchor="w",
        )
        self._sc_status_lbl.grid(row=1, column=0, padx=12, pady=(0, 8), sticky="ew")

        sc_btns = ctk.CTkFrame(sc_card, fg_color="transparent")
        sc_btns.grid(row=2, column=0, sticky="ew", padx=12, pady=(0, 10))
        sc_btns.grid_columnconfigure((0, 1), weight=1)

        ctk.CTkButton(
            sc_btns, text="Sincronizar",
            height=28, font=ctk.CTkFont(size=10),
            command=lambda: self._sync_window._on_sync_manual(),
        ).grid(row=0, column=0, sticky="ew", padx=(0, 4))

        ctk.CTkButton(
            sc_btns, text="Ver mis Likes",
            height=28, font=ctk.CTkFont(size=10),
            fg_color="#dc2626", hover_color="#b91c1c",
            command=lambda: self._sync_window._on_show_likes_preview(),
        ).grid(row=0, column=1, sticky="ew", padx=(4, 0))

        # Separador
        ctk.CTkFrame(left, height=1, fg_color="#2d2d2d").grid(
            row=3, column=0, padx=14, pady=8, sticky="ew"
        )

        # ── Panel de actividad (real-time downloads) ──────────────────── #
        self._activity_panel = ActivityPanel(left, height=180)
        self._activity_panel.grid(row=4, column=0, padx=14, pady=(0, 8), sticky="ew")

        # Separador
        ctk.CTkFrame(left, height=1, fg_color="#2d2d2d").grid(
            row=5, column=0, padx=14, pady=8, sticky="ew"
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


        ctk.CTkFrame(left, height=1, fg_color="#2d2d2d").grid(
            row=16, column=0, padx=14, pady=10, sticky="ew"
        )

        ctk.CTkButton(
            left, text="Configuracion",
            fg_color="transparent", border_width=1,
            command=self._on_settings,
        ).grid(row=17, column=0, padx=18, pady=(0, 8), sticky="ew")

        ctk.CTkButton(
            left, text="📥 Importar mis Likes",
            fg_color="transparent", border_width=1,
            command=self._on_import_likes,
        ).grid(row=18, column=0, padx=18, pady=(0, 8), sticky="ew")

        ctk.CTkButton(
            left, text="👁️ Ver Mis Likes",
            fg_color="transparent", border_width=1,
            command=self._on_view_likes,
        ).grid(row=19, column=0, padx=18, pady=(0, 8), sticky="ew")

        ctk.CTkButton(
            left, text="📊 Ver BD de Likes (341)",
            fg_color="transparent", border_width=1,
            command=self._on_view_db,
        ).grid(row=20, column=0, padx=18, pady=(0, 8), sticky="ew")

        # Preset activo label
        self._preset_lbl = ctk.CTkLabel(
            left, text="", font=ctk.CTkFont(size=11), text_color="#6b7280",
        )
        self._preset_lbl.grid(row=21, column=0, padx=18, pady=(0, 4), sticky="w")

        # Status bar mejorado
        self._status_bar = StatusBar(left)
        self._status_bar.grid(row=20, column=0, padx=18, pady=(4, 18), sticky="ew")

        # ── Panel derecho ────────────────────────────────────────────── #
        right = ctk.CTkFrame(self, corner_radius=0, fg_color="#0f0f0f")
        right.grid(row=0, column=1, sticky="nsew")
        right.grid_rowconfigure(0, weight=1)
        right.grid_columnconfigure(0, weight=1)

        self._tabs = ctk.CTkTabview(right)
        self._tabs.grid(row=0, column=0, sticky="nsew", padx=8, pady=8)
        self._tabs.grid_rowconfigure(0, weight=1)

        tab_dl = self._tabs.add("Descargas")
        tab_dl.grid_rowconfigure(1, weight=1)
        tab_dl.grid_columnconfigure(0, weight=1)

        # ── URL Input Section ────────────────────────────────────────── #
        url_section = ctk.CTkFrame(tab_dl, fg_color="transparent")
        url_section.grid(row=0, column=0, sticky="ew", padx=8, pady=(8, 4))
        url_section.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            url_section, text="Descargar por link:",
            font=ctk.CTkFont(size=11, weight="bold"),
        ).grid(row=0, column=0, sticky="w", pady=(0, 6))

        self._url_box = ctk.CTkTextbox(url_section, height=80)
        self._url_box.grid(row=1, column=0, sticky="ew", pady=(0, 6))

        btn_row = ctk.CTkFrame(url_section, fg_color="transparent")
        btn_row.grid(row=2, column=0, sticky="ew", pady=(0, 8))
        btn_row.grid_columnconfigure(0, weight=1)

        ctk.CTkButton(
            btn_row, text="Procesar enlaces",
            command=self._on_process_urls,
        ).grid(row=0, column=0, sticky="ew", padx=(0, 8))

        # Descargas en paralelo
        par_frame = ctk.CTkFrame(btn_row, fg_color="transparent")
        par_frame.grid(row=0, column=1, sticky="ew")
        par_frame.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            par_frame, text="Paralelo:",
            font=ctk.CTkFont(size=9),
        ).grid(row=0, column=0, sticky="e", padx=(0, 4))

        self._par_lbl = ctk.CTkLabel(par_frame, text="3", width=20, font=ctk.CTkFont(size=9))
        self._par_lbl.grid(row=0, column=2, padx=(4, 0))

        self._par_slider = ctk.CTkSlider(
            par_frame, from_=1, to=10, number_of_steps=9,
            command=self._on_parallel_change, height=20,
        )
        self._par_slider.grid(row=0, column=1, sticky="ew", padx=4, ipadx=30)

        # ── Track List ───────────────────────────────────────────────── #
        self._track_list = TrackListFrame(
            tab_dl,
            on_download=self._on_single_download,
            on_cancel=self._on_single_cancel,
            fg_color="transparent",
        )
        self._track_list.grid(row=1, column=0, sticky="nsew", pady=(4, 0))

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
            config_path=os.path.join(_BASE, "config.json"),
            download_folder=self._ui_controller.get_config_value("dest_folder", ""),
            downloader=downloader,
            download_manager=self._manager,
            on_status_update=self._on_sc_status_update,
            activity_panel=self._activity_panel,
        )
        self._sync_window.grid(row=0, column=0, sticky="nsew")

        self._install_log_handler()

    def _apply_config_to_ui(self):
        self._dest_lbl.configure(text=_shorten(self._ui_controller.get_config_value("dest_folder", "")))
        workers = int(self._ui_controller.get_config_value("max_workers", 3))
        self._par_slider.set(workers)
        self._par_lbl.configure(text=str(workers))
        self._update_preset_label()
        # Si hay credenciales guardadas, abrir directamente en Sincronizar
        sc = self._ui_controller.get_config_value("soundcloud", {})
        if sc.get("oauth_token") and sc.get("client_id"):
            self._tabs.set("Sincronizar")

    def _update_preset_label(self):
        preset = get_preset(self._ui_controller.get_config_value("quality_preset", "mp3_320"))
        self._preset_lbl.configure(text=f"Calidad: {preset['label']}")

    # ------------------------------------------------------------------ #
    # Handlers de eventos                                                  #
    # ------------------------------------------------------------------ #

    def _on_process_urls(self):
        text = self._url_box.get("1.0", "end")
        urls = parse_urls_from_text(text)
        if not urls:
            self._status_bar.set_text("No se encontraron URLs validas de YouTube o SoundCloud.")
            return

        new_urls = [u for u in urls if not self._track_list.get_row(u)]
        if not new_urls:
            self._status_bar.set_text("Todos los enlaces ya estan en la lista.")
            return

        self._status_bar.set_text(f"Procesando {len(new_urls)} enlace(s)...")
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
        self._status_bar.set_text(f"{total} track(s) en la lista.")

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
        """Agrega filas por lotes para no bloquear el hilo principal."""
        pending = [m for m in tracks if not self._track_list.get_row(m.url)]
        if not pending:
            return

        def add_chunk(i=0):
            if self._closing:
                return
            # Agregar 20 filas a la vez
            chunk = pending[i:i + 20]
            for meta in chunk:
                self._track_list.add_track(TrackInfo.from_metadata(meta))

            # Si hay más, agenda el siguiente lote
            if i + 20 < len(pending):
                self.after(10, lambda: add_chunk(i + 20))
            else:
                self._status_bar.set_text(
                    f"{len(self._track_list.get_all())} track(s) en la lista."
                )

        add_chunk()

    def _on_browse(self):
        folder = filedialog.askdirectory(
            initialdir=self._ui_controller.get_config_value("dest_folder", ""),
            title="Seleccionar carpeta de destino",
        )
        if folder:
            self._ui_controller.set_config_value("dest_folder", folder)
            self._dest_lbl.configure(text=_shorten(folder))
            self._sync_window.download_folder = folder

    def _on_parallel_change(self, value: float):
        n = int(value)
        self._par_lbl.configure(text=str(n))
        self._ui_controller.set_config_value("max_workers", n)
        self._manager.set_max_workers(n)

    def _on_single_download(self, track: TrackInfo):
        self._start_downloads([track])

    def _on_single_cancel(self, track: TrackInfo):
        self._manager.cancel_track(track.url)
        self._activity_panel.log(f"⊗ Cancelado: {track.title[:50]}")

    def _on_pause_resume(self):
        if self._manager.is_paused:
            self._manager.resume_all()
            self._status_bar.mark_downloading()
            self._activity_panel.log("▶ Descargas reanudadas")
        else:
            self._manager.pause_all()
            self._status_bar.mark_paused()
            self._activity_panel.log("⏸ Descargas pausadas")

    def _on_cancel_all(self):
        self._manager.cancel_all()
        self._status_bar.mark_idle()
        self._activity_panel.log("⊗ Cancelando todas las descargas...")

    def _on_settings(self):
        config_dict = self._ui_controller.get_config()

        def on_settings_save(updates: dict):
            """Callback para guardar cambios de configuración."""
            for key, value in updates.items():
                self._ui_controller.set_config_value(key, value)

        dlg = SettingsDialog(self, config_dict, on_save_callback=on_settings_save)
        self.wait_window(dlg)
        self._update_preset_label()
        self._manager.start(self._ui_controller.get_config_value("max_workers", 3))

    def _on_import_likes(self):
        """Importa tus likes de SoundCloud como 'ya descargados'."""
        from tkinter import messagebox

        self._status_bar.set_text("📥 Importando likes de SoundCloud...", "#3b82f6")
        self.update()

        result = self._ui_controller.import_soundcloud_likes()

        if result['success']:
            msg = f"✅ Importación completada:\n\n"
            msg += f"✓ Importados: {result['imported']} likes\n"
            if result['skipped'] > 0:
                msg += f"⊘ Omitidos: {result['skipped']} (ya existían)\n"

            messagebox.showinfo("Importar Likes", msg)
            self._status_bar.mark_idle()
            self._activity_panel.log(f"✅ Importados {result['imported']} likes de SoundCloud")
        else:
            messagebox.showerror("Error", f"❌ Error en importación:\n{result['error']}")
            self._status_bar.mark_error("Error importando likes")
            self._activity_panel.log(f"❌ Error: {result['error']}")

    def _on_batch_download(self, tracks: list):
        """Inicia descarga de un lote de tracks."""
        if not tracks:
            return
        self._start_downloads(tracks)

    def _on_view_likes(self):
        """Abre ventana para ver y descargar tus likes de SoundCloud."""
        from gui.likes_viewer_window import LikesViewerWindow
        LikesViewerWindow(self, self._ui_controller)

    def _on_view_db(self):
        """Abre ventana para ver y descargar likes de la BD."""
        from gui.db_viewer_window import DBViewerWindow
        DBViewerWindow(self, self._ui_controller)

    def _on_close(self):
        try:
            logger.info("Cerrando aplicación...")
            self._closing = True  # Evitar callbacks mientras se limpia
            self._manager.cancel_all()
            self._manager.shutdown()
            if self._sync_window and self._sync_window.scheduler:
                self._sync_window.scheduler.stop()
            logger.info("Aplicación cerrada")
        except Exception as e:
            logger.error(f"Error al cerrar: {e}", exc_info=True)
        finally:
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
            self._status_bar.set_text("Ningun track pendiente para descargar.")
            return

        dest = self._ui_controller.get_config_value("dest_folder", "")
        if not dest:
            self._status_bar.set_text("Selecciona una carpeta de destino primero.")
            return

        self._status_bar.set_text(f"Iniciando {len(eligible)} descarga(s)...")
        self._activity_panel.log(f"→ Iniciando {len(eligible)} descarga(s)...")
        for idx, track in enumerate(eligible, 1):
            title = track.title if track.title != "Cargando..." else track.url.split("/")[-1]
            self._activity_panel.log(f"⬇ [{idx}/{len(eligible)}] {title[:60]}...")
            self._submit_one(track, dest, idx, len(eligible))

    def _submit_one(self, track: TrackInfo, dest_folder: str, idx: int = 0, total: int = 0):
        url = track.url
        try:
            handler = detect_handler(url)
        except ValueError as exc:
            self._track_list.update_status(url, STATUS_ERROR, str(exc)[:80])
            return

        preset = get_preset(self._ui_controller.get_config_value("quality_preset", "mp3_320"))
        post_config = {
            "normalize_volume": self._ui_controller.get_config_value("normalize_volume", False),
            "remove_silence": self._ui_controller.get_config_value("remove_silence", False),
            "embed_artwork": self._ui_controller.get_config_value("embed_artwork", True),
            "embed_metadata": self._ui_controller.get_config_value("embed_metadata", True),
        }

        counter_str = f"[{idx}/{total}] " if total > 0 else ""

        def on_progress(v: float):
            if not self._closing:
                try:
                    self.after(0, lambda: self._track_list.update_progress(url, v))
                except Exception:
                    pass  # Ignore errors if widget is destroyed

        def on_status(status: str, err: str):
            def log_status():
                if not self._closing:
                    self._handle_status(url, status, err)
                    try:
                        title = track.title if track.title != "Cargando..." else url.split("/")[-1]
                        status_emoji = {
                            STATUS_DOWNLOADING: "⬇",
                            STATUS_DONE: "✓",
                            STATUS_ERROR: "✗",
                            STATUS_SKIP: "⊘",
                            STATUS_FETCHING: "🔍",
                        }.get(status, "•")
                        self._activity_panel.log(f"{status_emoji} {counter_str}{title[:50]}")
                    except Exception:
                        pass  # Ignore logging errors
            try:
                self.after(0, log_status)
            except Exception:
                pass  # Ignore after() errors if widget is destroyed

        self._manager.submit_download(
            track=track,
            handler=handler,
            dest_folder=dest_folder,
            filename_pattern=self._ui_controller.get_config_value("filename_pattern", "{artist} - {title}"),
            subfolder_by_artist=self._ui_controller.get_config_value("subfolder_by_artist", False),
            quality_preset=preset,
            post_config=post_config,
            delay=float(self._ui_controller.get_config_value("delay", 0.5)),
            on_progress=on_progress,
            on_status=on_status,
            oauth_token=(self._ui_controller.get_config_value("soundcloud", {}).get("oauth_token", "")
                         or self._ui_controller.get_config_value("oauth_token", "")),
        )

    def _handle_status(self, url: str, status: str, error_msg: str):
        # Evitar callbacks mientras se cierra la app
        if self._closing:
            logger.debug(f"Ignoring status callback (app closing): {status}")
            return

        try:
            self._track_list.update_status(url, status, error_msg)

            if status == STATUS_DONE:
                try:
                    row = self._track_list.get_row(url)
                    if row:
                        thread = threading.Thread(
                            target=self._ui_controller.record_download,
                            args=(row.track,),
                            daemon=True
                        )
                        thread.start()
                except Exception as rec_exc:
                    logger.error(f"Error recording download: {rec_exc}", exc_info=True)

            if status in (STATUS_DONE, STATUS_ERROR):
                thread = threading.Thread(
                    target=self._refresh_status_bar,
                    daemon=True
                )
                thread.start()
        except Exception as e:
            logger.exception(f"Error in _handle_status for {url}: {e}")

    def _refresh_status_bar(self):
        try:
            tracks = self._track_list.get_all()
            done = sum(1 for t in tracks if t.status == STATUS_DONE)
            errors = sum(1 for t in tracks if t.status == STATUS_ERROR)
            total = len(tracks)
            if total == 0:
                self._status_bar.set_text("Listo")
            else:
                parts = [f"Completados: {done}/{total}"]
                if errors:
                    parts.append(f"Errores: {errors}")
                self._status_bar.set_text("  |  ".join(parts))
        except Exception as e:
            logger.exception(f"Error refreshing status bar: {e}")


    # ------------------------------------------------------------------ #
    # Helpers UI                                                           #
    # ------------------------------------------------------------------ #

    def _on_sc_status_update(self, user_info: dict):
        """Actualiza la tarjeta SoundCloud del panel izquierdo tras verificar credenciales."""
        self._sc_status_lbl.configure(
            text=f"● {user_info['username']}  |  {user_info['likes_count']} likes",
            text_color="#4ade80",
        )

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
