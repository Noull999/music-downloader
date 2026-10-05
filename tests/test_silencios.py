"""
Tests de "Eliminar silencios" (quality/post_processor.py).

El bug: se usaba silenceremove con stop_periods=1, que toma el PRIMER
silencio de 0.5 s como el final del archivo y descarta todo lo que sigue.
En musica de baile, con cortes y breaks, dejo canciones de 0.7 s en lugar
de 4 minutos. Reproduciendo el filtro sobre 14 temas sanos de la biblioteca,
5 salieron truncados.
"""
import os
import subprocess
import tempfile
import unittest

from mutagen.mp3 import MP3

from quality.post_processor import PostProcessor
from utils.dependencies import FFmpegValidator
from utils.subprocess_utils import NO_WINDOW


def _ffmpeg():
    try:
        return FFmpegValidator.find_ffmpeg_executable()
    except Exception:
        return None


def _generar(ruta: str, graph: str, duracion: float) -> None:
    subprocess.run(
        [_ffmpeg(), "-f", "lavfi", "-i", graph, "-t", str(duracion),
         "-c:a", "libmp3lame", "-b:a", "128k", "-y", ruta],
        capture_output=True, creationflags=NO_WINDOW, check=True,
    )


def _largo(ruta: str) -> float:
    return MP3(ruta).info.length


@unittest.skipUnless(_ffmpeg(), "ffmpeg no disponible")
class TestEliminarSilencios(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()

    def _tema_con_silencio_en_el_medio(self) -> str:
        # 10 s de tono, 1 s de silencio total (un break), 10 s de tono.
        ruta = os.path.join(self.dir, "tema.mp3")
        graph = ("aevalsrc='if(between(t,10,11),0,0.5*sin(2*PI*440*t))':s=44100")
        _generar(ruta, graph, 21)
        return ruta

    def test_un_silencio_en_el_medio_no_corta_el_tema(self):
        ruta = self._tema_con_silencio_en_el_medio()
        antes = _largo(ruta)
        PostProcessor({"remove_silence": True})._apply_ffmpeg_filters(ruta)
        despues = _largo(ruta)
        assert despues > antes - 2, (
            f"el tema paso de {antes:.1f}s a {despues:.1f}s: el filtro lo corto "
            "en el primer silencio"
        )

    def test_recorta_el_silencio_del_final(self):
        # 10 s de tono + 6 s de silencio: el final de silencio sobra.
        ruta = os.path.join(self.dir, "final.mp3")
        _generar(ruta, "aevalsrc='if(lt(t,10),0.5*sin(2*PI*440*t),0)':s=44100", 16)
        PostProcessor({"remove_silence": True})._apply_ffmpeg_filters(ruta)
        assert _largo(ruta) < 12, "deberia haber quitado casi todo el silencio final"

    def test_recorta_el_silencio_del_inicio(self):
        ruta = os.path.join(self.dir, "inicio.mp3")
        _generar(ruta, "aevalsrc='if(gt(t,6),0.5*sin(2*PI*440*t),0)':s=44100", 16)
        PostProcessor({"remove_silence": True})._apply_ffmpeg_filters(ruta)
        assert _largo(ruta) < 12, "deberia haber quitado casi todo el silencio inicial"

    def test_si_el_resultado_queda_mucho_mas_corto_se_conserva_el_original(self):
        # Red de seguridad independiente del filtro: si ffmpeg devuelve algo
        # mucho mas corto, el original no se pisa.
        ruta = self._tema_con_silencio_en_el_medio()
        original = open(ruta, "rb").read()
        pp = PostProcessor({"remove_silence": True})
        with unittest.mock.patch.object(PostProcessor, "_duracion",
                                        side_effect=[200.0, 0.7]):
            pp._apply_ffmpeg_filters(ruta)
        assert open(ruta, "rb").read() == original, "no debe pisar el original"
        assert not os.path.exists(ruta + ".pp_temp.mp3"), "no debe dejar el temporal"


import unittest.mock  # noqa: E402

if __name__ == "__main__":
    unittest.main()
