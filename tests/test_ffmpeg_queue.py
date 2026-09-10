"""
Tests de quality/ffmpeg_queue.py: la cola de post-procesado.

Antes creaba un ThreadPoolExecutor(max_workers=2) que NUNCA usaba: las
tareas las corría un hilo despachador propio, una por una. O sea que el
post-procesado era serial pese a que el log decía "2 workers paralelos".
Con "Detectar BPM y tonalidad" activo (~2s por track) eso es un cuello de
botella que además no se veía en ningún lado.
"""
import threading
import time
import unittest
from unittest.mock import patch

from quality.ffmpeg_queue import FFmpegQueue


class TestFFmpegQueue(unittest.TestCase):
    def setUp(self):
        # Es un singleton: para tener una instancia limpia por test hay que
        # soltar la anterior.
        FFmpegQueue._instance = None
        self.cola = FFmpegQueue()

    def tearDown(self):
        FFmpegQueue._instance = None

    def test_procesa_dos_tareas_en_paralelo(self):
        en_curso = []
        max_simultaneas = [0]
        candado = threading.Lock()

        class PostProcessorLento:
            def __init__(self, config):
                pass

            def process(self, path, metadata, thumbnail_url=""):
                with candado:
                    en_curso.append(path)
                    max_simultaneas[0] = max(max_simultaneas[0], len(en_curso))
                time.sleep(0.3)
                with candado:
                    en_curso.remove(path)

        listo = threading.Event()
        completadas = []

        def on_complete(path):
            completadas.append(path)
            if len(completadas) == 2:
                listo.set()

        with patch("quality.post_processor.PostProcessor", PostProcessorLento):
            self.cola.enqueue("a.mp3", {}, {}, on_complete=on_complete)
            self.cola.enqueue("b.mp3", {}, {}, on_complete=on_complete)
            assert listo.wait(timeout=10), "las dos tareas deberían haber terminado"

        assert max_simultaneas[0] == 2, (
            f"esperaba 2 tareas simultáneas, hubo {max_simultaneas[0]} "
            "(el post-procesado quedó serial)"
        )

    def test_un_error_no_frena_la_cola(self):
        procesadas = []

        class PostProcessorQueFalla:
            def __init__(self, config):
                pass

            def process(self, path, metadata, thumbnail_url=""):
                procesadas.append(path)
                if path == "rompe.mp3":
                    raise RuntimeError("ffmpeg explotó")

        errores = []
        listo = threading.Event()

        with patch("quality.post_processor.PostProcessor", PostProcessorQueFalla):
            self.cola.enqueue("rompe.mp3", {}, {}, on_error=lambda p, e: errores.append(p))
            self.cola.enqueue("ok.mp3", {}, {}, on_complete=lambda p: listo.set())
            assert listo.wait(timeout=10), "la tarea siguiente debe procesarse igual"

        assert errores == ["rompe.mp3"], "el fallo debe reportarse por on_error"

    def test_un_on_complete_roto_no_propaga(self):
        class PostProcessorOk:
            def __init__(self, config):
                pass

            def process(self, path, metadata, thumbnail_url=""):
                pass

        def revienta(path):
            raise RuntimeError("boom")

        with patch("quality.post_processor.PostProcessor", PostProcessorOk):
            self.cola.enqueue("x.mp3", {}, {}, on_complete=revienta)
            self.cola.shutdown()  # espera a que termine; no debe levantar


if __name__ == "__main__":
    unittest.main()
