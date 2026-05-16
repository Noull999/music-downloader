"""
Script de debug para monitorear descargas y detectar congelamientos.
"""
import threading
import time
import logging
from datetime import datetime

logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    handlers=[
        logging.FileHandler('debug_download.log'),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger('debug_download')

class ThreadMonitor:
    """Monitorea threads para detectar congelamientos."""

    def __init__(self):
        self.last_callback_time = {}
        self.callback_counts = {}
        self.lock = threading.Lock()

    def log_callback(self, callback_name, value=None):
        """Registra una llamada a callback."""
        with self.lock:
            now = time.time()
            self.last_callback_time[callback_name] = now
            self.callback_counts[callback_name] = self.callback_counts.get(callback_name, 0) + 1

            # Log cada 10 callbacks para ver patron
            count = self.callback_counts[callback_name]
            if count % 10 == 0 or count <= 5:
                logger.info(f"[CB] {callback_name} #{count} v={value}")

    def check_stuck(self, timeout=5.0):
        """Verifica si algún callback está atascado."""
        with self.lock:
            now = time.time()
            for name, last_time in self.last_callback_time.items():
                elapsed = now - last_time
                if elapsed > timeout:
                    logger.warning(f"[STUCK] Callback '{name}' atascado por {elapsed:.1f}s")

    def print_stats(self):
        """Imprime estadísticas de callbacks."""
        with self.lock:
            logger.info("=== Stats de Callbacks ===")
            for name, count in self.callback_counts.items():
                last_time = self.last_callback_time.get(name, 0)
                elapsed = time.time() - last_time if last_time else 0
                logger.info(f"  {name}: count={count}, last_elapsed={elapsed:.2f}s")

# Instancia global
_monitor = ThreadMonitor()

def patch_download_manager():
    """Parchea DownloadManager para agregar debug."""
    from download_manager import DownloadManager

    original_submit = DownloadManager.submit_download

    def patched_submit(self, track, handler, *args, **kwargs):
        logger.info(f"[START] Iniciando descarga: {track.title}")
        _monitor.callback_counts.clear()
        _monitor.last_callback_time.clear()

        # Envolver callbacks
        on_progress = kwargs.get('on_progress') or args[8] if len(args) > 8 else None
        on_status = kwargs.get('on_status') or args[9] if len(args) > 9 else None

        if on_progress:
            original_progress = on_progress
            def debug_progress(v):
                _monitor.log_callback('on_progress', v)
                try:
                    original_progress(v)
                except Exception as e:
                    logger.error(f"❌ Error en on_progress: {e}", exc_info=True)
            kwargs['on_progress'] = debug_progress

        if on_status:
            original_status = on_status
            def debug_status(status, msg):
                _monitor.log_callback('on_status', status)
                logger.debug(f"Status: {status} - {msg}")
                try:
                    original_status(status, msg)
                except Exception as e:
                    logger.error(f"❌ Error en on_status: {e}", exc_info=True)
            kwargs['on_status'] = debug_status

        return original_submit(self, track, handler, *args, **kwargs)

    DownloadManager.submit_download = patched_submit
    logger.info("[OK] DownloadManager parchado para debug")

def monitor_threads():
    """Monitorea estado de threads cada 2 segundos."""
    while True:
        time.sleep(2)
        _monitor.check_stuck(timeout=5)
        active_threads = threading.active_count()
        if active_threads > 10:
            logger.warning(f"[WARNING] {active_threads} threads activos")

if __name__ == '__main__':
    logger.info("=" * 60)
    logger.info("[DEBUG] Debug Download Monitor iniciado")
    logger.info("=" * 60)

    patch_download_manager()

    # Monitoreo en background
    monitor_thread = threading.Thread(target=monitor_threads, daemon=True)
    monitor_thread.start()

    logger.info("[OK] Monitor activo. Ahora ejecuta la app normalmente.")
    logger.info("  Verifica debug_download.log para detalles.")
