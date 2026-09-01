"""
Queue de post-procesado con FFmpeg parallelizado.
Permite 2-3 procesos ffmpeg simultáneos sin bloquear descargas.
Uso: FFmpegQueue.enqueue(file, metadata, post_config)
"""
import logging
import queue
import threading
from concurrent.futures import ThreadPoolExecutor
from typing import Optional, Callable

logger = logging.getLogger(__name__)


class FFmpegQueueTask:
    """Representa un archivo que requiere post-procesado."""

    def __init__(
        self,
        file_path: str,
        metadata: dict,
        thumbnail_url: str,
        post_config: dict,
        on_complete: Optional[Callable[[str], None]] = None,
        on_error: Optional[Callable[[str, str], None]] = None,
    ):
        self.file_path = file_path
        self.metadata = metadata
        self.thumbnail_url = thumbnail_url
        self.post_config = post_config
        self.on_complete = on_complete
        self.on_error = on_error


class FFmpegQueue:
    """Gestor de cola de post-procesado con paralelismo."""

    _instance: Optional["FFmpegQueue"] = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._init_queue()
        return cls._instance

    def _init_queue(self):
        self._task_queue: queue.Queue[FFmpegQueueTask] = queue.Queue()
        self._executor = ThreadPoolExecutor(max_workers=2)  # 2 procesos ffmpeg paralelos
        self._running = True
        self._worker_thread = threading.Thread(target=self._process_queue, daemon=True)
        self._worker_thread.start()
        logger.info("✓ FFmpegQueue iniciado (2 workers paralelos)")

    def enqueue(
        self,
        file_path: str,
        metadata: dict,
        post_config: dict,
        thumbnail_url: str = "",
        on_complete: Optional[Callable[[str], None]] = None,
        on_error: Optional[Callable[[str, str], None]] = None,
    ) -> None:
        """Encola un archivo para post-procesado."""
        task = FFmpegQueueTask(
            file_path, metadata, thumbnail_url, post_config, on_complete, on_error
        )
        self._task_queue.put(task)
        logger.debug(f"📝 Post-procesado encolado: {file_path}")

    def _process_queue(self):
        """Worker que procesa queue de post-procesado."""
        from quality.post_processor import PostProcessor

        while self._running:
            try:
                task = self._task_queue.get(timeout=1)
                if task is None:  # sentinel to stop
                    break

                try:
                    pp = PostProcessor(task.post_config)
                    pp.process(task.file_path, task.metadata, task.thumbnail_url)

                    if task.on_complete:
                        try:
                            task.on_complete(task.file_path)
                        except Exception as e:
                            logger.error(f"Error en on_complete: {e}")

                    logger.debug(f"✓ Post-procesado completado: {task.file_path}")

                except Exception as exc:
                    logger.warning(f"Error en post-procesado de {task.file_path}: {exc}")
                    if task.on_error:
                        try:
                            task.on_error(task.file_path, str(exc))
                        except Exception as e:
                            logger.error(f"Error en on_error: {e}")

            except queue.Empty:
                continue
            except Exception as exc:
                logger.error(f"Error procesando queue: {exc}")

    def shutdown(self):
        """Detiene queue y workers."""
        self._running = False
        self._task_queue.put(None)  # sentinel
        self._executor.shutdown(wait=True)
        if self._worker_thread.is_alive():
            self._worker_thread.join(timeout=5)
        logger.info("✓ FFmpegQueue detenido")
