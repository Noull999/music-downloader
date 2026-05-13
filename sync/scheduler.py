"""
Auto-sincronización en background sin bloquear la GUI.
Ejecuta sync periódicamente (cada N minutos) en un thread separado.
"""
import threading
import time
import logging
from typing import Callable, Optional

logger = logging.getLogger(__name__)


class AutoSyncScheduler:
    """
    Corre sincronizaciones automáticas periódicamente.
    - No bloquea la GUI (corre en thread de background)
    - Thread-safe
    - Permite cambiar intervalo sin reiniciar
    """

    def __init__(
        self,
        sync_manager,
        interval_minutes: int = 30,
        use_sync_recent: bool = False
    ):
        """
        Args:
            sync_manager: Instancia de SyncManager
            interval_minutes: Intervalo entre sincs (default 30 min)
            use_sync_recent: Si True, usa sync_recent (más rápido)
                           Si False, usa sync_once (completo)
        """
        self.sync_manager = sync_manager
        self.interval = interval_minutes * 60  # Convertir a segundos
        self.use_sync_recent = use_sync_recent
        self._thread = None
        self._stop_event = threading.Event()
        self.is_running = False

        # Callbacks para notificar a la GUI
        self.on_sync_start: Optional[Callable] = None
        self.on_sync_complete: Optional[Callable[[dict], None]] = None

        logger.info(
            f"AutoSyncScheduler iniciado: cada {interval_minutes} minutos "
            f"({'sync_recent' if use_sync_recent else 'sync_once'})"
        )

    def start(self):
        """Inicia el scheduler en background."""
        if self.is_running:
            logger.warning("Scheduler ya está corriendo")
            return

        logger.info("Iniciando auto-sync scheduler")
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        self.is_running = True

    def stop(self):
        """Detiene el scheduler limpiamente."""
        if not self.is_running:
            return

        logger.info("Deteniendo auto-sync scheduler")
        self._stop_event.set()
        self.is_running = False
        if self._thread:
            self._thread.join(timeout=5)

    def set_interval(self, minutes: int):
        """
        Cambia el intervalo sin reiniciar.
        Toma efecto en la siguiente sincronización.

        Args:
            minutes: Nuevo intervalo en minutos
        """
        self.interval = minutes * 60
        logger.info(f"Intervalo cambiado a {minutes} minutos")

    def _loop(self):
        """
        Loop principal del scheduler.
        Ejecuta sync cada interval segundos.
        """
        while not self._stop_event.is_set():
            try:
                logger.info(f"Auto-sync iniciada (interval: {self.interval}s)")

                # Callback: comenzó la sync
                if self.on_sync_start:
                    try:
                        self.on_sync_start()
                    except Exception as e:
                        logger.error(f"Error en on_sync_start: {e}")

                # Ejecutar sync
                try:
                    if self.use_sync_recent:
                        results = self.sync_manager.sync_recent(count=10)
                    else:
                        results = self.sync_manager.sync_once()
                except Exception as e:
                    logger.error(f"Error en auto-sync: {e}")
                    results = {
                        'new': 0, 'skipped': 0, 'errors': 1,
                        'tracks': [], 'duplicates': []
                    }

                # Callback: terminó la sync
                if self.on_sync_complete:
                    try:
                        self.on_sync_complete(results)
                    except Exception as e:
                        logger.error(f"Error en on_sync_complete: {e}")

            except Exception as e:
                logger.error(f"Error no esperado en _loop: {e}")

            # Esperar el intervalo
            # Chequeamos stop event cada segundo para poder detener rápido
            for _ in range(self.interval):
                if self._stop_event.is_set():
                    logger.info("Loop del scheduler detenido")
                    return
                time.sleep(1)
