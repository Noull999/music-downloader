"""
Queue de post-procesado con FFmpeg parallelizado.
Permite 2-3 procesos ffmpeg simultáneos sin bloquear descargas.
Uso: FFmpegQueue.enqueue(file, metadata, post_config)
"""
import logging
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
        # Antes había además una queue.Queue propia con un hilo despachador
        # que llamaba a PostProcessor directamente: el executor se creaba
        # pero no se usaba nunca, así que el post-procesado era SERIAL pese
        # a que el log decía "2 workers paralelos". Con el executor haciendo
        # el trabajo, su cola interna ya cumple la función de la otra.
        self._executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="ffmpeg")
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
        self._executor.submit(self._run_task, task)
        logger.debug(f"📝 Post-procesado encolado: {file_path}")

    @staticmethod
    def _run_task(task: FFmpegQueueTask) -> None:
        """
        Procesa una tarea. Cada una toca su propio archivo, así que dos en
        paralelo no se pisan. Nunca propaga: se ejecuta dentro del executor
        y una excepción ahí quedaría enterrada en un Future que nadie mira.
        """
        from quality.post_processor import PostProcessor

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

    def shutdown(self):
        """Detiene los workers, esperando a que terminen lo encolado."""
        self._executor.shutdown(wait=True)
        logger.info("✓ FFmpegQueue detenido")
