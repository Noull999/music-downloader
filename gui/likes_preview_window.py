"""
Ventana de likes de SoundCloud.
Muestra qué canciones están en los likes y su estado de descarga.
Permite filtrar, seleccionar y descargar individual o en lote.
"""
import threading
import logging
from tkinter import messagebox

import customtkinter as ctk

from models import TrackInfo, STATUS_DONE, STATUS_ERROR, STATUS_CANCELLED, STATUS_SKIP
from quality.presets import get_preset
from quality.post_processor import PostProcessor

logger = logging.getLogger(__name__)


class LikesPreviewWindow(ctk.CTkFrame):
    """
    Panel de likes de SoundCloud con filtros, búsqueda y descarga en lote.
    Usa DownloadManager si está disponible (pausa/cancelación reales);
    cae a un loop secuencial si no.
    """

    def __init__(self, master, sync_manager, downloader,
                 download_manager=None, config: dict = None):
        super().__init__(master, corner_radius=0, fg_color="transparent")
        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(0, weight=1)

        self.sync_manager = sync_manager
        self.downloader = downloader
        self.download_manager = download_manager
        self.config = config or {}

        self._selected_tracks: set[str] = set()
        # Cada elemento: (widget_row, BooleanVar, like_dict)
        self._table_rows: list[tuple] = []
        self._batch_urls: list[str] = []   # URLs en vuelo para cancelación

        self._build_header()
        self._build_table()
        self._build_footer()

        self.after(100, self._load_likes)

    # ── Construcción ────────────────────────────────────────────────────

    def _build_header(self):
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=16, pady=12)
        header.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(
            header, text="Mis Likes de SoundCloud",
            font=ctk.CTkFont(size=13, weight="bold")
        ).grid(row=0, column=0, sticky="w", pady=(0, 10))

        search_frame = ctk.CTkFrame(header, fg_color="transparent")
        search_frame.grid(row=1, column=0, columnspan=3, sticky="ew", pady=(0, 8))
        search_frame.grid_columnconfigure(0, weight=1)

        self._search_entry = ctk.CTkEntry(
            search_frame, placeholder_text="Buscar canción, artista..."
        )
        self._search_entry.grid(row=0, column=0, sticky="ew")
        self._search_entry.bind("<KeyRelease>", lambda e: self._filter_table())

        filter_frame = ctk.CTkFrame(header, fg_color="transparent")
        filter_frame.grid(row=2, column=0, columnspan=3, sticky="ew")

        self._filter_var = ctk.StringVar(value="todos")
        for label, value in [("Todos", "todos"), ("Descargados ✓", "descargados"),
                              ("Pendientes ⏳", "pendientes")]:
            ctk.CTkRadioButton(
                filter_frame, text=label, value=value,
                variable=self._filter_var, command=self._filter_table
            ).pack(side="left", padx=(0, 16))

        ctk.CTkButton(
            header, text="🔄 Actualizar",
            width=100, height=28, command=self._load_likes
        ).grid(row=2, column=3, sticky="e", padx=(8, 0))

    def _build_table(self):
        scroll = ctk.CTkScrollableFrame(
            self, fg_color="transparent", label_text="Canciones"
        )
        scroll.grid(row=1, column=0, sticky="nsew", padx=16, pady=12)
        scroll.grid_columnconfigure(0, weight=1)

        headers_frame = ctk.CTkFrame(scroll, fg_color="#1f2937", corner_radius=4)
        headers_frame.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        headers_frame.grid_columnconfigure(2, weight=1)

        for i, (text, width) in enumerate([("☑", 40), ("Estado", 80),
                                            ("Canción", 0), ("Artista", 150),
                                            ("Acciones", 100)]):
            lbl = ctk.CTkLabel(headers_frame, text=text, text_color="#9ca3af",
                               font=ctk.CTkFont(size=10, weight="bold"))
            lbl.grid(row=0, column=i, sticky="ew", padx=8, pady=8)
            if width > 0:
                lbl.grid_columnconfigure(0, minwidth=width)

        self._table_frame = ctk.CTkFrame(scroll, fg_color="transparent")
        self._table_frame.grid(row=1, column=0, sticky="ew")
        self._table_frame.grid_columnconfigure(2, weight=1)

    def _build_footer(self):
        footer = ctk.CTkFrame(self, fg_color="transparent")
        footer.grid(row=2, column=0, sticky="ew", padx=16, pady=12)
        footer.grid_columnconfigure(1, weight=1)

        self._stats_label = ctk.CTkLabel(
            footer, text="Cargando...",
            text_color="#9ca3af", font=ctk.CTkFont(size=10)
        )
        self._stats_label.grid(row=0, column=0, sticky="w")

        self._progress_frame = ctk.CTkFrame(footer, fg_color="transparent")
        self._progress_frame.grid(row=0, column=1, sticky="ew", padx=(16, 0))
        self._progress_frame.grid_columnconfigure(0, weight=1)

        self._progress_bar = ctk.CTkProgressBar(self._progress_frame, height=6)
        self._progress_bar.set(0)
        self._progress_bar.grid(row=0, column=0, sticky="ew", pady=(0, 4))

        self._progress_label = ctk.CTkLabel(
            self._progress_frame, text="",
            text_color="#10b981", font=ctk.CTkFont(size=9)
        )
        self._progress_label.grid(row=1, column=0, sticky="w")
        self._progress_frame.grid_remove()

        buttons_frame = ctk.CTkFrame(footer, fg_color="transparent")
        buttons_frame.grid(row=0, column=2, sticky="e", padx=(16, 0))

        self._cancel_batch_btn = ctk.CTkButton(
            buttons_frame, text="Cancelar",
            fg_color="#7f1d1d", hover_color="#991b1b",
            width=80, state="disabled",
            command=self._cancel_batch
        )
        self._cancel_batch_btn.pack(side="right", padx=(8, 0))

        ctk.CTkButton(
            buttons_frame, text="Descargar seleccionados",
            fg_color="#10b981", hover_color="#059669",
            command=self._download_selected
        ).pack(side="right", padx=(8, 0))

        ctk.CTkButton(
            buttons_frame, text="Deseleccionar todo",
            fg_color="#6b7280", hover_color="#4b5563",
            command=self._deselect_all
        ).pack(side="right", padx=(8, 0))

        ctk.CTkButton(
            buttons_frame, text="Seleccionar todo",
            fg_color="#6b7280", hover_color="#4b5563",
            command=self._select_all
        ).pack(side="right", padx=(8, 0))

    # ── Carga y renderizado ─────────────────────────────────────────────

    def _load_likes(self):
        if not self.sync_manager:
            self._stats_label.configure(text="Error: SyncManager no inicializado")
            return

        def load():
            try:
                self._likes = self.sync_manager.get_likes_with_status()
                self.after(0, self._render_table)
            except Exception as e:
                logger.error(f"Error cargando likes: {e}")
                self.after(0, lambda: self._stats_label.configure(
                    text=f"Error: {str(e)[:60]}"
                ))

        threading.Thread(target=load, daemon=True).start()

    def _render_table(self):
        for row_widget, _, _ in self._table_rows:
            row_widget.destroy()
        self._table_rows = []

        if not hasattr(self, '_likes'):
            return

        filtered = self._apply_filters(self._likes)
        for i, like in enumerate(filtered):
            self._render_like_row(i, like)

        downloaded = sum(1 for l in self._likes if l['downloaded'])
        total = len(self._likes)
        self._stats_label.configure(
            text=f"Total: {total} | Descargadas: {downloaded} | Pendientes: {total - downloaded}"
        )

    def _render_like_row(self, index: int, like: dict):
        row = ctk.CTkFrame(self._table_frame, fg_color="#111827", corner_radius=4)
        row.grid(row=index, column=0, sticky="ew", pady=4)
        row.grid_columnconfigure(2, weight=1)

        # Checkbox — refleja el estado actual de selección
        var = ctk.BooleanVar(value=like['url'] in self._selected_tracks)
        checkbox = ctk.CTkCheckBox(row, text="", variable=var)
        checkbox.grid(row=0, column=0, padx=8, pady=8)

        def on_change(url=like['url']):
            if var.get():
                self._selected_tracks.add(url)
            else:
                self._selected_tracks.discard(url)

        checkbox.configure(command=on_change)

        # Estado
        status_text = "✓ Descargada" if like['downloaded'] else "⏳ Pendiente"
        status_color = "#4ade80" if like['downloaded'] else "#fbbf24"
        ctk.CTkLabel(row, text=status_text, text_color=status_color,
                     font=ctk.CTkFont(size=10)).grid(row=0, column=1, padx=8, pady=8)

        # Título
        ctk.CTkLabel(row, text=like['title'], text_color="#e5e7eb",
                     anchor="w", font=ctk.CTkFont(size=10)
                     ).grid(row=0, column=2, sticky="ew", padx=8, pady=8)

        # Artista
        ctk.CTkLabel(row, text=like['artist'], text_color="#9ca3af",
                     font=ctk.CTkFont(size=9)
                     ).grid(row=0, column=3, sticky="ew", padx=8, pady=8, minwidth=150)

        # Acciones
        actions = ctk.CTkFrame(row, fg_color="transparent")
        actions.grid(row=0, column=4, sticky="e", padx=8, pady=8)

        if not like['downloaded']:
            ctk.CTkButton(
                actions, text="Descargar", width=80, height=24,
                font=ctk.CTkFont(size=9),
                command=lambda lk=like: self._download_single(lk)
            ).pack(side="left", padx=(0, 4))

        ctk.CTkButton(
            actions, text="⋯", width=30, height=24,
            font=ctk.CTkFont(size=10),
            fg_color="#6b7280", hover_color="#4b5563",
            command=lambda lk=like: self._show_track_info(lk)
        ).pack(side="left")

        self._table_rows.append((row, var, like))

    # ── Filtros ─────────────────────────────────────────────────────────

    def _apply_filters(self, likes: list) -> list:
        search = self._search_entry.get().lower()
        filter_type = self._filter_var.get()
        result = []
        for like in likes:
            if search and search not in like['title'].lower() and search not in like['artist'].lower():
                continue
            if filter_type == "descargados" and not like['downloaded']:
                continue
            if filter_type == "pendientes" and like['downloaded']:
                continue
            result.append(like)
        return result

    def _filter_table(self):
        self._render_table()

    # ── Selección ───────────────────────────────────────────────────────

    def _select_all(self):
        """Marca todos los visibles sin re-renderizar la tabla."""
        if not hasattr(self, '_likes'):
            return
        filtered_urls = {like['url'] for like in self._apply_filters(self._likes)}
        self._selected_tracks.update(filtered_urls)
        for _, var, like in self._table_rows:
            if like['url'] in filtered_urls:
                var.set(True)

    def _deselect_all(self):
        """Desmarca todos sin re-renderizar."""
        self._selected_tracks.clear()
        for _, var, _ in self._table_rows:
            var.set(False)

    # ── Descarga ────────────────────────────────────────────────────────

    def _download_single(self, like: dict):
        self._selected_tracks = {like['url']}
        for _, var, lk in self._table_rows:
            var.set(lk['url'] == like['url'])
        self._download_selected()

    def _download_selected(self):
        if not self._selected_tracks:
            messagebox.showwarning("Sin selección", "Selecciona al menos una canción")
            return

        if not hasattr(self, '_likes'):
            return

        selected_likes = [l for l in self._likes if l['url'] in self._selected_tracks]
        if not selected_likes:
            return

        count = len(selected_likes)
        if not messagebox.askyesno(
            "Confirmar descarga",
            f"¿Descargar {count} canción(es)?\n\n"
            f"Se usará la calidad configurada en Ajustes."
        ):
            return

        self._batch_urls = [l['url'] for l in selected_likes]
        self._cancel_batch_btn.configure(state="normal")

        if self.download_manager:
            threading.Thread(
                target=self._perform_batch_managed, args=(selected_likes,), daemon=True
            ).start()
        else:
            threading.Thread(
                target=self._perform_batch_sequential, args=(selected_likes,), daemon=True
            ).start()

    def _cancel_batch(self):
        """Cancela las descargas en vuelo."""
        if self.download_manager:
            for url in self._batch_urls:
                self.download_manager.cancel_track(url)
        self._cancel_batch_btn.configure(state="disabled")

    # ── Descarga vía DownloadManager (pausa/cancel reales) ──────────────

    def _perform_batch_managed(self, likes: list):
        from handlers.soundcloud_handler import SoundCloudHandler

        total = len(likes)
        lock = threading.Lock()
        results = {"done": 0, "error": 0, "pending": total}

        dest_folder = self.sync_manager.download_folder
        quality_preset = get_preset(self.config.get("quality_preset", "mp3_320"))
        filename_pattern = self.config.get("filename_pattern", "{artist} - {title}")
        subfolder = self.config.get("subfolder_by_artist", False)
        delay = float(self.config.get("delay", 0.5))
        oauth_token = self.config.get("soundcloud", {}).get("oauth_token", "")
        post_config = {
            "embed_artwork": self.config.get("embed_artwork", True),
            "embed_metadata": self.config.get("embed_metadata", True),
            "normalize_volume": self.config.get("normalize_volume", False),
            "remove_silence": self.config.get("remove_silence", False),
        }

        self.after(0, self._show_progress_bar)

        for like in likes:
            track = TrackInfo(
                url=like['url'],
                title=like['title'],
                artist=like['artist'],
                platform="SoundCloud",
                thumbnail_url=like.get('artwork_url', ''),
            )

            def make_callbacks(lk, tk):
                def on_progress(v):
                    pass  # progreso individual no mostrado en esta vista

                def on_status(status, err):
                    with lock:
                        results["pending"] -= 1
                        if status == STATUS_DONE:
                            results["done"] += 1
                            try:
                                self.sync_manager.history.mark_downloaded(
                                    lk['url'], lk['title'], lk['artist'],
                                    tk.local_path, platform="soundcloud"
                                )
                            except Exception as ex:
                                logger.warning("Error registrando en historial: %s", ex)
                        elif status in (STATUS_ERROR, STATUS_CANCELLED):
                            results["error"] += 1
                        completed = total - results["pending"]
                        is_done = results["pending"] == 0
                        done_n, err_n = results["done"], results["error"]

                    pct = int((completed / total) * 100)
                    msg = f"{lk['artist']} - {lk['title']}"
                    self.after(0, lambda p=pct, m=msg: self._update_download_status(p, m))
                    if is_done:
                        self.after(0, lambda d=done_n, e=err_n:
                                   self._on_batch_download_complete(d, e, total))

                return on_progress, on_status

            on_progress, on_status = make_callbacks(like, track)
            self.download_manager.submit_download(
                track=track,
                handler=self.downloader,
                dest_folder=dest_folder,
                filename_pattern=filename_pattern,
                subfolder_by_artist=subfolder,
                quality_preset=quality_preset,
                post_config=post_config,
                delay=delay,
                on_progress=on_progress,
                on_status=on_status,
                oauth_token=oauth_token,
            )

    # ── Descarga secuencial (fallback sin DownloadManager) ───────────────

    def _perform_batch_sequential(self, likes: list):
        quality_preset = get_preset(self.config.get("quality_preset", "mp3_320"))
        post_config = {
            "embed_artwork": self.config.get("embed_artwork", True),
            "embed_metadata": self.config.get("embed_metadata", True),
            "normalize_volume": self.config.get("normalize_volume", False),
            "remove_silence": self.config.get("remove_silence", False),
        }

        self.after(0, self._show_progress_bar)
        downloaded = 0
        errors = 0

        for i, like in enumerate(likes):
            if like['url'] not in self._batch_urls:
                continue  # fue cancelado

            progress = int((i / len(likes)) * 100)
            msg = f"Descargando {i + 1}/{len(likes)}: {like['artist']} - {like['title']}"
            self.after(0, lambda p=progress, m=msg: self._update_download_status(p, m))

            try:
                output_path = self.sync_manager._build_output_path(
                    like['artist'], like['title']
                )
                file_path = self.downloader.download(
                    like['url'], output_path, quality_preset,
                    progress_callback=None, cancel_check=None
                )

                if file_path:
                    # Embeber carátula y metadatos
                    pp = PostProcessor(post_config)
                    pp.process(file_path, {
                        "title": like['title'], "artist": like['artist'],
                        "album": "", "year": "",
                    }, like.get('artwork_url', ''))

                    self.sync_manager.history.mark_downloaded(
                        like['url'], like['title'], like['artist'],
                        file_path, platform="soundcloud"
                    )
                    downloaded += 1
            except Exception as e:
                errors += 1
                logger.error("Error descargando %s - %s: %s",
                             like['artist'], like['title'], e)

        self.after(0, lambda: self._on_batch_download_complete(downloaded, errors, len(likes)))

    # ── Callbacks de progreso ───────────────────────────────────────────

    def _show_progress_bar(self):
        self._progress_frame.grid()
        self._progress_bar.set(0)
        self._progress_label.configure(text="Iniciando descargas...")

    def _update_download_status(self, progress: int, message: str):
        self._progress_bar.set(progress / 100)
        self._progress_label.configure(text=f"{progress}% — {message[:55]}")

    def _on_batch_download_complete(self, downloaded: int, errors: int, total: int):
        self._cancel_batch_btn.configure(state="disabled")
        self._batch_urls = []
        self._progress_bar.set(1.0)
        messagebox.showinfo(
            "Descarga completa",
            f"✓ Descargas completadas\n\n"
            f"Éxito: {downloaded}/{total}\n"
            f"Errores: {errors}"
        )
        self._load_likes()

    # ── Menú de detalles ────────────────────────────────────────────────

    def _show_track_info(self, like: dict):
        dur_s = like.get('duration_ms', 0) // 1000
        m, s = divmod(dur_s, 60)
        messagebox.showinfo(
            f"{like['artist']} — {like['title']}",
            f"Duración: {m}:{s:02d}\n"
            f"Género: {like.get('genre') or 'No especificado'}\n"
            f"Estado: {'Descargada' if like['downloaded'] else 'Pendiente'}\n"
            f"URL: {like['url'][:60]}..."
        )
