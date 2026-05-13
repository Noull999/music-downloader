"""
Notificaciones del sistema operativo (Windows/Mac/Linux).
Usa plyer para compatibilidad cross-platform.
"""
import logging

logger = logging.getLogger(__name__)

try:
    from plyer import notification
    PLYER_AVAILABLE = True
except ImportError:
    PLYER_AVAILABLE = False
    logger.warning("plyer no instalado; notificaciones deshabilitadas")


class Notifier:
    """
    Muestra notificaciones del sistema operativo.
    Si plyer no está disponible, fallback a logging.
    """

    APP_NAME = "Music Downloader"
    ICON_PATH = None  # Opcional: ruta a un .ico/.png para el ícono

    @staticmethod
    def notify(title: str, message: str, timeout: int = 5):
        """
        Muestra notificación del sistema.

        Args:
            title: Título de la notificación
            message: Cuerpo del mensaje
            timeout: Segundos para que desaparezca (algunos OS lo ignoran)
        """
        if not PLYER_AVAILABLE:
            logger.info(f"[NOTIF] {title}: {message}")
            return

        try:
            notification.notify(
                title=title,
                message=message,
                app_name=Notifier.APP_NAME,
                app_icon=Notifier.ICON_PATH,
                timeout=timeout,
            )
            logger.debug(f"Notificación mostrada: {title}")
        except Exception as e:
            # Si la notificación falla (raro), log pero no crashear
            logger.warning(f"Error mostrando notificación: {e}")

    @staticmethod
    def notify_sync_complete(new: int, skipped: int, errors: int):
        """
        Notifica cuando termina una sincronización.

        Args:
            new: Canciones descargadas
            skipped: Canciones omitidas
            errors: Errores durante descarga
        """
        if new == 0 and errors == 0:
            title = "✓ Sincronización completada"
            message = f"No hay canciones nuevas. ({skipped} ya descargadas)"
        elif errors > 0:
            title = "⚠️ Sincronización con errores"
            message = (
                f"✓ {new} descargadas  |  "
                f"⚠️ {errors} errores  |  "
                f"⏭️ {skipped} omitidas"
            )
        else:
            title = f"✓ {new} canción(es) nueva(s) descargada(s)"
            message = f"⏭️ {skipped} ya existían y fueron omitidas"

        Notifier.notify(title, message)

    @staticmethod
    def notify_new_like_detected(title: str, artist: str):
        """
        Notifica cuando se detecta un like nuevo.

        Args:
            title: Título de la canción
            artist: Artista
        """
        Notifier.notify(
            "🎵 Nuevo like detectado",
            f"{artist} - {title}\nDescargando...",
            timeout=3
        )

    @staticmethod
    def notify_error(error_title: str, error_msg: str):
        """
        Notifica errores importantes.

        Args:
            error_title: Tipo de error (ej: "Token inválido")
            error_msg: Detalle del error
        """
        Notifier.notify(
            f"❌ {error_title}",
            error_msg,
            timeout=10
        )

    @staticmethod
    def notify_sync_started(total_likes: int):
        """Notifica cuando comienza una sincronización."""
        Notifier.notify(
            "🔄 Sincronización iniciada",
            f"Procesando {total_likes} likes...",
            timeout=2
        )
