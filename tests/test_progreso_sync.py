"""
Tests del aviso de progreso durante el análisis de huellas
(analysis/fingerprint.py: LibraryFingerprintIndex.build).

Antes esta parte no llamaba a ningún callback: podía tardar minutos sin
que la interfaz tuviera forma de saber que seguía trabajando, y se veía
como si la app estuviera colgada.
"""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from analysis.fingerprint import LibraryFingerprintIndex


class TestAvisoDeProgreso(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        for i in range(3):
            (self.tmp / f"t{i}.mp3").write_bytes(b"\x00")

    def test_avisa_al_calcular_archivos_nuevos(self):
        avisos = []
        with patch("analysis.fingerprint.fingerprint_file", return_value=[1, 2, 3]):
            idx = LibraryFingerprintIndex(cache_path=self.tmp / "cache.json")
            idx.build([str(self.tmp)], on_progress=lambda h, t: avisos.append((h, t)))

        assert avisos, "debería haber avisado al menos una vez"
        # El último aviso siempre se emite, para que la barra llegue al 100%.
        assert avisos[-1][0] == avisos[-1][1] == 3

    def test_no_avisa_si_todo_esta_en_cache(self):
        with patch("analysis.fingerprint.fingerprint_file", return_value=[1, 2, 3]):
            idx = LibraryFingerprintIndex(cache_path=self.tmp / "cache.json")
            idx.build([str(self.tmp)])  # primera vez: llena el caché

            avisos = []
            idx2 = LibraryFingerprintIndex(cache_path=self.tmp / "cache.json")
            idx2.build([str(self.tmp)], on_progress=lambda h, t: avisos.append((h, t)))

        assert avisos == [], "con todo cacheado no hay nada que avisar"

    def test_un_callback_que_rompe_no_frena_el_indexado(self):
        def avisar_roto(hecho, total):
            raise RuntimeError("boom")

        with patch("analysis.fingerprint.fingerprint_file", return_value=[1, 2, 3]):
            idx = LibraryFingerprintIndex(cache_path=self.tmp / "cache.json")
            idx.build([str(self.tmp)], on_progress=avisar_roto)  # no debe propagar

        assert len(idx) == 3

    def test_sin_callback_no_rompe(self):
        with patch("analysis.fingerprint.fingerprint_file", return_value=[1, 2, 3]):
            idx = LibraryFingerprintIndex(cache_path=self.tmp / "cache.json")
            idx.build([str(self.tmp)])
        assert len(idx) == 3


if __name__ == "__main__":
    unittest.main()
