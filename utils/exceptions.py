"""
Excepciones personalizadas para manejo de errores coherente.
"""


class MusicDownloaderError(Exception):
    """Excepción base para toda la aplicación."""
    pass


class DependencyNotFoundError(MusicDownloaderError):
    """Dependencia externa no encontrada (ffmpeg, ffprobe, etc.)."""
    pass


class DependencyVersionError(MusicDownloaderError):
    """Versión de dependencia insuficiente."""
    pass


class NetworkError(MusicDownloaderError):
    """Error de red (timeout, conexión rechazada, etc.)."""
    pass


class URLInvalidError(MusicDownloaderError):
    """URL inválida o no soportada."""
    pass


class RateLimitError(MusicDownloaderError):
    """Rate limit de API alcanzado (retry necesario)."""
    pass


class VideoUnavailableError(MusicDownloaderError):
    """Video/canción no disponible (privado, eliminado, etc.)."""
    pass


class DownloadError(MusicDownloaderError):
    """Error genérico durante descarga."""
    pass


class ConfigurationError(MusicDownloaderError):
    """Error en configuración de la aplicación."""
    pass


class DatabaseError(MusicDownloaderError):
    """Error en operaciones de base de datos."""
    pass
