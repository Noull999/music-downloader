"""
TrackInfo: estado de descarga + metadatos de la plataforma.
Combina TrackMetadata (datos estáticos) con estado mutable de GUI.
"""
from dataclasses import dataclass, field
from handlers.base_handler import TrackMetadata

# ── Constantes de estado ─────────────────────────────────────────────── #
STATUS_PENDING = "pending"
STATUS_FETCHING = "fetching"
STATUS_DOWNLOADING = "downloading"
STATUS_DONE = "done"
STATUS_ERROR = "error"
STATUS_SKIP = "skip"
STATUS_CANCELLED = "cancelled"

ALL_STATUSES = (
    STATUS_PENDING, STATUS_FETCHING, STATUS_DOWNLOADING,
    STATUS_DONE, STATUS_ERROR, STATUS_SKIP, STATUS_CANCELLED,
)


@dataclass
class TrackInfo:
    """
    Unidad de trabajo en la GUI: metadatos de plataforma + estado de descarga.
    Inmutable en cuanto a identidad (url), mutable en cuanto a estado.
    """
    # ── Metadatos de plataforma ──────────────────────────────────────── #
    url: str
    title: str = "Cargando..."
    artist: str = ""
    duration: int = 0
    thumbnail_url: str = ""
    album: str = ""
    year: str = ""
    platform: str = ""                # "YouTube", "YouTube Music", "SoundCloud"
    detected_quality: str = ""        # ej: "251kbps Opus", "128kbps Mp3"
    available_qualities: list = field(default_factory=list)
    track_id: str = ""
    genre: str = ""                   # género según la plataforma (texto libre)

    # ── Estado de descarga (mutable) ─────────────────────────────────── #
    status: str = STATUS_PENDING
    progress: float = 0.0
    error_msg: str = ""
    local_path: str = ""

    # ── Helpers ──────────────────────────────────────────────────────── #

    def duration_str(self) -> str:
        if not self.duration:
            return "--:--"
        m, s = divmod(self.duration, 60)
        return f"{m}:{s:02d}"

    def platform_quality_str(self) -> str:
        """Línea de info para la GUI: 'YouTube Music · 3:39 · 251kbps Opus'"""
        parts = [p for p in [self.platform, self.duration_str(), self.detected_quality] if p]
        return "  ·  ".join(parts)

    @classmethod
    def from_metadata(cls, meta: TrackMetadata) -> "TrackInfo":
        return cls(
            url=meta.url,
            title=meta.title,
            artist=meta.artist,
            duration=meta.duration,
            thumbnail_url=meta.thumbnail_url or "",
            album=meta.album or "",
            year=meta.year or "",
            platform=meta.platform,
            detected_quality=meta.detected_quality,
            available_qualities=list(meta.available_qualities or []),
            track_id=meta.track_id,
            genre=meta.genre or "",
        )

    def update_from_metadata(self, meta: TrackMetadata) -> None:
        """Actualiza los campos de metadatos sin tocar el estado de descarga."""
        self.title = meta.title
        self.artist = meta.artist
        self.duration = meta.duration
        self.thumbnail_url = meta.thumbnail_url or ""
        self.album = meta.album or ""
        self.year = meta.year or ""
        self.platform = meta.platform
        self.detected_quality = meta.detected_quality
        self.available_qualities = list(meta.available_qualities or [])
        self.track_id = meta.track_id
        self.genre = meta.genre or ""
