"""
Ventana de preview de likes de SoundCloud.
Muestra qué canciones están en los likes y cuál es su estado de descarga.
Permite seleccionar y descargar específicamente.
"""
import threading
import logging
from tkinter import messagebox
from pathlib import Path

import customtkinter as ctk

logger = logging.getLogger(__name__)


class LikesPreviewWindow(ctk.CTkFrame):
    """
    Panel que muestra los likes de SoundCloud con estado de descarga.
    Incluye filtros, búsqueda, y acciones (descargar, marcar como duplicado).
    """

    def __init__(self, master, sync_manager, downloader):
        """
        Args:
            master: Frame padre
            sync_manager: Instancia de SyncManager
            downloader: Handler de descargas
        """
        super().__init__(master, corner_radius=0, fg_color="transparent")
        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(0, weight=1)

        self.sync_manager = sync_manager
        self.downloader = downloader
        self._selected_tracks = set()

        # Header con búsqueda y filtros
        self._build_header()

        # Tabla con likes
        self._build_table()

        # Footer con acciones
        self._build_footer()

        # Cargar datos al iniciar
        self.after(100, self._load_likes)

    def _build_header(self):
        """Construye la barra de búsqueda y filtros."""
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=16, pady=12)
        header.grid_columnconfigure(1, weight=1)

        # Label
        ctk.CTkLabel(
            header, text="Mis Likes de SoundCloud",
            font=ctk.CTkFont(size=13, weight="bold")
        ).grid(row=0, column=0, sticky="w", pady=(0, 10))

        # Search box
        search_frame = ctk.CTkFrame(header, fg_color="transparent")
        search_frame.grid(row=1, column=0, columnspan=3, sticky="ew", pady=(0, 8))
        search_frame.grid_columnconfigure(0, weight=1)

        self._search_entry = ctk.CTkEntry(
            search_frame, placeholder_text="Buscar canción, artista..."
        )
        self._search_entry.grid(row=0, column=0, sticky="ew")
        self._search_entry.bind("<KeyRelease>", lambda e: self._filter_table())

        # Filter buttons
        filter_frame = ctk.CTkFrame(header, fg_color="transparent")
        filter_frame.grid(row=2, column=0, columnspan=3, sticky="ew")

        self._filter_var = ctk.StringVar(value="todos")
        filters = [
            ("Todos", "todos"),
            ("Descargados ✓", "descargados"),
            ("Pendientes ⏳", "pendientes"),
        ]

        for label, value in filters:
            ctk.CTkRadioButton(
                filter_frame, text=label, value=value,
                variable=self._filter_var,
                command=self._filter_table
            ).pack(side="left", padx=(0, 16))

        # Refresh button
        ctk.CTkButton(
            header, text="🔄 Actualizar",
            width=100, height=28,
            command=self._load_likes
        ).grid(row=2, column=3, sticky="e", padx=(8, 0))

    def _build_table(self):
        """Construye la tabla con likes."""
        # Container scrolleable con mejor soporte para muchos widgets
        scroll = ctk.CTkScrollableFrame(
            self, fg_color="transparent", label_text="Canciones"
        )
        scroll.grid(row=1, column=0, sticky="nsew", padx=16, pady=12)
        scroll.grid_columnconfigure(0, weight=1)

        # Headers
        headers_frame = ctk.CTkFrame(scroll, fg_color="#1f2937", corner_radius=4)
        headers_frame.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        headers_frame.grid_columnconfigure(2, weight=1)

        headers = [
            ("☑", 40),
            ("Estado", 80),
            ("Canción", 0),
            ("Artista", 150),
            ("Acciones", 100),
        ]

        for i, (text, width) in enumerate(headers):
            label = ctk.CTkLabel(
                headers_frame, text=text,
                text_color="#9ca3af",
                font=ctk.CTkFont(size=10, weight="bold")
            )
            label.grid(row=0, column=i, sticky="ew", padx=8, pady=8)
            if width > 0:
                headers_frame.grid_columnconfigure(i, minsize=width)

        # Frame contenedor de filas - sin sticky vertical para que crezca naturalmente
        self._table_frame = ctk.CTkFrame(scroll, fg_color="transparent")
        self._table_frame.grid(row=1, column=0, sticky="ew")
        self._table_frame.grid_columnconfigure(2, weight=1)

        self._table_rows = []
        self._scroll = scroll

    def _build_footer(self):
        """Construye la barra de acciones."""
        footer = ctk.CTkFrame(self, fg_color="transparent")
        footer.grid(row=2, column=0, sticky="ew", padx=16, pady=12)
        footer.grid_columnconfigure(1, weight=1)

        # Stats
        self._stats_label = ctk.CTkLabel(
            footer, text="Cargando...",
            text_color="#9ca3af", font=ctk.CTkFont(size=10)
        )
        self._stats_label.grid(row=0, column=0, sticky="w")

        # Progreso (hidden por defecto)
        self._progress_frame = ctk.CTkFrame(footer, fg_color="transparent")
        self._progress_frame.grid(row=0, column=1, sticky="ew", padx=(16, 0))
        self._progress_frame.grid_columnconfigure(0, weight=1)

        self._progress_bar = ctk.CTkProgressBar(self._progress_frame, height=4)
        self._progress_bar.set(0)
        self._progress_bar.grid(row=0, column=0, sticky="ew", pady=(0, 4))

        self._progress_label = ctk.CTkLabel(
            self._progress_frame, text="",
            text_color="#10b981", font=ctk.CTkFont(size=8)
        )
        self._progress_label.grid(row=1, column=0, sticky="w")
        self._progress_frame.grid_remove()  # Hidden

        # Botones
        buttons_frame = ctk.CTkFrame(footer, fg_color="transparent")
        buttons_frame.grid(row=0, column=2, sticky="e", padx=(16, 0))

        ctk.CTkButton(
            buttons_frame, text="Descargar seleccionados",
            fg_color="#10b981", hover_color="#059669",
            command=self._download_selected
        ).pack(side="right", padx=(8, 0))

        ctk.CTkButton(
            buttons_frame, text="Seleccionar todo",
            fg_color="#6b7280", hover_color="#4b5563",
            command=self._select_all
        ).pack(side="right", padx=(8, 0))

    def _load_likes(self):
        """Carga los likes del sync_manager."""
        if not self.sync_manager:
            self._stats_label.configure(text="Error: SyncManager no inicializado")
            return

        self._stats_label.configure(text="Cargando likes...")

        def load():
            try:
                self._likes = self.sync_manager.get_likes_with_status()
                logger.info(f"✓ Cargados {len(self._likes)} likes del sync_manager")
                self.after(0, self._render_table)
            except Exception as e:
                logger.error(f"Error cargando likes: {e}")
                self.after(0, lambda: self._stats_label.configure(
                    text=f"Error: {str(e)[:50]}"
                ))

        threading.Thread(target=load, daemon=True).start()

    def _render_table(self):
        """Renderiza la tabla con los likes."""
        # Limpiar filas anteriores
        for row_widget in self._table_rows:
            row_widget.destroy()
        self._table_rows = []
        self._selected_tracks = set()

        if not hasattr(self, '_likes'):
            return

        # Aplicar filtros
        filtered_likes = self._apply_filters(self._likes)

        logger.info(f"Renderizando {len(filtered_likes)} de {len(self._likes)} likes")

        # Renderizar filas
        for i, like in enumerate(filtered_likes):
            self._render_like_row(i, like)

        # Forzar actualización del layout
        self._table_frame.update_idletasks()

        # Actualizar stats
        downloaded = sum(1 for l in self._likes if l['downloaded'])
        total = len(self._likes)
        self._stats_label.configure(
            text=f"Total: {total} | Descargadas: {downloaded} | Pendientes: {total - downloaded}"
        )

    def _render_like_row(self, index: int, like: dict):
        """Renderiza una fila de la tabla."""
        row = ctk.CTkFrame(self._table_frame, fg_color="#111827", corner_radius=4)
        row.pack(fill="x", pady=4, padx=0)
        row.grid_columnconfigure(2, weight=1)

        # Checkbox
        var = ctk.BooleanVar(value=False)
        checkbox = ctk.CTkCheckBox(row, text="", variable=var)
        checkbox.grid(row=0, column=0, padx=8, pady=8)

        # Estado
        status_text = "✓ Descargada" if like['downloaded'] else "⏳ Pendiente"
        status_color = "#4ade80" if like['downloaded'] else "#fbbf24"
        status_label = ctk.CTkLabel(
            row, text=status_text, text_color=status_color,
            font=ctk.CTkFont(size=10)
        )
        status_label.grid(row=0, column=1, padx=8, pady=8)

        # Canción (título)
        title = ctk.CTkLabel(
            row, text=like['title'],
            text_color="#e5e7eb", anchor="w",
            font=ctk.CTkFont(size=10)
        )
        title.grid(row=0, column=2, sticky="ew", padx=8, pady=8)

        # Artista
        artist = ctk.CTkLabel(
            row, text=like['artist'],
            text_color="#9ca3af",
            font=ctk.CTkFont(size=9)
        )
        artist.grid(row=0, column=3, sticky="ew", padx=8, pady=8, minwidth=150)

        # Acciones
        actions_frame = ctk.CTkFrame(row, fg_color="transparent")
        actions_frame.grid(row=0, column=4, sticky="e", padx=8, pady=8)

        if not like['downloaded']:
            ctk.CTkButton(
                actions_frame, text="Descargar", width=80, height=24,
                font=ctk.CTkFont(size=9),
                command=lambda: self._download_single(like)
            ).pack(side="left", padx=(0, 4))

        ctk.CTkButton(
            actions_frame, text="⋯", width=30, height=24,
            font=ctk.CTkFont(size=10),
            fg_color="#6b7280", hover_color="#4b5563",
            command=lambda: self._show_track_menu(like)
        ).pack(side="left")

        # Store reference
        self._table_rows.append(row)

        # Bind checkbox change
        def on_checkbox_change():
            if var.get():
                self._selected_tracks.add(like['url'])
            else:
                self._selected_tracks.discard(like['url'])

        checkbox.configure(command=on_checkbox_change)

    def _apply_filters(self, likes: list) -> list:
        """Filtra los likes según búsqueda y estado."""
        search = self._search_entry.get().lower()
        filter_type = self._filter_var.get()

        result = []
        for like in likes:
            # Filtro de búsqueda
            if search:
                match = (
                    search in like['title'].lower() or
                    search in like['artist'].lower()
                )
                if not match:
                    continue

            # Filtro de estado
            if filter_type == "descargados" and not like['downloaded']:
                continue
            elif filter_type == "pendientes" and like['downloaded']:
                continue

            result.append(like)

        logger.debug(f"Filtrado: {len(likes)} -> {len(result)} (filter={filter_type}, search='{search}')")
        return result

    def _filter_table(self):
        """Re-renderiza la tabla con filtros aplicados."""
        self._render_table()

    def _select_all(self):
        """Selecciona todos los likes visibles."""
        if hasattr(self, '_likes'):
            filtered = self._apply_filters(self._likes)
            self._selected_tracks = {like['url'] for like in filtered}
            self._render_table()

    def _download_single(self, like: dict):
        """Descarga una canción específica."""
        self._selected_tracks = {like['url']}
        self._download_selected()

    def _download_selected(self):
        """Descarga todas las canciones seleccionadas."""
        if not self._selected_tracks:
            messagebox.showwarning("Sin selección", "Selecciona al menos una canción")
            return

        # Obtener tracks seleccionados
        selected_likes = [
            l for l in self._likes if l['url'] in self._selected_tracks
        ]

        if not selected_likes:
            messagebox.showwarning("Error", "No se encontraron canciones seleccionadas")
            return

        # Confirmar descarga
        count = len(selected_likes)
        response = messagebox.askyesno(
            "Confirmar descarga",
            f"¿Descargar {count} canción(es)?\n\n"
            f"Esto no marcará como duplicado,\n"
            f"descargará directamente sin sincronizar."
        )

        if not response:
            return

        # Ejecutar descarga en thread
        def download():
            self._perform_batch_download(selected_likes)

        threading.Thread(target=download, daemon=True).start()

    def _perform_batch_download(self, likes: list):
        """Ejecuta descarga en batch de múltiples canciones."""
        if not self.sync_manager or not self.downloader:
            self.after(0, lambda: messagebox.showerror(
                "Error", "SyncManager no inicializado"
            ))
            return

        # Mostrar progress bar
        self.after(0, self._show_progress_bar)

        logger.info(f"Iniciando descarga de {len(likes)} canciones...")
        downloaded = 0
        errors = 0

        for i, like in enumerate(likes):
            try:
                # Actualizar UI
                progress = int((i / len(likes)) * 100)
                msg = f"Descargando {i+1}/{len(likes)}: {like['artist']} - {like['title']}"
                self.after(0, lambda p=progress, m=msg: self._update_download_status(p, m))

                # Descargar
                output_path = self.sync_manager._build_output_path(
                    like['artist'], like['title']
                )
                file_path = self.downloader.download(
                    like['url'],
                    output_path,
                    quality_preset={
                        "sc_format": "bestaudio/best",
                        "yt_format": "bestaudio/best",
                        "convert_to": "mp3",
                        "bitrate": "320"
                    },
                    progress_callback=None
                )

                # Registrar en historial
                self.sync_manager.history.mark_downloaded(
                    like['url'],
                    like['title'],
                    like['artist'],
                    file_path,
                    platform="soundcloud"
                )

                downloaded += 1
                logger.info(f"✓ Descargada: {like['artist']} - {like['title']}")

            except Exception as e:
                errors += 1
                logger.error(f"Error descargando {like['artist']} - {like['title']}: {e}")

        # Finalizar
        self.after(0, lambda: self._on_batch_download_complete(downloaded, errors, len(likes)))

    def _show_progress_bar(self):
        """Muestra la barra de progreso."""
        self._progress_frame.grid()
        self._progress_bar.set(0)
        self._progress_label.configure(text="Iniciando descargas...")

    def _update_download_status(self, progress: int, message: str):
        """Actualiza status durante descarga."""
        self._progress_bar.set(progress / 100)
        self._progress_label.configure(text=f"{progress}% - {message[:50]}")

    def _on_batch_download_complete(self, downloaded: int, errors: int, total: int):
        """Callback cuando termina descarga en batch."""
        skipped = total - downloaded - errors

        msg = (
            f"✓ Descargas completadas\n\n"
            f"Éxito: {downloaded}/{total}\n"
            f"Errores: {errors}"
        )

        messagebox.showinfo("Descarga completa", msg)

        # Recargar likes para actualizar status
        self._load_likes()

        logger.info(f"Batch download: +{downloaded} ✓ | !{errors} ⚠️")

    def _show_track_menu(self, like: dict):
        """Muestra menú de opciones para una canción."""
        status = "descargada" if like['downloaded'] else "pendiente"

        msg = f"""
{like['artist']} - {like['title']}

Duración: {like['duration_ms'] // 1000 // 60} min
Género: {like['genre'] or 'No especificado'}
Estado: {status}
URL: {like['url'][:50]}...
        """

        messagebox.showinfo("Detalles de canción", msg.strip())
