"""
Ventana de sincronización de likes de SoundCloud.
Se integra como una pestaña en la GUI principal.
"""
import threading
import logging
import json
import os
from pathlib import Path
from tkinter import messagebox, filedialog

import customtkinter as ctk

from sync.sync_manager import SyncManager
from sync.scheduler import AutoSyncScheduler
from sync.soundcloud_api import SoundCloudAPIClient
from notifications.notifier import Notifier
from gui.likes_preview_window import LikesPreviewWindow

logger = logging.getLogger(__name__)


class SyncWindow(ctk.CTkFrame):
    """
    Panel de sincronización de likes de SoundCloud.
    Se inserta como una pestaña en tabview.
    """

    def __init__(self, master, config_path: str, download_folder: str, downloader,
                 download_manager=None):
        """
        Args:
            master: Frame padre (tab en tabview)
            config_path: Ruta a config.json
            download_folder: Carpeta de descargas
            downloader: Handler de SoundCloud
            download_manager: DownloadManager compartido con MainWindow
        """
        super().__init__(master, corner_radius=0, fg_color="transparent")
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)

        self.config_path = config_path
        self.download_folder = download_folder
        self.downloader = downloader
        self._download_manager = download_manager

        # State
        self.manager: SyncManager | None = None
        self.scheduler: AutoSyncScheduler | None = None
        self._config = self._load_config()

        # UI
        scroll = ctk.CTkScrollableFrame(self, fg_color="transparent")
        scroll.grid(row=0, column=0, sticky="nsew", padx=0, pady=0)
        scroll.grid_columnconfigure(0, weight=1)

        self._build_ui(scroll)

    # ────────────────────────────────────────────────────────────────── #
    # Construccion de UI                                                  #
    # ────────────────────────────────────────────────────────────────── #

    def _build_ui(self, parent):
        """Construye todos los paneles de la interfaz."""
        # ── Panel 1: Credenciales ──────────────────────────────────── #
        self._build_credentials_panel(parent)

        # ── Separador ──────────────────────────────────────────────── #
        ctk.CTkFrame(parent, height=1, fg_color="#374151").grid(
            row=1, column=0, sticky="ew", padx=16, pady=12
        )

        # ── Panel 2: Carpeta ────────────────────────────────────────── #
        self._build_folder_panel(parent)

        # ── Separador ──────────────────────────────────────────────── #
        ctk.CTkFrame(parent, height=1, fg_color="#374151").grid(
            row=3, column=0, sticky="ew", padx=16, pady=12
        )

        # ── Panel 3: Auto-sync ────────────────────────────────────── #
        self._build_autosync_panel(parent)

        # ── Separador ──────────────────────────────────────────────── #
        ctk.CTkFrame(parent, height=1, fg_color="#374151").grid(
            row=5, column=0, sticky="ew", padx=16, pady=12
        )

        # ── Panel 4: Progreso ──────────────────────────────────────── #
        self._build_progress_panel(parent)

        # ── Separador ──────────────────────────────────────────────── #
        ctk.CTkFrame(parent, height=1, fg_color="#374151").grid(
            row=7, column=0, sticky="ew", padx=16, pady=12
        )

        # ── Panel 5: Opciones Avanzadas ────────────────────────────── #
        self._build_advanced_panel(parent)

        # ── Separador ──────────────────────────────────────────────── #
        ctk.CTkFrame(parent, height=1, fg_color="#374151").grid(
            row=9, column=0, sticky="ew", padx=16, pady=12
        )

        # ── Panel 6: Stats ────────────────────────────────────────── #
        self._build_stats_panel(parent)

        # Padding final
        ctk.CTkLabel(parent, text="").grid(row=11, column=0, pady=20)

    def _build_credentials_panel(self, parent):
        """Panel de credenciales de SoundCloud."""
        container = ctk.CTkFrame(parent, fg_color="transparent")
        container.grid(row=0, column=0, sticky="ew", padx=16, pady=12)
        container.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(
            container, text="Credenciales de SoundCloud",
            font=ctk.CTkFont(size=13, weight="bold")
        ).grid(row=0, column=0, columnspan=3, sticky="w", pady=(0, 10))

        # OAuth Token
        ctk.CTkLabel(container, text="OAuth Token:").grid(
            row=1, column=0, sticky="e", padx=(0, 8)
        )
        self._oauth_entry = ctk.CTkEntry(
            container, placeholder_text="OAuth 2-XXXXX-XXXXX-XXXXX",
            show="*"
        )
        self._oauth_entry.grid(row=1, column=1, sticky="ew", padx=(0, 8))
        self._oauth_entry.insert(0, self._config.get("soundcloud", {}).get("oauth_token", ""))

        self._oauth_entry.bind("<KeyRelease>", lambda e: self._on_cred_change())

        ctk.CTkButton(
            container, text="Ver", width=50, height=28,
            command=self._toggle_oauth_visibility
        ).grid(row=1, column=2, padx=(0, 8))

        # Client ID
        ctk.CTkLabel(container, text="Client ID:").grid(
            row=2, column=0, sticky="e", padx=(0, 8), pady=(8, 0)
        )
        self._client_entry = ctk.CTkEntry(
            container, placeholder_text="XXXXXXXXXXXXXXXX"
        )
        self._client_entry.grid(row=2, column=1, sticky="ew", padx=(0, 8), pady=(8, 0))
        self._client_entry.insert(0, self._config.get("soundcloud", {}).get("client_id", ""))
        self._client_entry.bind("<KeyRelease>", lambda e: self._on_cred_change())

        ctk.CTkButton(
            container, text="Copiar", width=50, height=28,
            command=self._copy_client_id
        ).grid(row=2, column=2, padx=(0, 8), pady=(8, 0))

        # Estado
        self._status_label = ctk.CTkLabel(
            container, text="No verificado",
            text_color="#6b7280", font=ctk.CTkFont(size=10)
        )
        self._status_label.grid(
            row=3, column=0, columnspan=2, sticky="w", pady=(8, 0)
        )

        # Botones
        btn_row = ctk.CTkFrame(container, fg_color="transparent")
        btn_row.grid(row=4, column=0, columnspan=3, sticky="ew", pady=(10, 0))

        ctk.CTkButton(
            btn_row, text="Verificar credenciales", height=28,
            command=self._on_verify_credentials
        ).pack(side="left", padx=(0, 8))

        ctk.CTkButton(
            btn_row, text="? Ayuda",
            fg_color="#6b7280", hover_color="#4b5563",
            height=28, width=80,
            command=self._show_help
        ).pack(side="left")

    def _build_folder_panel(self, parent):
        """Panel de selección de carpeta."""
        container = ctk.CTkFrame(parent, fg_color="transparent")
        container.grid(row=2, column=0, sticky="ew", padx=16, pady=12)
        container.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(
            container, text="Carpeta de descarga",
            font=ctk.CTkFont(size=13, weight="bold")
        ).grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 8))

        self._folder_label = ctk.CTkLabel(
            container, text=self.download_folder,
            text_color="#9ca3af", font=ctk.CTkFont(size=10),
            anchor="w"
        )
        self._folder_label.grid(row=1, column=0, sticky="ew", padx=(0, 8))

        ctk.CTkButton(
            container, text="Cambiar", width=80, height=28,
            command=self._on_change_folder
        ).grid(row=1, column=1)

    def _build_autosync_panel(self, parent):
        """Panel de auto-sincronización."""
        container = ctk.CTkFrame(parent, fg_color="transparent")
        container.grid(row=4, column=0, sticky="ew", padx=16, pady=12)
        container.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(
            container, text="Auto-sincronizacion",
            font=ctk.CTkFont(size=13, weight="bold")
        ).grid(row=0, column=0, columnspan=3, sticky="w", pady=(0, 10))

        # Toggle
        self._autosync_var = ctk.BooleanVar(
            value=self._config.get("soundcloud", {}).get("auto_sync", False)
        )
        self._autosync_toggle = ctk.CTkSwitch(
            container, text="Activar auto-sync",
            variable=self._autosync_var,
            command=self._on_autosync_toggle
        )
        self._autosync_toggle.grid(row=1, column=0, columnspan=2, sticky="w", pady=(0, 10))

        # Intervalo
        ctk.CTkLabel(container, text="Cada:").grid(
            row=2, column=0, sticky="e", padx=(0, 8)
        )

        interval_frame = ctk.CTkFrame(container, fg_color="transparent")
        interval_frame.grid(row=2, column=1, sticky="ew")
        interval_frame.grid_columnconfigure(1, weight=1)

        self._interval_entry = ctk.CTkEntry(
            interval_frame,
            width=60, placeholder_text="30"
        )
        self._interval_entry.insert(0, str(
            self._config.get("soundcloud", {}).get("sync_interval_minutes", 30)
        ))
        self._interval_entry.grid(row=0, column=0, padx=(0, 8))
        self._interval_entry.bind("<KeyRelease>", lambda e: self._on_interval_change())

        ctk.CTkLabel(interval_frame, text="minutos").grid(row=0, column=1)

        # Estado scheduler
        self._scheduler_status = ctk.CTkLabel(
            container, text="[Inactivo]",
            text_color="#6b7280", font=ctk.CTkFont(size=10)
        )
        self._scheduler_status.grid(
            row=3, column=0, columnspan=2, sticky="w", pady=(8, 0)
        )

    def _build_progress_panel(self, parent):
        """Panel de progreso durante sincronización."""
        container = ctk.CTkFrame(parent, fg_color="transparent")
        container.grid(row=6, column=0, sticky="ew", padx=16, pady=12)
        container.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            container, text="Sincronizacion",
            font=ctk.CTkFont(size=13, weight="bold")
        ).grid(row=0, column=0, sticky="w", pady=(0, 10))

        # Barra de progreso
        self._progress = ctk.CTkProgressBar(container, height=6)
        self._progress.set(0)
        self._progress.grid(row=1, column=0, sticky="ew", pady=(0, 8))

        # Mensaje
        self._progress_msg = ctk.CTkLabel(
            container, text="Listo",
            text_color="#9ca3af", font=ctk.CTkFont(size=10)
        )
        self._progress_msg.grid(row=2, column=0, sticky="w", pady=(0, 10))

        # Botones
        btn_row = ctk.CTkFrame(container, fg_color="transparent")
        btn_row.grid(row=3, column=0, sticky="ew")

        self._sync_now_btn = ctk.CTkButton(
            btn_row, text="Sincronizar ahora",
            command=self._on_sync_manual
        )
        self._sync_now_btn.pack(side="left", padx=(0, 8))

        self._recent_count_menu = ctk.CTkOptionMenu(
            btn_row,
            values=["10", "20", "30", "40", "50"],
            width=70, height=28,
            fg_color="#374151", button_color="#4b5563",
            button_hover_color="#374151",
        )
        self._recent_count_menu.set("10")
        self._recent_count_menu.pack(side="left", padx=(0, 4))

        self._sync_recent_btn = ctk.CTkButton(
            btn_row, text="Verificar últimas",
            fg_color="#6b7280", hover_color="#4b5563",
            command=self._on_sync_recent
        )
        self._sync_recent_btn.pack(side="left", padx=(0, 8))

        self._sync_stop_btn = ctk.CTkButton(
            btn_row, text="Detener",
            fg_color="#6b7280", hover_color="#4b5563",
            state="disabled",
            command=self._on_sync_stop
        )
        self._sync_stop_btn.pack(side="left")

    def _build_advanced_panel(self, parent):
        """Panel de opciones avanzadas."""
        container = ctk.CTkFrame(parent, fg_color="transparent")
        container.grid(row=8, column=0, sticky="ew", padx=16, pady=12)
        for i in range(4):
            container.grid_columnconfigure(i, weight=1)

        ctk.CTkLabel(
            container, text="Opciones Avanzadas",
            font=ctk.CTkFont(size=13, weight="bold")
        ).grid(row=0, column=0, columnspan=3, sticky="w", pady=(0, 10))

        # Botón principal de likes
        preview_btn = ctk.CTkButton(
            container, text="Ver mis Likes",
            fg_color="#8b5cf6", hover_color="#7c3aed",
            command=self._on_show_likes_preview
        )
        preview_btn.grid(row=1, column=0, sticky="ew", padx=(0, 8))

        # Reparar historial local
        sync_files_btn = ctk.CTkButton(
            container, text="🔧 Reparar historial",
            fg_color="#06b6d4", hover_color="#0891b2",
            command=self._on_sync_filesystem
        )
        sync_files_btn.grid(row=1, column=1, sticky="ew", padx=(0, 8))

        # Solo explorar sin descargar
        self._scan_only_btn = ctk.CTkButton(
            container, text="Solo explorar (sin descargar)",
            fg_color="#7c3aed", hover_color="#6d28d9",
            command=self._on_scan_only
        )
        self._scan_only_btn.grid(row=1, column=2, sticky="ew", padx=(0, 8))

        # Descargar desde posición específica
        ctk.CTkLabel(container, text="Desde posición:").grid(
            row=2, column=1, sticky="e", padx=(0, 8)
        )
        self._start_index_entry = ctk.CTkEntry(
            container, placeholder_text="0 = primera, 50 = desde la 51ra..."
        )
        self._start_index_entry.insert(0, "0")
        self._start_index_entry.grid(row=2, column=2, sticky="ew", padx=(0, 8))

        self._sync_from_index_btn = ctk.CTkButton(
            container, text="Descargar desde posición",
            fg_color="#7c3aed", hover_color="#6d28d9",
            command=self._on_sync_from_index
        )
        self._sync_from_index_btn.grid(row=2, column=0, sticky="ew", padx=(0, 8))

    def _build_stats_panel(self, parent):
        """Panel de estadísticas."""
        container = ctk.CTkFrame(parent, fg_color="transparent")
        container.grid(row=10, column=0, sticky="ew", padx=16, pady=12)

        ctk.CTkLabel(
            container, text="Estadisticas",
            font=ctk.CTkFont(size=13, weight="bold")
        ).pack(anchor="w", pady=(0, 10))

        # Ultima sync
        self._last_sync_label = ctk.CTkLabel(
            container, text="Ultima sincronizacion: Nunca",
            text_color="#9ca3af", font=ctk.CTkFont(size=10)
        )
        self._last_sync_label.pack(anchor="w", pady=(0, 4))

        # Historial
        self._history_label = ctk.CTkLabel(
            container, text="Historial: 0 canciones | 0 artistas",
            text_color="#9ca3af", font=ctk.CTkFont(size=10)
        )
        self._history_label.pack(anchor="w")

        # Actualizar stats
        self._refresh_stats()

    # ────────────────────────────────────────────────────────────────── #
    # Handlers de eventos                                                 #
    # ────────────────────────────────────────────────────────────────── #

    def _on_cred_change(self):
        """Guarda credenciales automáticamente cuando cambian."""
        self._save_config()
        self._status_label.configure(text="Credenciales guardadas", text_color="#9ca3af")

    def _on_verify_credentials(self):
        """Verifica las credenciales ingresadas."""
        oauth = self._oauth_entry.get().strip()
        client_id = self._client_entry.get().strip()

        if not oauth or not client_id:
            self._status_label.configure(
                text="Error: Completa los campos",
                text_color="#f87171"
            )
            return

        # Verificar en thread para no bloquear GUI
        def verify():
            try:
                api = SoundCloudAPIClient(oauth, client_id)
                user = api.validate_credentials()
                self.after(0, lambda: self._on_verify_success(user))
            except Exception as e:
                self.after(0, lambda: self._on_verify_error(str(e)))

        threading.Thread(target=verify, daemon=True).start()
        self._status_label.configure(text="Verificando...", text_color="#fbbf24")

    def _on_verify_success(self, user_info):
        """Credenciales válidas."""
        self._status_label.configure(
            text=f"OK: {user_info['username']} | "
                 f"{user_info['likes_count']} likes",
            text_color="#4ade80"
        )
        self._save_config()
        self._init_manager()

        messagebox.showinfo(
            "Exito",
            f"Credenciales validas!\n\n"
            f"Usuario: {user_info['username']}\n"
            f"Likes: {user_info['likes_count']}"
        )

    def _on_verify_error(self, error):
        """Error en verificación."""
        self._status_label.configure(
            text=f"Error: {error[:50]}",
            text_color="#f87171"
        )

    def _toggle_oauth_visibility(self):
        """Alterna visibilidad del OAuth token."""
        current_show = self._oauth_entry.cget("show")
        self._oauth_entry.configure(show="" if current_show == "*" else "*")

    def _copy_client_id(self):
        """Copia el Client ID al portapapeles."""
        client_id = self._client_entry.get()
        if client_id:
            self.clipboard_clear()
            self.clipboard_append(client_id)
            messagebox.showinfo("Copiado", "Client ID copiado al portapapeles")

    def _on_change_folder(self):
        """Abre diálogo para cambiar carpeta."""
        folder = filedialog.askdirectory(
            title="Seleccionar carpeta de descarga",
            initialdir=self.download_folder
        )
        if folder:
            self.download_folder = folder
            self._folder_label.configure(text=folder)
            self._save_config()

    def _on_autosync_toggle(self):
        """Activa/desactiva auto-sync."""
        enabled = self._autosync_var.get()

        if enabled:
            if not self.manager:
                messagebox.showerror(
                    "Error",
                    "Primero verifica tus credenciales"
                )
                self._autosync_var.set(False)
                return

            # Iniciar scheduler
            interval = int(self._interval_entry.get())
            self.scheduler = AutoSyncScheduler(self.manager, interval_minutes=interval)
            self.scheduler.on_sync_start = self._on_scheduler_start
            self.scheduler.on_sync_complete = self._on_scheduler_complete
            self.scheduler.start()

            self._scheduler_status.configure(
                text=f"[Activo] Proxima sync en {interval} minutos",
                text_color="#4ade80"
            )
        else:
            if self.scheduler:
                self.scheduler.stop()
                self.scheduler = None

            self._scheduler_status.configure(
                text="[Inactivo]",
                text_color="#6b7280"
            )

        self._save_config()

    def _on_interval_change(self):
        """Cambia el intervalo de auto-sync."""
        try:
            interval = int(self._interval_entry.get())
            if interval < 5:
                interval = 5
                self._interval_entry.delete(0, "end")
                self._interval_entry.insert(0, "5")
            elif interval > 1440:
                interval = 1440
                self._interval_entry.delete(0, "end")
                self._interval_entry.insert(0, "1440")

            if self.scheduler:
                self.scheduler.set_interval(interval)
                self._scheduler_status.configure(
                    text=f"[Activo] Intervalo: {interval} minutos"
                )
            self._save_config()
        except ValueError:
            pass

    def _on_sync_manual(self):
        """Inicia sincronización manual completa."""
        if not self.manager:
            messagebox.showerror("Error", "Verifica tus credenciales primero")
            return

        if not messagebox.askyesno(
            "Confirmar sincronización completa",
            "Esto descargará TODAS tus canciones pendientes de SoundCloud.\n\n"
            "Si tienes muchos likes puede tomar bastante tiempo.\n\n¿Continuar?",
            parent=self
        ):
            return

        self._sync_now_btn.configure(state="disabled")
        self._sync_stop_btn.configure(state="normal")

        def sync():
            results = self.manager.sync_once(
                progress_callback=self._on_sync_progress
            )
            self.after(0, lambda: self._on_sync_complete_manual(results))

        threading.Thread(target=sync, daemon=True).start()

    def _on_sync_recent(self):
        """Inicia sincronización rápida con el rango seleccionado."""
        if not self.manager:
            messagebox.showerror("Error", "Verifica tus credenciales primero")
            return

        count = int(self._recent_count_menu.get())
        self._sync_recent_btn.configure(state="disabled")
        self._recent_count_menu.configure(state="disabled")
        self._sync_stop_btn.configure(state="normal")

        def sync():
            results = self.manager.sync_recent(
                count=count,
                progress_callback=self._on_sync_progress
            )
            self.after(0, lambda: self._on_sync_complete_manual(results))

        threading.Thread(target=sync, daemon=True).start()

    def _on_sync_stop(self):
        """Detiene la sincronización en curso."""
        if self.manager:
            self.manager.stop()
            self._sync_stop_btn.configure(state="disabled")

    def _on_scan_only(self):
        """Solo verifica duplicados sin descargar."""
        if not self.manager:
            messagebox.showerror("Error", "Verifica tus credenciales primero")
            return

        self._scan_only_btn.configure(state="disabled")
        self._sync_stop_btn.configure(state="normal")

        def scan():
            results = self.manager.scan_only(
                progress_callback=self._on_sync_progress
            )
            self.after(0, lambda: self._on_scan_complete(results))

        threading.Thread(target=scan, daemon=True).start()

    def _on_scan_complete(self, results):
        """Verificación completada."""
        self._progress.set(1.0)
        self._progress_msg.configure(
            text=f"✓ Verificación: {results['new']} nuevas, {results['skipped']} ya tienes"
        )
        self._scan_only_btn.configure(state="normal")
        self._sync_stop_btn.configure(state="disabled")

        msg = (f"Verificación completada\n\n"
               f"Nuevas para descargar: {results['new']}\n"
               f"Ya tienes: {results['skipped']}")

        if results['duplicates']:
            dup_list = "\n".join([f"• {t.artist} - {t.title}"
                                  for t, _ in results['duplicates'][:5]])
            if len(results['duplicates']) > 5:
                dup_list += f"\n• ... y {len(results['duplicates']) - 5} más"
            msg += f"\n\nDuplicados encontrados:\n{dup_list}"

        messagebox.showinfo("Verificación", msg)

    def _on_sync_from_index(self):
        """Descarga desde un índice específico."""
        if not self.manager:
            messagebox.showerror("Error", "Verifica tus credenciales primero")
            return

        try:
            start_index = int(self._start_index_entry.get())
        except ValueError:
            messagebox.showerror("Error", "Índice debe ser un número")
            return

        if start_index < 0:
            messagebox.showerror("Error", "Índice no puede ser negativo")
            return

        self._sync_from_index_btn.configure(state="disabled")
        self._sync_now_btn.configure(state="disabled")
        self._sync_stop_btn.configure(state="normal")

        def sync():
            results = self.manager.sync_from_index(
                start_index=start_index,
                progress_callback=self._on_sync_progress
            )
            self.after(0, lambda: self._on_sync_complete_manual(results))

        threading.Thread(target=sync, daemon=True).start()

    def _on_sync_progress(self, pct: int, msg: str):
        """Actualiza barra de progreso."""
        self.after(0, lambda: self._progress.set(pct / 100))
        self.after(0, lambda: self._progress_msg.configure(text=msg))

    def _on_sync_complete_manual(self, results):
        """Sincronización manual completada."""
        self._progress.set(1.0)
        self._progress_msg.configure(
            text=f"OK: +{results['new']} | "
                 f"-{results['skipped']} | "
                 f"!{results['errors']}"
        )
        self._sync_now_btn.configure(state="normal")
        self._sync_recent_btn.configure(state="normal")
        self._recent_count_menu.configure(state="normal")
        self._sync_from_index_btn.configure(state="normal")
        self._scan_only_btn.configure(state="normal")
        self._sync_stop_btn.configure(state="disabled")

        self._refresh_stats()

        if results['new'] > 0:
            messagebox.showinfo(
                "Exito",
                f"Sincronizacion completada!\n\n"
                f"Descargadas: {results['new']}\n"
                f"Omitidas: {results['skipped']}\n"
                f"Errores: {results['errors']}"
            )

    def _on_scheduler_start(self):
        """Scheduler inició sincronización."""
        self.after(0, lambda: self._progress_msg.configure(text="Auto-sync en progreso..."))
        self.after(0, lambda: self._progress.set(0))

    def _on_scheduler_complete(self, results):
        """Scheduler completó sincronización."""
        self.after(0, lambda: self._progress_msg.configure(
            text=f"Auto-sync: +{results['new']} | "
                 f"-{results['skipped']} | "
                 f"!{results['errors']}"
        ))
        self.after(0, lambda: self._refresh_stats())

    def _on_show_likes_preview(self):
        """Abre la ventana de likes para ver y descargar."""
        if not self.manager:
            messagebox.showerror("Error", "Primero verifica tus credenciales")
            return

        preview_window = ctk.CTkToplevel(self)
        preview_window.title("Mis Likes de SoundCloud")
        preview_window.geometry("1000x620")
        preview_window.resizable(True, True)

        preview_panel = LikesPreviewWindow(
            preview_window,
            self.manager,
            self.downloader,
            download_manager=self._download_manager,
            config=self._config,
        )
        preview_panel.pack(fill="both", expand=True)

    def _on_sync_filesystem(self):
        """Sincroniza archivos del filesystem con la base de datos."""
        if not self.manager:
            messagebox.showerror("Error", "Verifica tus credenciales primero")
            return

        def sync():
            try:
                results = self.manager.sync_filesystem_to_db()
                self.after(0, lambda: self._on_sync_filesystem_complete(results))
            except Exception as e:
                self.after(0, lambda: messagebox.showerror("Error", str(e)))

        messagebox.showinfo(
            "Sincronizando",
            "Escaneando archivos locales...\nEsto puede tomar un momento."
        )
        threading.Thread(target=sync, daemon=True).start()

    def _on_sync_filesystem_complete(self, results):
        """Muestra resultado de sincronización de filesystem."""
        msg = (
            f"✓ Sincronización completada\n\n"
            f"Archivos agregados: {results['added']}\n"
            f"Archivos ya rastreados: {results['already_tracked']}\n"
            f"Total encontrado: {results['total_found']}"
        )
        messagebox.showinfo("Sync Filesystem", msg)

    def _show_help(self):
        """Muestra ayuda sobre cómo obtener credenciales."""
        help_text = """
COMO OBTENER TUS CREDENCIALES DE SOUNDCLOUD

1. Abre https://soundcloud.com en tu navegador
2. Inicia sesion con tu cuenta
3. Presiona F12 (DevTools)
4. Ve a la pestana "Network"
5. Escribe "api-v2" en el filtro
6. Recarga la pagina (F5)
7. Haz click en cualquier request

OAUTH TOKEN:
- En "Request Headers" busca "Authorization"
- Copia el valor completo: "OAuth 2-XXXXX-XXXXX-XXXXX"

CLIENT ID:
- En la URL del request busca "client_id=XXXXXXXX"
- Copia solo la parte alfanumerica

ADVERTENCIA:
- Estos valores son como contraseñas, NO los compartas
- Mantenlos privados como si fueran credenciales bancarias
        """
        messagebox.showinfo("Como obtener credenciales", help_text)

    # ────────────────────────────────────────────────────────────────── #
    # Internos                                                             #
    # ────────────────────────────────────────────────────────────────── #

    def _init_manager(self):
        """Inicializa el SyncManager con credenciales válidas."""
        oauth = self._oauth_entry.get().strip()
        client_id = self._client_entry.get().strip()

        # Obtener threshold del config
        threshold = self._config.get("duplicate_checker", {}).get("similarity_threshold", 85)

        try:
            self.manager = SyncManager(
                oauth, client_id,
                self.download_folder,
                self.downloader,
                similarity_threshold=threshold,
                filename_pattern=self._config.get("filename_pattern", "{artist} - {title}"),
                subfolder_by_artist=self._config.get("subfolder_by_artist", False)
            )
            # Validar credenciales en el nuevo client para obtener user_id
            self.manager.validate_credentials()
            logger.info(f"SyncManager inicializado (threshold: {threshold}%) y validado")

            # Sincronizar filesystem con DB para recuperar archivos anteriores
            def sync_fs():
                try:
                    results = self.manager.sync_filesystem_to_db()
                    logger.info(f"Sync FS: +{results['added']} archivos, "
                               f"{results['already_tracked']} rastreados")
                except Exception as e:
                    logger.warning(f"Error sincronizando filesystem: {e}")

            threading.Thread(target=sync_fs, daemon=True).start()

            # Cargar likes guardados sin necesidad de verificar de nuevo
            self._load_saved_likes()
        except Exception as e:
            logger.error(f"Error inicializando SyncManager: {e}")

    def _refresh_stats(self):
        """Refresca estadísticas del historial."""
        if not self.manager:
            return

        stats = self.manager.get_history_stats()
        last_sync = self.manager.get_last_sync_info()

        self._history_label.configure(
            text=f"Historial: {stats['total_tracks']} canciones | "
                 f"{stats['total_artists']} artistas"
        )

        if last_sync:
            self._last_sync_label.configure(
                text=f"Ultima sincronizacion: {last_sync['synced_at']} | "
                     f"+{last_sync['new_tracks']} | "
                     f"-{last_sync['skipped']}"
            )

    def _load_config(self) -> dict:
        """Carga config.json."""
        if os.path.exists(self.config_path):
            try:
                with open(self.config_path) as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"Error cargando config: {e}")
        return {}

    def _save_config(self):
        """Guarda credenciales a config.json."""
        config = self._load_config()

        if "soundcloud" not in config:
            config["soundcloud"] = {}

        config["soundcloud"]["oauth_token"] = self._oauth_entry.get().strip()
        config["soundcloud"]["client_id"] = self._client_entry.get().strip()
        config["soundcloud"]["auto_sync"] = self._autosync_var.get()
        config["soundcloud"]["sync_interval_minutes"] = int(self._interval_entry.get())

        try:
            with open(self.config_path, "w") as f:
                json.dump(config, f, indent=2)
            logger.info("Config guardada")
        except Exception as e:
            logger.error(f"Error guardando config: {e}")

    def _load_saved_likes(self):
        """Carga likes guardados de la DB al iniciar."""
        if not self.manager:
            return

        try:
            saved_likes = self.manager.load_saved_likes()
            if saved_likes:
                self._progress_msg.configure(
                    text=f"✓ {len(saved_likes)} likes cargados de tu cuenta"
                )
                logger.info(f"Cargados {len(saved_likes)} likes desde DB")
            else:
                self._progress_msg.configure(
                    text="Sin likes guardados - haz clic en 'Verificar' para obtenerlos"
                )
        except Exception as e:
            logger.error(f"Error cargando likes guardados: {e}")
