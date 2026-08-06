"""
Ventana simple para ver y descargar canciones de la BD de historial.
"""
import os
import tkinter as tk
from tkinter import ttk, messagebox
import customtkinter as ctk

from db.history import DownloadHistory

class DBViewerWindow(ctk.CTkToplevel):
    """Ventana para ver y descargar canciones desde la BD."""

    def __init__(self, master, ui_controller):
        super().__init__(master)
        self.title("Historial de descargas")
        self.geometry("900x600")
        self.ui_controller = ui_controller
        self.history = DownloadHistory()
        self._selected_urls = set()

        self._build_ui()
        self._load_likes()

    def _build_ui(self):
        # Header con info
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", padx=10, pady=10)

        ctk.CTkLabel(header, text="Canciones en la BD",
                    font=("Arial", 16, "bold")).pack(side="left")

        # Buscador
        search_frame = ctk.CTkFrame(self, fg_color="transparent")
        search_frame.pack(fill="x", padx=10, pady=5)

        ctk.CTkLabel(search_frame, text="Buscar:").pack(side="left", padx=5)
        self.search_var = tk.StringVar()
        self.search_var.trace("w", self._on_search)
        search_entry = ctk.CTkEntry(search_frame, textvariable=self.search_var,
                                    placeholder_text="Artista o canción...")
        search_entry.pack(side="left", fill="x", expand=True, padx=5)

        self._all_downloads = []

        # Tabla con scrollbar
        table_frame = ctk.CTkFrame(self)
        table_frame.pack(fill="both", expand=True, padx=10, pady=5)

        # Crear treeview
        self.tree = ttk.Treeview(table_frame, height=20, columns=("Artist", "Title", "Platform"))
        self.tree.heading("#0", text="Seleccionar")
        self.tree.heading("Artist", text="Artista")
        self.tree.heading("Title", text="Canción")
        self.tree.heading("Platform", text="Plataforma")

        self.tree.column("#0", width=80)
        self.tree.column("Artist", width=200)
        self.tree.column("Title", width=400)
        self.tree.column("Platform", width=100)

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

        ctk.CTkLabel(footer, text="Seleccionadas: 0",
                    textvariable=tk.StringVar()).pack(side="left")

        ctk.CTkButton(footer, text="Seleccionar Todo",
                     command=self._select_all, width=150).pack(side="left", padx=5)

        ctk.CTkButton(footer, text="Deseleccionar Todo",
                     command=self._deselect_all, width=150).pack(side="left", padx=5)

        ctk.CTkButton(footer, text="🔍 Buscar duplicados de audio",
                     command=self._scan_audio_duplicates, width=210).pack(side="left", padx=5)

        ctk.CTkButton(footer, text="Descargar Seleccionadas",
                     command=self._download_selected, width=200,
                     fg_color="green").pack(side="right", padx=5)

    def _scan_audio_duplicates(self):
        """
        Escanea la carpeta de descargas buscando duplicados de AUDIO real
        (fingerprint acústico), no solo nombres parecidos. Requiere
        'pyacoustid' instalado + el binario 'fpcalc' (chromaprint) en PATH;
        si falta alguno, avisa y no rompe nada más de la app.
        """
        from utils.audio_fingerprint import is_available

        if not is_available():
            messagebox.showwarning(
                "No disponible",
                "El escaneo de duplicados de audio requiere:\n"
                "  1. pip install pyacoustid\n"
                "  2. El binario 'fpcalc' (Chromaprint) en el PATH\n\n"
                "Instálalos y volvé a intentar."
            )
            return

        dest_folder = self.ui_controller.get_config_value("dest_folder", "")
        if not dest_folder or not os.path.isdir(dest_folder):
            messagebox.showwarning("Carpeta inválida", "No se encontró la carpeta de descargas configurada.")
            return

        import threading
        from sync.audio_duplicate_scanner import scan_folder_for_audio_duplicates

        def run_scan():
            groups = scan_folder_for_audio_duplicates(dest_folder)
            self.after(0, lambda: self._show_scan_results(groups))

        messagebox.showinfo("Escaneando...", "Esto puede tardar según el tamaño de tu biblioteca. La app seguirá respondiendo.")
        threading.Thread(target=run_scan, daemon=True).start()

    def _show_scan_results(self, groups: list):
        if not groups:
            messagebox.showinfo("Duplicados de audio", "No se encontraron duplicados de audio.")
            return

        lines = []
        for i, group in enumerate(groups, 1):
            lines.append(f"Grupo {i}:")
            for path in group:
                lines.append(f"   • {os.path.basename(path)}")
        messagebox.showinfo(
            "Duplicados de audio encontrados",
            f"{len(groups)} grupo(s) de canciones acústicamente idénticas:\n\n" + "\n".join(lines[:60])
        )

    def _load_likes(self):
        """Carga todas las descargas registradas en la BD."""
        try:
            self._all_downloads = self.history.get_all_downloads()
            self.title(f"Historial de descargas - {len(self._all_downloads)} canciones")
            self._render_downloads(self._all_downloads)
        except Exception as e:
            messagebox.showerror("Error", f"Error cargando historial: {e}")

    def _render_downloads(self, downloads):
        """Renderiza los downloads en la tabla."""
        # Limpiar tabla
        for item in self.tree.get_children():
            self.tree.delete(item)

        # Agregar downloads
        for download in downloads:
            self.tree.insert("", "end", iid=download['url'],
                           text="☐", values=(download['artist'] or "Unknown",
                                            download['title'] or "Unknown",
                                            download['platform'] or "soundcloud"))

    def _on_search(self, *args):
        """Filtra la tabla en tiempo real."""
        search_text = self.search_var.get().lower()

        if not search_text:
            self._render_downloads(self._all_downloads)
            return

        filtered = [d for d in self._all_downloads
                   if search_text in (d['artist'] or "").lower() or
                      search_text in (d['title'] or "").lower()]

        self._render_downloads(filtered)

    def _select_all(self):
        """Selecciona todas las canciones."""
        for item in self.tree.get_children():
            self._selected_urls.add(item)
            self.tree.item(item, text="☑")

    def _deselect_all(self):
        """Deselecciona todas las canciones."""
        self._selected_urls.clear()
        for item in self.tree.get_children():
            self.tree.item(item, text="☐")

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

    def get_all_downloads(self):
        """Retorna todos los downloads de la BD en el formato esperado."""
        try:
            downloads = []
            for item in self.tree.get_children():
                values = self.tree.item(item, "values")
                if len(values) >= 3:
                    downloads.append({
                        'url': item,
                        'artist': values[0],
                        'title': values[1],
                        'platform': values[2]
                    })
            return downloads
        except Exception as e:
            messagebox.showerror("Error", f"Error leyendo datos: {e}")
            return []

    def _download_selected(self):
        """Descarga las canciones seleccionadas."""
        import logging
        logger = logging.getLogger(__name__)

        # Obtener datos de las seleccionadas
        selected_downloads = []
        for item in self.tree.get_children():
            if self.tree.item(item, "text") == "☑":
                values = self.tree.item(item, "values")
                selected_downloads.append({
                    'url': item,
                    'artist': values[0],
                    'title': values[1],
                    'platform': values[2]
                })

        if not selected_downloads:
            messagebox.showwarning("Aviso", "Selecciona al menos una canción")
            return

        # Convertir a TrackInfo
        from models import TrackInfo
        tracks = []
        for download in selected_downloads:
            track = TrackInfo(
                url=download['url'],
                title=download['title'],
                artist=download['artist'],
                platform=download['platform'] or "soundcloud"
            )
            tracks.append(track)

        logger.info(f"📥 Iniciando descarga de {len(tracks)} canciones desde DB Viewer")

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
