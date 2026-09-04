"""
Tests de utils/disk_usage.py: el tamaño "En disco" que muestra la sidebar.

Antes salía de sumar la columna file_size del historial, que nunca se
llenaba al grabar una descarga (quedaba en 0) y además queda vieja en
cuanto un archivo se mueve/renombra o el historial viene migrado desde
otra carpeta. Ahora se recorre la carpeta real de biblioteca en disco.
"""
import tempfile
import unittest
from pathlib import Path

from utils.disk_usage import audio_bytes_in


class TestAudioBytesIn(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def test_suma_archivos_de_audio_recursivo(self):
        (self.tmp / "House").mkdir()
        (self.tmp / "House" / "a.mp3").write_bytes(b"x" * 100)
        (self.tmp / "House" / "b.flac").write_bytes(b"x" * 50)
        (self.tmp / "c.wav").write_bytes(b"x" * 25)

        assert audio_bytes_in(str(self.tmp)) == 175

    def test_ignora_archivos_no_audio(self):
        (self.tmp / "cover.jpg").write_bytes(b"x" * 1000)
        (self.tmp / "notas.txt").write_bytes(b"x" * 1000)
        (self.tmp / "tema.mp3").write_bytes(b"x" * 10)

        assert audio_bytes_in(str(self.tmp)) == 10

    def test_carpeta_vacia_es_cero(self):
        assert audio_bytes_in(str(self.tmp)) == 0

    def test_carpeta_inexistente_es_cero_no_rompe(self):
        assert audio_bytes_in(str(self.tmp / "no_existe")) == 0

    def test_carpeta_vacia_string_es_cero_no_rompe(self):
        assert audio_bytes_in("") == 0

    def test_extension_en_mayusculas_cuenta(self):
        (self.tmp / "tema.MP3").write_bytes(b"x" * 42)
        assert audio_bytes_in(str(self.tmp)) == 42


if __name__ == "__main__":
    unittest.main()
