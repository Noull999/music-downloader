"""
StatusBar: Barra de estado mejorada con indicadores visuales.
Muestra: FFmpeg status, Descargas en progreso, Información del sistema.
"""
import customtkinter as ctk
from typing import Optional


class StatusBar(ctk.CTkFrame):
    """Barra de estado mejorada con múltiples indicadores."""

    def __init__(self, master, **kwargs):
        super().__init__(master, **kwargs)

        # Layout: izquierda | centro | derecha
        self.grid_columnconfigure(1, weight=1)

        # 🔴 Izquierda: Status de conexiones
        left_frame = ctk.CTkFrame(self, fg_color="transparent")
        left_frame.grid(row=0, column=0, padx=10, pady=5, sticky="w")

        self.ffmpeg_indicator = ctk.CTkLabel(
            left_frame,
            text="✓ FFmpeg: OK",
            font=ctk.CTkFont(size=11),
            text_color="#10b981"
        )
        self.ffmpeg_indicator.pack(side="left", padx=(0, 15))

        self.ytdlp_indicator = ctk.CTkLabel(
            left_frame,
            text="✓ yt-dlp: OK",
            font=ctk.CTkFont(size=11),
            text_color="#10b981"
        )
        self.ytdlp_indicator.pack(side="left")

        # 🟡 Centro: Status de descargas
        center_frame = ctk.CTkFrame(self, fg_color="transparent")
        center_frame.grid(row=0, column=1, padx=10, pady=5, sticky="ew")
        center_frame.grid_columnconfigure(0, weight=1)

        self.download_status = ctk.CTkLabel(
            center_frame,
            text="Listo para descargar",
            font=ctk.CTkFont(size=11),
            text_color="#9ca3af"
        )
        self.download_status.pack(side="left")

        # 🟢 Derecha: Info del sistema
        right_frame = ctk.CTkFrame(self, fg_color="transparent")
        right_frame.grid(row=0, column=2, padx=10, pady=5, sticky="e")

        self.system_info = ctk.CTkLabel(
            right_frame,
            text="3 workers",
            font=ctk.CTkFont(size=10),
            text_color="#6b7280"
        )
        self.system_info.pack(side="right", padx=(0, 5))

    def set_ffmpeg_status(self, version: Optional[str] = None, error: Optional[str] = None):
        """Actualiza indicador de FFmpeg."""
        if error:
            self.ffmpeg_indicator.configure(
                text=f"✗ FFmpeg: {error}",
                text_color="#ef4444"
            )
        elif version:
            self.ffmpeg_indicator.configure(
                text=f"✓ FFmpeg v{version}",
                text_color="#10b981"
            )

    def set_ytdlp_status(self, version: Optional[str] = None, error: Optional[str] = None):
        """Actualiza indicador de yt-dlp."""
        if error:
            self.ytdlp_indicator.configure(
                text=f"✗ yt-dlp: {error}",
                text_color="#ef4444"
            )
        elif version:
            self.ytdlp_indicator.configure(
                text=f"✓ yt-dlp: {version}",
                text_color="#10b981"
            )

    def set_download_status(self, status: str, color: str = "#9ca3af"):
        """Actualiza status de descargas."""
        self.download_status.configure(
            text=status,
            text_color=color
        )

    def set_system_info(self, workers: int = 3, queue_size: int = 0):
        """Actualiza info del sistema."""
        info = f"{workers} workers"
        if queue_size > 0:
            info += f" • {queue_size} en cola"
        self.system_info.configure(text=info)

    def mark_downloading(self):
        """Marca como "descargando"."""
        self.set_download_status("⬇️  Descargando...", "#3b82f6")

    def mark_idle(self):
        """Marca como "inactivo"."""
        self.set_download_status("Listo para descargar", "#9ca3af")

    def mark_paused(self):
        """Marca como "pausado"."""
        self.set_download_status("⏸️  Pausado", "#f59e0b")

    def mark_error(self, msg: str = "Error"):
        """Marca como "error"."""
        self.set_download_status(f"❌ {msg}", "#ef4444")

    def set_text(self, text: str, color: str = "#9ca3af"):
        """Establece texto personalizado en el status bar."""
        self.set_download_status(text, color)
