"""
Lista de tracks: TrackListFrame (scrollable) + TrackRow (fila individual).
Muestra plataforma, calidad detectada, progreso y estado por color.
"""
import threading
import customtkinter as ctk

from models import (
    TrackInfo,
    STATUS_PENDING, STATUS_FETCHING, STATUS_DOWNLOADING,
    STATUS_DONE, STATUS_ERROR, STATUS_SKIP, STATUS_CANCELLED,
)
from utils.metadata import load_thumbnail_image

# ── Mapa de estado → color texto ─────────────────────────────────────── #
_STATUS_COLOR: dict[str, str] = {
    STATUS_PENDING:     "#9ca3af",   # gris claro
    STATUS_FETCHING:    "#fbbf24",   # amarillo
    STATUS_DOWNLOADING: "#60a5fa",   # azul
    STATUS_DONE:        "#4ade80",   # verde
    STATUS_ERROR:       "#f87171",   # rojo
    STATUS_SKIP:        "#a78bfa",   # violeta
    STATUS_CANCELLED:   "#6b7280",   # gris oscuro
}

_STATUS_LABEL: dict[str, str] = {
    STATUS_PENDING:     "Pendiente",
    STATUS_FETCHING:    "Procesando...",
    STATUS_DOWNLOADING: "Descargando",
    STATUS_DONE:        "Completado",
    STATUS_ERROR:       "Error",
    STATUS_SKIP:        "Ya existe",
    STATUS_CANCELLED:   "Cancelado",
}

# Icono de plataforma (texto, sin emojis para evitar problemas de encoding en Windows)
_PLATFORM_ICON: dict[str, str] = {
    "YouTube":        "[YT]",
    "YouTube Music":  "[YTM]",
    "SoundCloud":     "[SC]",
}

_THUMB_SIZE = (48, 48)


class TrackRow(ctk.CTkFrame):
    """Fila individual en la lista de tracks."""

    def __init__(
        self,
        master,
        track: TrackInfo,
        on_download: callable,
        on_cancel: callable,
        **kwargs,
    ):
        super().__init__(master, corner_radius=8, **kwargs)
        self.track = track
        self._on_download = on_download
        self._on_cancel = on_cancel
        self._selected = ctk.BooleanVar(value=False)
        self._thumb_ref = None   # evita GC de CTkImage

        self._build()
        self._load_thumb_async()

    # ------------------------------------------------------------------ #
    # Construccion                                                         #
    # ------------------------------------------------------------------ #

    def _build(self):
        self.grid_columnconfigure(2, weight=1)

        # Checkbox
        ctk.CTkCheckBox(
            self, text="", variable=self._selected, width=24
        ).grid(row=0, column=0, padx=(8, 4), pady=8, rowspan=3)

        # Thumbnail
        self._thumb = ctk.CTkLabel(
            self, text="?", width=_THUMB_SIZE[0], height=_THUMB_SIZE[1],
            fg_color="#1f2937", corner_radius=6,
            font=ctk.CTkFont(size=18),
        )
        self._thumb.grid(row=0, column=1, padx=(4, 10), pady=8, rowspan=3)

        # Titulo
        self._title_lbl = ctk.CTkLabel(
            self, text=_trunc(self.track.title, 55),
            anchor="w", font=ctk.CTkFont(size=13, weight="bold"),
        )
        self._title_lbl.grid(row=0, column=2, sticky="ew", padx=4, pady=(8, 0))

        # Artista
        self._artist_lbl = ctk.CTkLabel(
            self, text=_trunc(self.track.artist, 45),
            anchor="w", font=ctk.CTkFont(size=11), text_color="#d1d5db",
        )
        self._artist_lbl.grid(row=1, column=2, sticky="ew", padx=4, pady=0)

        # Linea de plataforma + calidad
        self._info_lbl = ctk.CTkLabel(
            self, text=self._info_text(),
            anchor="w", font=ctk.CTkFont(size=11), text_color="#6b7280",
        )
        self._info_lbl.grid(row=2, column=2, sticky="ew", padx=4, pady=(0, 8))

        # Barra de progreso + porcentaje
        progress_row = ctk.CTkFrame(self, fg_color="transparent")
        progress_row.grid(row=3, column=1, columnspan=2, sticky="ew", padx=10, pady=(0, 8))
        progress_row.grid_columnconfigure(0, weight=1)

        self._progress = ctk.CTkProgressBar(progress_row, height=14, corner_radius=4)
        self._progress.set(0)
        self._progress.grid(row=0, column=0, sticky="ew")

        self._pct_lbl = ctk.CTkLabel(
            progress_row, text="0%", width=36,
            font=ctk.CTkFont(size=11), text_color="#9ca3af",
        )
        self._pct_lbl.grid(row=0, column=1, padx=(6, 0))

        # Estado
        self._status_lbl = ctk.CTkLabel(
            self, text=_STATUS_LABEL[STATUS_PENDING],
            width=90, font=ctk.CTkFont(size=11),
            text_color=_STATUS_COLOR[STATUS_PENDING],
        )
        self._status_lbl.grid(row=0, column=3, rowspan=2, padx=10)

        # Botones
        btn_col = ctk.CTkFrame(self, fg_color="transparent")
        btn_col.grid(row=0, column=4, rowspan=3, padx=(0, 8), pady=8)

        self._dl_btn = ctk.CTkButton(
            btn_col, text="Bajar", width=60, height=28,
            command=lambda: self._on_download(self.track),
            font=ctk.CTkFont(size=12),
        )
        self._dl_btn.pack(pady=(0, 4))

        self._cancel_btn = ctk.CTkButton(
            btn_col, text="X", width=60, height=28,
            fg_color="#6b7280", hover_color="#4b5563",
            command=lambda: self._on_cancel(self.track),
            state="disabled",
        )
        self._cancel_btn.pack()

    # ------------------------------------------------------------------ #
    # Actualizaciones de estado (llamar desde hilo principal)             #
    # ------------------------------------------------------------------ #

    def update_progress(self, value: float):
        self._progress.set(value)
        self._pct_lbl.configure(text=f"{int(value * 100)}%")

    def update_status(self, status: str, error_msg: str = ""):
        self.track.status = status
        if error_msg:
            self.track.error_msg = error_msg

        label = _STATUS_LABEL.get(status, status)
        if status == STATUS_ERROR and error_msg:
            label = _trunc(error_msg, 28)

        color = _STATUS_COLOR.get(status, "#9ca3af")
        self._status_lbl.configure(text=label, text_color=color)

        is_active = status in (STATUS_DOWNLOADING, STATUS_FETCHING)
        self._cancel_btn.configure(state="normal" if is_active else "disabled")
        self._dl_btn.configure(
            state="disabled" if is_active else "normal"
        )

    def update_track_info(self, track: TrackInfo):
        """Refresca titulo/artista/plataforma despues del fetch de metadatos."""
        self.track = track
        self._title_lbl.configure(text=_trunc(track.title, 55))
        self._artist_lbl.configure(text=_trunc(track.artist, 45))
        self._info_lbl.configure(text=self._info_text())
        if track.thumbnail_url and not self._thumb_ref:
            self._load_thumb_async()

    @property
    def is_selected(self) -> bool:
        return self._selected.get()

    # ------------------------------------------------------------------ #
    # Internos                                                             #
    # ------------------------------------------------------------------ #

    def _info_text(self) -> str:
        icon = _PLATFORM_ICON.get(self.track.platform, "")
        parts = [p for p in [icon, self.track.duration_str(), self.track.detected_quality] if p]
        return "  ".join(parts)

    def _load_thumb_async(self):
        url = self.track.thumbnail_url
        if not url:
            return

        def worker():
            img = load_thumbnail_image(url, _THUMB_SIZE)
            if img:
                self.after(0, lambda: self._set_thumb(img))

        threading.Thread(target=worker, daemon=True).start()

    def _set_thumb(self, pil_img):
        try:
            ctk_img = ctk.CTkImage(light_image=pil_img, dark_image=pil_img, size=_THUMB_SIZE)
            self._thumb_ref = ctk_img
            self._thumb.configure(image=ctk_img, text="")
        except Exception:
            pass


