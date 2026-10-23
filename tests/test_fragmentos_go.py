"""
Temas de SoundCloud Go+ ("policy": "SNIP"): SoundCloud solo da 30 s.

Antes la app guardaba ese fragmento como si fuera la cancion (un "Drakk -
Gangstas" de 30 s en vez de 5:05) y despues lo daba por "ya descargado".
"""
import unittest
from unittest.mock import MagicMock

from sync.soundcloud_api import SoundCloudTrack, _duracion_y_fragmento
from sync.sync_manager import SyncManager


class TestLeerLike(unittest.TestCase):
    def test_un_tema_go_usa_la_duracion_completa(self):
        assert _duracion_y_fragmento({"policy": "SNIP", "duration": 30000, "full_duration": 305293}) == (305293, True)

    def test_un_tema_normal_no_cambia(self):
        assert _duracion_y_fragmento({"policy": "ALLOW", "duration": 240000, "full_duration": 240000}) == (240000, False)
        assert _duracion_y_fragmento({"duration": 1000}) == (1000, False)


def _track(fragmento):
    return SoundCloudTrack(id=1, url="https://soundcloud.com/drakk-sc/gangstas", title="Gangstas",
                           artist="Drakk", duration_ms=305293, artwork_url=None, genre="", created_at="",
                           fragmento=fragmento)


class TestDescargar(unittest.TestCase):
    def _sm(self, youtube=True):
        sm = object.__new__(SyncManager)
        sm.quality_preset = "mp3_320"
        sm._stop_event = MagicMock()
        sm._stop_event.is_set.return_value = False
        sm.downloader = MagicMock()
        sm.downloader.download.return_value = "fragmento.mp3"
        sm.youtube_fallback_enabled = youtube
        sm._respaldo_youtube = MagicMock(return_value="completo.mp3")
        return sm

    def test_no_baja_el_fragmento_y_va_a_youtube(self):
        sm = self._sm()
        assert sm._descargar(_track(True), "salida") == ("completo.mp3", "youtube")
        sm.downloader.download.assert_not_called()

    def test_sin_version_en_youtube_queda_como_fallido_con_motivo_claro(self):
        sm = self._sm()
        sm._respaldo_youtube.return_value = None
        with self.assertRaises(RuntimeError) as ctx:
            sm._descargar(_track(True), "salida")
        assert "30 s" in str(ctx.exception)
        sm.downloader.download.assert_not_called()

    def test_con_youtube_desactivado_tampoco_baja_el_fragmento(self):
        sm = self._sm(youtube=False)
        with self.assertRaises(RuntimeError):
            sm._descargar(_track(True), "salida")
        sm.downloader.download.assert_not_called()

    def test_un_tema_normal_sigue_bajando_de_soundcloud(self):
        sm = self._sm()
        assert sm._descargar(_track(False), "salida") == ("fragmento.mp3", "soundcloud")


if __name__ == "__main__":
    unittest.main()
