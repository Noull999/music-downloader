"""
Interfaz abstracta común que todos los handlers de plataforma deben implementar.
"""
import os
import sys
import shutil
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional, Callable

_FFMPEG_CANDIDATES = {
    "win32": [
        r"C:\ffmpeg\ffmpeg-master-latest-win64-gpl\bin",
        r"C:\ffmpeg\bin",
    ],
    "darwin": [
        "/opt/homebrew/bin",
        "/usr/local/bin",
        "/usr/local/opt/ffmpeg/bin",
    ],
    "linux": [
        "/usr/bin",
        "/usr/local/bin",
        "/usr/local/opt/ffmpeg/bin",
    ]
}


def ffmpeg_location() -> str | None:
    """Retorna la carpeta bin de ffmpeg si existe en una ruta conocida, sino None.
    Busca en rutas específicas por SO, con fallback a PATH del sistema."""
    platform = sys.platform
    candidates = _FFMPEG_CANDIDATES.get(platform, [])
    ffmpeg_name = "ffmpeg.exe" if platform == "win32" else "ffmpeg"

    # Buscar en rutas conocidas
    for path in candidates:
        if os.path.isfile(os.path.join(path, ffmpeg_name)):
            return path

    # Fallback: buscar en PATH del sistema
    ffmpeg_path = shutil.which("ffmpeg")
    if ffmpeg_path:
        return os.path.dirname(ffmpeg_path)

    return None


@dataclass
class TrackMetadata:
    """Metadatos de un track extraídos de la plataforma, sin estado de descarga."""
    url: str
    title: str
    artist: str
    duration: int                           # en segundos
    thumbnail_url: Optional[str] = None
    album: Optional[str] = None
    year: Optional[str] = None
    available_qualities: list = field(default_factory=list)  # ["251kbps Opus", "128kbps AAC", ...]
    platform: str = ""                      # "YouTube", "YouTube Music", "SoundCloud"
    detected_quality: str = ""             # calidad real disponible, ej: "251kbps Opus"
    track_id: str = ""                      # ID único de la plataforma


class BaseHandler(ABC):

    @abstractmethod
    def can_handle(self, url: str) -> bool:
        """Retorna True si este handler puede procesar la URL."""

    @abstractmethod
    def get_metadata(self, url: str) -> list[TrackMetadata]:
        """
        Extrae metadatos sin descargar.
        Retorna lista de 1 elemento para tracks individuales,
        N elementos para playlists/perfiles.
        Lanza RuntimeError si la URL no es válida o no se puede procesar.
        """

    @abstractmethod
    def download(
        self,
        url: str,
        output_path: str,
        quality_preset: dict,
        progress_callback: Callable[[float], None],
        cancel_check: Optional[Callable[[], bool]] = None,
    ) -> str:
        """
        Descarga el track y retorna la ruta absoluta del archivo final.
        - output_path: directorio + nombre base SIN extensión
          (el handler agrega la extensión correcta)
        - quality_preset: dict de quality/presets.py
        - progress_callback: recibe float 0.0-1.0
        - cancel_check: si retorna True, cancelar inmediatamente
        Lanza RuntimeError ante errores conocidos (privado, región, etc.)
        """

    # ── Helpers compartidos ──────────────────────────────────────────── #

    def _best_audio_quality(self, formats: list[dict]) -> str:
        """Detecta la mejor calidad de audio disponible y retorna string descriptivo."""
        audio = [
            f for f in formats
            if f.get("acodec") not in (None, "none")
            and (f.get("vcodec") in (None, "none") or not f.get("vcodec"))
        ]
        if not audio:
            return ""
        best = max(audio, key=lambda f: f.get("abr") or f.get("tbr") or 0)
        bitrate = int(best.get("abr") or best.get("tbr") or 0)
        codec = (best.get("acodec") or "audio").split(".")[0].capitalize()
        return f"{bitrate}kbps {codec}" if bitrate else codec

    def _all_audio_qualities(self, formats: list[dict]) -> list[str]:
        """Retorna lista de calidades de audio disponibles ordenadas de mayor a menor."""
        seen: set[str] = set()
        result: list[str] = []
        audio = [
            f for f in formats
            if f.get("acodec") not in (None, "none")
            and (f.get("vcodec") in (None, "none") or not f.get("vcodec"))
            and f.get("abr")
        ]
        for f in sorted(audio, key=lambda x: x.get("abr") or 0, reverse=True):
            bitrate = int(f.get("abr") or 0)
            codec = (f.get("acodec") or "").split(".")[0].capitalize()
            label = f"{bitrate}kbps {codec}" if bitrate else codec
            if label and label not in seen:
                seen.add(label)
                result.append(label)
        return result
