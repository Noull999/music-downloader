"""
Detecta qué handler corresponde a una URL dada.
Agregar nuevos handlers aquí para soportar más plataformas.
"""
from handlers.base_handler import BaseHandler
from handlers.soundcloud_handler import SoundCloudHandler
from handlers.youtube_handler import YouTubeHandler

# Orden importa: plataformas más específicas primero
_HANDLERS: list[BaseHandler] = [
    YouTubeHandler(),
    SoundCloudHandler(),
]


def detect_handler(url: str) -> BaseHandler:
    """
    Retorna el handler apropiado para la URL.
    Lanza ValueError si ningún handler puede manejarla.
    """
    for handler in _HANDLERS:
        if handler.can_handle(url):
            return handler
    raise ValueError(
        f"URL no soportada. Solo se aceptan URLs de YouTube y SoundCloud.\n({url})"
    )


def detect_platform_name(url: str) -> str:
    """Retorna el nombre de la plataforma sin instanciar el handler completo."""
    url = url.strip().lower()
    if "soundcloud.com" in url:
        return "SoundCloud"
    if "music.youtube.com" in url:
        return "YouTube Music"
    if "youtube.com" in url or "youtu.be" in url:
        return "YouTube"
    return "Desconocido"


def supported_domains() -> list[str]:
    """Lista de dominios soportados (para validación rápida)."""
    return [
        "soundcloud.com",
        "youtube.com",
        "youtu.be",
        "music.youtube.com",
    ]
