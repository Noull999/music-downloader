"""
Tests de los falsos duplicados: canciones que la app daba por descargadas sin
estarlo.

Encontrado al contrastar el historial con el disco: de 458 likes, 38 estaban
registrados como "ya descargados" apuntando a un archivo de OTRO tema. Causas:

1. clean_for_match borra todo lo que va entre parentesis, y ahi esta el nombre
   del remixer: "Faithless - Insomnia (SX2 Remix)" e "Insomnia - Faithless
   (Restricted & NIK)" quedaban identicos.
2. La huella de audio mira solo 30 s: un remix o bootleg que comparte la voz
   con otro tema suena igual ahi (dos temas de O.B.I. quedaron enlazados a
   "Loreen - Tattoo"), pero casi nunca dura lo mismo.
"""
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from sync import match_utils
from sync.duplicate_checker import DuplicateChecker


class TestTokensDeRemixer(unittest.TestCase):
    def test_saca_el_nombre_del_remixer(self):
        assert match_utils.tokens_de_remixer("Faithless - Insomnia (SX2 Remix) [FREE DL]") == {"sx2"}

    def test_ignora_las_palabras_de_promo(self):
        assert match_utils.tokens_de_remixer("Tema (Free Download)") == frozenset()
        assert match_utils.tokens_de_remixer("Tema (Temporary Free Download)") == frozenset()
        assert match_utils.tokens_de_remixer("Tema (Extended Mix)") == frozenset()

    def test_no_mira_los_corchetes(self):
        # Ahi van sellos y codigos, no remixers.
        assert match_utils.tokens_de_remixer("Tema [TFT046] [Proclam Rec.]") == frozenset()

    def test_varios_nombres(self):
        assert match_utils.tokens_de_remixer("Tema (Holy Priest & elMefti Hard Techno Remix)") == {
            "holy", "priest", "elmefti"}

    def test_sin_parentesis(self):
        assert match_utils.tokens_de_remixer("Tema sin nada") == frozenset()
        assert match_utils.tokens_de_remixer("") == frozenset()

    def test_las_tildes_y_signos_no_estorban(self):
        assert match_utils.tokens_de_remixer("Tema (Ñandú Remix)") == {"nandu"}


class TestRespetaRemixer(unittest.TestCase):
    def test_otro_remixer_no_vale(self):
        assert not match_utils.respeta_remixer(
            "Faithless - Insomnia (SX2 Remix)", "Insonmia - Faithless (Restricted & NIK)")

    def test_el_mismo_remixer_vale(self):
        assert match_utils.respeta_remixer(
            "Faithless - Insomnia (SX2 Remix)", "Faithless - Insomnia SX2 Remix")

    def test_sin_remixer_en_el_titulo_todo_vale(self):
        assert match_utils.respeta_remixer("Tema (Free Download)", "cualquier nombre")

    def test_la_version_sin_remixer_no_reemplaza_a_la_remezcla(self):
        assert not match_utils.respeta_remixer("Tema (Juan Remix)", "Tema")


class TestFindBestMatchConTitulo(unittest.TestCase):
    def _indice(self, *nombres):
        return match_utils.index_audio_files([self._carpeta(nombres)])

    def _carpeta(self, nombres):
        d = tempfile.mkdtemp()
        for n in nombres:
            Path(d, n).write_bytes(b"x")
        return d

    def test_ya_no_da_por_igual_a_otro_remix(self):
        indice = self._indice("Insomnia - Faithless (Restricted & NIK).mp3")
        titulo = "Faithless - Insomnia (SX2 Remix)"
        cands = match_utils.like_candidates("SX2", titulo)
        # Sin `titulo` la comparacion por nombre lo daba por duplicado.
        assert match_utils.find_best_match(cands, indice, 80)[0] is not None
        assert match_utils.find_best_match(cands, indice, 80, titulo=titulo)[0] is None

    def test_sigue_reconociendo_el_duplicado_real(self):
        indice = self._indice("Faithless - Insomnia (SX2 Remix).mp3")
        titulo = "Faithless - Insomnia (SX2 Remix)"
        cands = match_utils.like_candidates("SX2", titulo)
        assert match_utils.find_best_match(cands, indice, 80, titulo=titulo)[0] is not None


def _wav(ruta: str, segundos: int):
    from utils.dependencies import FFmpegValidator
    from utils.subprocess_utils import NO_WINDOW
    subprocess.run([FFmpegValidator.find_ffmpeg_executable(), "-f", "lavfi", "-i", "sine=f=440",
                    "-t", str(segundos), "-y", ruta], capture_output=True, creationflags=NO_WINDOW, check=True)