# ── Contenedor scrollable ─────────────────────────────────────────────── #

class TrackListFrame(ctk.CTkScrollableFrame):
    """Contenedor scrollable de TrackRow widgets, indexados por URL."""

    def __init__(self, master, on_download: callable, on_cancel: callable, **kwargs):
        super().__init__(master, **kwargs)
        self._on_download = on_download
        self._on_cancel = on_cancel
        self._rows: dict[str, TrackRow] = {}
        self.grid_columnconfigure(0, weight=1)

        self._empty_label = ctk.CTkLabel(
            self,
            text='Pegá links arriba\no abrí "Ver mis Likes" en la pestaña Sincronizar',
            text_color="#4b5563",
            font=ctk.CTkFont(size=13),
            justify="center",
        )
        self._empty_label.grid(row=0, column=0, pady=60)

    def add_track(self, track: TrackInfo) -> TrackRow:
        if track.url in self._rows:
            return self._rows[track.url]
        if not self._rows:
            self._empty_label.grid_remove()
        row = TrackRow(
            self, track=track,
            on_download=self._on_download,
            on_cancel=self._on_cancel,
            fg_color=("#1e293b", "#0f172a"),
        )
        row.grid(row=len(self._rows), column=0, sticky="ew", padx=6, pady=4)
        self._rows[track.url] = row
        return row

    def get_row(self, url: str) -> TrackRow | None:
        return self._rows.get(url)

    def get_selected(self) -> list[TrackInfo]:
        return [r.track for r in self._rows.values() if r.is_selected]

    def get_all(self) -> list[TrackInfo]:
        return [r.track for r in self._rows.values()]

    def clear(self):
        for row in self._rows.values():
            row.destroy()
        self._rows.clear()
        self._empty_label.grid()

    def reindex_row(self, old_url: str, new_url: str):
        """Actualiza el índice cuando la URL canónica difiere de la URL original."""
        if old_url != new_url and old_url in self._rows:
            self._rows[new_url] = self._rows.pop(old_url)

    def update_progress(self, url: str, value: float):
        row = self._rows.get(url)
        if row:
            row.update_progress(value)

    def update_status(self, url: str, status: str, error_msg: str = ""):
        row = self._rows.get(url)
        if row:
            row.update_status(status, error_msg)

    def count_by_status(self, *statuses) -> int:
        return sum(1 for r in self._rows.values() if r.track.status in statuses)


def _trunc(text: str, n: int) -> str:
    return text if len(text) <= n else text[:n - 1] + "..."
