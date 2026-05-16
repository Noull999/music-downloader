"""
Ventana simple para ver y descargar canciones de la BD de historial.
"""
import tkinter as tk
from tkinter import ttk, messagebox
import customtkinter as ctk

from db.history_manager import HistoryManager

class DBViewerWindow(ctk.CTkToplevel):
    """Ventana para ver y descargar canciones desde la BD."""

    def __init__(self, master, ui_controller):
        super().__init__(master)
        self.title("Ver BD de Likes - 341 Canciones")
        self.geometry("900x600")
        self.ui_controller = ui_controller
        self.history = HistoryManager()
        self._selected_urls = set()

        self._build_ui()
        self._load_likes()

    def _build_ui(self):
        # Header con info
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", padx=10, pady=10)

        ctk.CTkLabel(header, text="341 Canciones en la BD",
                    font=("Arial", 16, "bold")).pack(side="left")

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

        ctk.CTkButton(footer, text="Descargar Seleccionadas",
                     command=self._download_selected, width=200,
                     fg_color="green").pack(side="right", padx=5)

    def _load_likes(self):
        """Carga todos los likes de la BD."""
        try:
            import sqlite3
            db_path = self.history.db_path
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()

            # Query directa - soporta ambos esquemas
            try:
                cursor.execute("SELECT url, title, artist, platform FROM downloads ORDER BY download_date DESC")
            except sqlite3.OperationalError:
                cursor.execute("SELECT url, title, artist, platform FROM downloads ORDER BY downloaded_at DESC")

            for row in cursor.fetchall():
                url, title, artist, platform = row
                self.tree.insert("", "end", iid=url,
                               text="☐", values=(artist or "Unknown", title or "Unknown", platform or "soundcloud"))

            conn.close()
        except Exception as e:
            messagebox.showerror("Error", f"Error cargando likes: {e}")

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

        messagebox.showinfo("Descargar", f"Se descargarán {len(selected_downloads)} canciones.\n"
                           "Esta funcionalidad se implementará pronto.")
        self.destroy()
