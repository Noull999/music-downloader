"""
Notificaciones del sistema operativo (toast nativo de Windows 10/11).

Antes usaba plyer (balloon tips legacy vía Shell_NotifyIcon), que en Windows
10/11 no se muestran de forma confiable y corren en un thread separado que
traga cualquier excepción en silencio. win11toast usa la API real de toast
notifications (WinRT), se ve con ícono/nombre de la app y queda en el
Centro de actividades.
"""
import logging
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

try:
    from win11toast import notify as _win_notify
    TOAST_AVAILABLE = True
except ImportError:
    TOAST_AVAILABLE = False
    logger.warning("win11toast no instalado; notificaciones deshabilitadas")

# Resuelve el ícono tanto en desarrollo (.py) como empaquetado (.exe):
# los datas empaquetados se extraen a _MEIPASS, no a la carpeta del .exe.
if getattr(sys, "frozen", False):
    _RESOURCES = getattr(sys, "_MEIPASS", str(Path(sys.executable).parent))
else:
    _RESOURCES = str(Path(__file__).resolve().parent.parent)

_ICON_PATH = str(Path(_RESOURCES) / "assets" / "icon.png")
if not Path(_ICON_PATH).is_file():
    _ICON_PATH = None


class Notifier:
    """Muestra notificaciones toast del sistema. Si win11toast no está
    disponible o falla, cae a logging (nunca lanza)."""

    APP_NAME = "Music Downloader"
    APP_ID = "Music Downloader"

    @staticmethod
    def notify(title: str, message: str, timeout: int = 5):
        """
        Muestra una notificación toast.

        Args:
            title: Título de la notificación
            message: Cuerpo del mensaje
            timeout: Segundos aprox. antes de que se auto-cierre (Windows
                     solo distingue "short"/"long"; >7s usa "long")
        """
        if not TOAST_AVAILABLE:
            logger.info(f"[NOTIF] {title}: {message}")
            return

        try:
            _win_notify(
                title,
                message,
                icon=_ICON_PATH,
                app_id=Notifier.APP_ID,
                duration="long" if timeout > 7 else "short",
            )
            logger.debug(f"Notificación mostrada: {title}")
        except Exception as e:
            # Si la notificación falla, log pero no crashear el flujo de sync
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
            title = "Sincronización completada"
            message = f"No hay canciones nuevas ({skipped} ya descargadas)"
        elif errors > 0:
            title = "Sincronización con errores"
            message = (
                f"{new} descargadas  |  "
                f"{errors} errores  |  "
                f"{skipped} omitidas"
            )
        else:
            title = f"{new} canción(es) nueva(s) descargada(s)"
            message = f"{skipped} ya existían y fueron omitidas"

        Notifier.notify(title, message)

    @staticmethod
    def notify_new_like_detected(title: str, artist: str):
        """Notifica cuando se detecta un like nuevo."""
        Notifier.notify(
            "Nuevo like detectado",
            f"{artist} - {title}\nDescargando...",
            timeout=3
        )

    @staticmethod
    def notify_error(error_title: str, error_msg: str):
        """Notifica errores importantes."""
        Notifier.notify(error_title, error_msg, timeout=10)

    @staticmethod
    def notify_sync_started(total_likes: int):
        """Notifica cuando comienza una sincronización."""
        Notifier.notify(
            "Sincronización iniciada",
            f"Procesando {total_likes} likes...",
            timeout=2
        )
