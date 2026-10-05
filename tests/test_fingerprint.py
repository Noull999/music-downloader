"""
Tests de la huella de audio (analysis/fingerprint.py).

Los umbrales salen de mediciones sobre una biblioteca real: el mismo tema
con desfase daba 0.96-0.99, y 14 pares de remixes distintos con títulos
casi idénticos se quedaron todos por debajo de 0.71. De ahí MATCH_THRESHOLD.
"""
import json
import tempfile
import unittest
from pathlib import Path

import numpy as np

from analysis.fingerprint import (
    MATCH_THRESHOLD,
    LibraryFingerprintIndex,
    similarity_aligned,
)


def _huella(semilla: int, largo: int = 200) -> list[int]:
    rng = np.random.default_rng(semilla)
    return rng.integers(0, 2**32, size=largo, dtype=np.uint64).astype(np.uint32).tolist()


class TestSimilitud(unittest.TestCase):
    def test_identica_da_uno(self):
        fp = _huella(1)
        assert similarity_aligned(fp, fp) == 1.0

    def test_distintas_dan_bajo(self):
        # Dos huellas al azar comparten ~la mitad de los bits por pura
        # probabilidad, así que el piso ronda 0.5, no 0.
        s = similarity_aligned(_huella(1), _huella(2))
        assert s < MATCH_THRESHOLD, f"dos temas distintos no deben matchear (dio {s})"

    def test_tolera_desfase(self):
        # El preview puede arrancar en otro punto que el archivo local.
        fp = _huella(3, largo=300)
        assert similarity_aligned(fp, fp[20:]) > 0.99

    def test_acepta_listas_y_arrays(self):
        fp = _huella(4)
        como_lista = similarity_aligned(fp, fp)
        como_array = similarity_aligned(np.asarray(fp, dtype=np.uint32),
                                        np.asarray(fp, dtype=np.uint32))
        assert como_lista == como_array == 1.0

    def test_solapamiento_minimo_no_rompe(self):
        # Con muy pocas posiciones en común no se puede concluir nada.
        assert similarity_aligned(_huella(5, largo=5), _huella(6, largo=5)) == 0.0


class TestRendimiento(unittest.TestCase):
    """
    La versión en Python puro tardaba ~19 s por canción contra 1400 temas,
    y era el grueso de la lentitud de cada sync. Este test falla si alguien
    vuelve a una implementación no vectorizada.
    """

    def test_busqueda_masiva_es_rapida(self):
        import time

        idx = LibraryFingerprintIndex(cache_path=Path(tempfile.mkdtemp()) / "x.json")
        idx._entries = {f"/f/{i}.mp3": {"fp": _huella(i, largo=460)} for i in range(300)}

        t0 = time.time()
        idx.find_best_match(_huella(999, largo=460))
        dt = time.time() - t0

        # En puro Python esto tardaba ~4 s; vectorizado no llega a 1.
        assert dt < 2.0, f"la comparación tardó {dt:.1f}s para 300 entradas"


class TestRemapeoDeRutas(unittest.TestCase):
    """
    Al mover archivos (ordenar por género) el contenido no cambia, así que
    las huellas se conservan y solo hay que actualizar las rutas. Antes se
    borraba el caché entero y la sync siguiente reanalizaba todo.
    """

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.cache = self.tmp / "fp.json"

    def test_remapea_y_conserva_la_huella(self):
        original = {"mtime": 1.0, "size": 10, "fp": [1, 2, 3]}
        self.cache.write_text(json.dumps({r"D:\Musik\prueba\a.mp3": original}), encoding="utf-8")

        n = LibraryFingerprintIndex.remap_paths(
            [(r"D:\Musik\prueba\a.mp3", r"D:\Musik\Schranz\a.mp3")], self.cache
        )

        assert n == 1
        datos = json.loads(self.cache.read_text(encoding="utf-8"))
        assert r"D:\Musik\prueba\a.mp3" not in datos, "la ruta vieja debe desaparecer"
        assert datos[r"D:\Musik\Schranz\a.mp3"] == original, "la huella debe conservarse"

    def test_rutas_que_no_estaban_no_rompen(self):
        self.cache.write_text(json.dumps({}), encoding="utf-8")
        assert LibraryFingerprintIndex.remap_paths([("/no/existe.mp3", "/otro.mp3")], self.cache) == 0

    def test_sin_cache_no_rompe(self):
        assert LibraryFingerprintIndex.remap_paths([("/a", "/b")], self.tmp / "no_existe.json") == 0

    def test_cache_corrupta_no_rompe(self):
        self.cache.write_text("{ esto no es json", encoding="utf-8")
        assert LibraryFingerprintIndex.remap_paths([("/a", "/b")], self.cache) == 0


class TestUmbral(unittest.TestCase):
    def test_solo_devuelve_match_sobre_el_umbral(self):
        idx = LibraryFingerprintIndex(cache_path=Path(tempfile.mkdtemp()) / "x.json")
        idx._entries = {"/f/otro.mp3": {"fp": _huella(20)}}
        # Una huella sin relación no debe devolverse como coincidencia.
        assert idx.find_best_match(_huella(21)) is None

    def test_devuelve_el_match_exacto(self):
        fp = _huella(30)
        idx = LibraryFingerprintIndex(cache_path=Path(tempfile.mkdtemp()) / "x.json")
        idx._entries = {"/f/igual.mp3": {"fp": fp}, "/f/otro.mp3": {"fp": _huella(31)}}
        resultado = idx.find_best_match(fp)
        assert resultado is not None
        ruta, score = resultado
        assert ruta == "/f/igual.mp3" and score == 1.0


if __name__ == "__main__":
    unittest.main()