class TestDuracionCompatible(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.ruta = os.path.join(self.dir, "tema.wav")
        try:
            _wav(self.ruta, 20)
        except Exception:
            self.skipTest("ffmpeg no disponible")

    def test_misma_duracion(self):
        assert match_utils.duracion_compatible(self.ruta, 20)
        assert match_utils.duracion_compatible(self.ruta, 25)

    def test_otra_duracion(self):
        assert not match_utils.duracion_compatible(self.ruta, 60)

    def test_sin_duracion_de_referencia_no_decide(self):
        assert match_utils.duracion_compatible(self.ruta, 0)

    def test_un_archivo_ilegible_no_decide(self):
        assert match_utils.duracion_compatible(os.path.join(self.dir, "no_existe.wav"), 100)


class TestDuplicateChecker(unittest.TestCase):
    def _checker(self, *nombres, duraciones=None):
        d = tempfile.mkdtemp()
        for n in nombres:
            Path(d, n).write_bytes(b"x")
        hist = MagicMock()
        hist.is_downloaded.return_value = False
        return DuplicateChecker(hist, library_folders=[d]), d

    def test_otro_remixer_no_es_duplicado(self):
        c, d = self._checker("Insomnia - Faithless (Restricted & NIK).mp3")
        es_dup, _ = c.is_duplicate("u", "Faithless - Insomnia (SX2 Remix)", "SX2", d, 359)
        assert es_dup is False

    def test_el_mismo_tema_si_es_duplicado(self):
        c, d = self._checker("Faithless - Insomnia (SX2 Remix).mp3")
        with patch("sync.match_utils.duracion_compatible", return_value=True):
            es_dup, _ = c.is_duplicate("u", "Faithless - Insomnia (SX2 Remix)", "SX2", d, 359)
        assert es_dup is True

    def test_mismo_nombre_pero_otra_duracion_no_es_duplicado(self):
        c, d = self._checker("LUWCK - FEEL ALIVE.mp3")
        with patch("sync.match_utils.duracion_compatible", return_value=False):
            es_dup, _ = c.is_duplicate("u", "FEEL ALIVE", "LUWCK", d, 224)
        assert es_dup is False

    def test_get_new_tracks_pasa_la_duracion(self):
        c, d = self._checker("LUWCK - FEEL ALIVE.mp3")
        track = MagicMock(url="u", title="FEEL ALIVE", artist="LUWCK", duration_ms=224000)
        visto = []
        with patch("sync.match_utils.duracion_compatible", side_effect=lambda p, dur, *a: visto.append(dur) or True):
            c.get_new_tracks([track], d)
        assert visto == [224.0]


if __name__ == "__main__":
    unittest.main()


class TestHuellaConDuracion(unittest.TestCase):
    """_fingerprint_precheck: la huella mira 30 s, asi que un remix con la misma voz coincide."""

    def _sm(self, encontrado, duracion_compatible):
        from sync.sync_manager import SyncManager
        sm = object.__new__(SyncManager)
        indice = MagicMock()
        indice.__len__ = lambda self: 5
        indice.find_best_match.return_value = encontrado
        sm._ensure_fingerprint_index = lambda: indice
        sm._progress_callback = None
        sm.oauth_token = ""
        return sm, duracion_compatible

    def _correr(self, encontrado, compatible):
        sm, _ = self._sm(encontrado, compatible)
        track = MagicMock(url="u", title="Sunglasses", duration_ms=336000)
        with patch("sync.sync_manager.audio_fingerprint.download_preview", return_value="p.mp3"), \
             patch("sync.sync_manager.audio_fingerprint.fingerprint_file", return_value=[1, 2, 3]), \
             patch("sync.sync_manager.match_utils.duracion_compatible", return_value=compatible):
            return sm._fingerprint_precheck(track)

    def test_misma_huella_y_misma_duracion_es_duplicado(self):
        assert self._correr(("D:/Musik/x.mp3", 0.95), True) == ("D:/Musik/x.mp3", 0.95)

    def test_misma_huella_pero_otra_duracion_se_descarga(self):
        # O.B.I. - Sunglasses quedo enlazado a "Loreen - Tattoo": comparten la voz.
        assert self._correr(("D:/Musik/Loreen - Tattoo.mp3", 0.95), False) is None

    def test_sin_coincidencia_sigue_siendo_none(self):
        assert self._correr(None, True) is None
