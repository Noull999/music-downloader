"""
Tests de la versión de ID3 con la que se guardan los tags.

El bug: mutagen guarda ID3v2.4 por defecto, y ni el Reproductor multimedia
ni el Explorador de Windows leen la carátula de un v2.4 — la canción se ve
sin tapa aunque el APIC esté perfecto. Medido en la biblioteca real: 993
archivos tenían carátula correcta y no se veía en ninguno de los dos.
v2.3 lo entienden ambos, además de Serato y Rekordbox.
"""
import os
import subprocess
import tempfile
import unittest

from mutagen.aiff import AIFF
from mutagen.id3 import ID3
from mutagen.mp3 import MP3
from mutagen.wave import WAVE

from quality.post_processor import PostProcessor
from utils.dependencies import FFmpegValidator
from utils.subprocess_utils import NO_WINDOW

# JPEG mínimo pero con firma real, para que el embebido no lo descarte.
_JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 600


def _generar(ruta: str) -> bool:
    """Crea un archivo de audio real de 1 segundo con ffmpeg."""
    try:
        ffmpeg = FFmpegValidator.find_ffmpeg_executable()
    except Exception:
        return False
    subprocess.run(
        [ffmpeg, "-f", "lavfi", "-i", "sine=f=440:d=1", "-y", ruta],
        capture_output=True, creationflags=NO_WINDOW,
    )
    return os.path.exists(ruta)


class TestVersionID3(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.pp = PostProcessor({"embed_metadata": True, "embed_artwork": True})

    def _procesar(self, ext: str):
        ruta = os.path.join(self.dir, "tema" + ext)
        if not _generar(ruta):
            self.skipTest("ffmpeg no disponible")
        self.pp._embed_tags(
            ruta,
            {"title": "Tema", "artist": "Artista", "album": "", "year": ""},
            "http://ejemplo/cover.jpg",
        )
        return ruta

    def _tags(self, ruta: str, ext: str):
        if ext == ".mp3":
            return MP3(ruta, ID3=ID3).tags
        return (WAVE(ruta) if ext == ".wav" else AIFF(ruta)).tags

    def test_guarda_en_v23_en_los_tres_formatos(self):
        # Sin red: que la carátula no se pueda bajar no debe cambiar la
        # versión con la que se escriben los tags.
        for ext in (".mp3", ".wav", ".aiff"):
            with self.subTest(ext=ext):
                ruta = self._procesar(ext)
                tags = self._tags(ruta, ext)
                assert tags is not None, f"{ext} quedó sin tags"
                assert tags.version[:2] == (2, 3), (
                    f"{ext} se guardó como ID3v{'.'.join(map(str, tags.version))}; "
                    "el Reproductor de Windows no lee la carátula de v2.4"
                )

    def test_los_tags_sobreviven_a_la_conversion(self):
        ruta = self._procesar(".mp3")
        tags = self._tags(ruta, ".mp3")
        assert str(tags.get("TIT2")) == "Tema"
        assert str(tags.get("TPE1")) == "Artista"


if __name__ == "__main__":
    unittest.main()
