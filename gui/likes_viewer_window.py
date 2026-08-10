"""
Ventana para ver, buscar y descargar tus likes de SoundCloud.
"""
import tkinter as tk
from tkinter import ttk, messagebox
import customtkinter as ctk

class LikesViewerWindow(ctk.CTkToplevel):
    """Ventana para ver y descargar likes de SoundCloud."""

    def __init__(self, master, ui_controller):
        super().__init__(master)
        self.title("Ver Mis Likes - SoundCloud")
        self.geometry("900x600")
        # CTkToplevel en Windows se re-muestra con delay y queda DETRÁS de la
        # ventana principal; forzarla al frente.
        self.transient(master)
        self.lift()
        self.focus_force()
        self.attributes("-topmost", True)
        self.after(400, lambda: self.attributes("-topmost", False))
        self.ui_controller = ui_controller
        self._selected_urls = set()
        self._all_likes = []

        self._build_ui()
        self._load_likes()

    def _build_ui(self):
        # Header con búsqueda
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", padx=10, pady=10)

        ctk.CTkLabel(header, text="Mis Likes de SoundCloud",
                    font=("Arial", 16, "bold")).pack(side="left")

        # Buscador en tiempo real
        search_frame = ctk.CTkFrame(self, fg_color="transparent")
        search_frame.pack(fill="x", padx=10, pady=5)

        ctk.CTkLabel(search_frame, text="Buscar:").pack(side="left", padx=5)
        self.search_var = tk.StringVar()
        self.search_var.trace("w", self._on_search)
        search_entry = ctk.CTkEntry(search_frame, textvariable=self.search_var,
                                    placeholder_text="Artista o canción...")
        search_entry.pack(side="left", fill="x", expand=True, padx=5)

        # Tabla con scrollbar
        table_frame = ctk.CTkFrame(self)
        table_frame.pack(fill="both", expand=True, padx=10, pady=5)

        # Crear treeview
        self.tree = ttk.Treeview(table_frame, height=20, columns=("Artist", "Title", "Duration"))
        self.tree.heading("#0", text="☐")
        self.tree.heading("Artist", text="Artista")
        self.tree.heading("Title", text="Canción")
        self.tree.heading("Duration", text="Duración")

        self.tree.column("#0", width=40)
        self.tree.column("Artist", width=200)
        self.tree.column("Title", width=450)
        self.tree.column("Duration", width=120)

        # Scrollbar
        scrollbar = ttk.Scrollbar(table_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscroll=scrollbar.set)

        # Bind click para seleccionar
        self.tree.bind("<Button-1>", self._on_tree_click)

        self.tree.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        # Footer con botones
        footer = ctk.CTkFrame(self, fg_color="transparent")
        footer.pack(fill="x", padx=10, pady=10)

        self.count_label = ctk.CTkLabel(footer, text="Seleccionadas: 0")
        self.count_label.pack(side="left", padx=5)

        ctk.CTkButton(footer, text="Seleccionar Todo",
                     command=self._select_all, width=150).pack(side="left", padx=5)

        ctk.CTkButton(footer, text="Deseleccionar Todo",
                     command=self._deselect_all, width=150).pack(side="left", padx=5)

        ctk.CTkButton(footer, text="Descargar Seleccionadas",
                     command=self._download_selected, width=200,
                     fg_color="green").pack(side="right", padx=5)

    def _load_likes(self):
        """Carga los likes desde SoundCloud API."""
        try:
            self.title("Cargando likes...")
            self.update()

            # Obtener likes desde el API
            from sync.soundcloud_api import SoundCloudAPIClient

            oauth_token = self.ui_controller.get_config_value("soundcloud", {}).get("oauth_token", "")
            client_id = self.ui_controller.get_config_value("soundcloud", {}).get("client_id", "")

            if not oauth_token or not client_id:
                messagebox.showerror("Error", "Credenciales no configuradas")
                self.destroy()
                return

            api = SoundCloudAPIClient(oauth_token, client_id)

            # Validar credenciales primero
            user_info = api.validate_credentials()
            if not user_info:
                messagebox.showerror("Error", "No se pudieron validar las credenciales")
                self.destroy()
                return

            likes = api.get_likes()

            self._all_likes = likes
            self._render_likes(likes)
            self.title(f"Ver Mis Likes - SoundCloud ({len(likes)} canciones)")

        except Exception as e:
            messagebox.showerror("Error", f"Error cargando likes: {e}")
            self.destroy()

    def _render_likes(self, likes):
        """Renderiza los likes en la tabla."""
        # Limpiar tabla
        for item in self.tree.get_children():
            self.tree.delete(item)

        # Agregar likes
        for like in likes:
            duration_ms = like.duration_ms or 0
            minutes = duration_ms // 60000
            seconds = (duration_ms % 60000) // 1000
            duration_str = f"{minutes}:{seconds:02d}"

            self.tree.insert("", "end", iid=like.url,
                           text="☐", values=(like.artist or "Unknown",
                                            like.title or "Unknown",
                                            duration_str))

    def _on_search(self, *args):
        """Filtra la tabla en tiempo real."""
        search_text = self.search_var.get().lower()

        if not search_text:
            self._render_likes(self._all_likes)
            return

        filtered = [like for like in self._all_likes
                   if search_text in (like.artist or "").lower() or
                      search_text in (like.title or "").lower()]

        self._render_likes(filtered)

    def _on_tree_click(self, event):
        """Maneja clicks en la tabla para marcar/desmarcar."""
        item = self.tree.identify("item", event.x, event.y)
        if not item:
            return

        current = self.tree.item(item, "text")
        new_text = "☑" if current == "☐" else "☐"
        self.tree.item(item, text=new_text)

        if new_text == "☑":
            self._selected_urls.add(item)
        else:
            self._selected_urls.discard(item)

        self.count_label.configure(text=f"Seleccionadas: {len(self._selected_urls)}")

    def _select_all(self):
        """Selecciona todas las canciones visibles."""
        self._selected_urls.clear()
        for item in self.tree.get_children():
            self.tree.item(item, text="☑")
            self._selected_urls.add(item)

        self.count_label.configure(text=f"Seleccionadas: {len(self._selected_urls)}")

    def _deselect_all(self):
        """Deselecciona todas las canciones."""
        self._selected_urls.clear()
        for item in self.tree.get_children():
            self.tree.item(item, text="☐")

        self.count_label.configure(text="Seleccionadas: 0")

    def _download_selected(self):
        """Descarga las canciones seleccionadas."""
        import logging
        logger = logging.getLogger(__name__)

        if not self._selected_urls:
            messagebox.showwarning("Aviso", "Selecciona al menos una canción")
            return

        # Obtener datos de las seleccionadas
        selected_likes = [like for like in self._all_likes if like.url in self._selected_urls]

        # Convertir SoundCloudTrack a TrackInfo
        from models import TrackInfo
        tracks = []
        for like in selected_likes:
            track = TrackInfo(
                url=like.url,
                title=like.title or "Unknown",
                artist=like.artist or "Unknown",
                thumbnail_url=like.artwork_url or "",
                duration=int((like.duration_ms or 0) / 1000),  # Convertir ms a segundos
                platform="soundcloud"
            )
            tracks.append(track)

        logger.info(f"📥 Iniciando descarga de {len(tracks)} canciones desde Likes Viewer")

        # Enviar al panel principal para descargar
        messagebox.showinfo("Descargar",
                           f"Se descargarán {len(tracks)} canciones.\n"
                           "Revisa el panel de descargas.")

        # Llamar al callback de descarga del padre
        if hasattr(self.master, '_on_batch_download'):
            logger.info("✓ Encontrado _on_batch_download en master")
            try:
                self.master._on_batch_download(tracks)
                logger.info("✓ Descarga iniciada")
            except Exception as e:
                logger.error(f"❌ Error en _on_batch_download: {e}")
                messagebox.showerror("Error", f"Error iniciando descarga: {e}")
        else:
            logger.error("❌ No se encontró _on_batch_download en master")
            messagebox.showerror("Error", "No se pudo conectar al panel de descargas")

        self.destroy()
