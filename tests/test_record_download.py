"""
Tests de UIController.record_download: registra una descarga en la tabla
`downloads` (de ahí lee "Últimas descargas" y el contador de "Descargas").

Hasta ahora solo se llamaba con un TrackInfo (que siempre tiene .album y
.platform, con default ""). El track que llega de la sync es un
SoundCloudTrack, que NO tiene esos atributos: llamar record_download con
uno tiraba AttributeError, silenciado por el except de adentro — así que
ninguna descarga de sync quedaba nunca en "Últimas descargas". Medido en
la base real: 1367 de 1778 descargas de sync no estaban registradas.
"""
import tempfile
import types
import unittest
from pathlib import Path

from db.history_manager import HistoryManager
from gui.ui_controller import UIController
from models import TrackInfo


class TestRecordDownload(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        # UIController.record_download solo usa self.history: un objeto con
        # ese atributo alcanza, sin pasar por __init__ (que toca ConfigManager
        # y DownloadManager, y sin db_path pisaría el historial real).
        self.controller = object.__new__(UIController)
        self.controller.history = HistoryManager(db_path=str(self.tmp / "history.db"))

    def test_trackinfo_normal_se_registra(self):
        t = TrackInfo(url="http://x/1", title="Tema", artist="Artista")
        UIController.record_download(self.controller, t)
        rows = self.controller.history.get_recent_downloads(10)
        assert len(rows) == 1
        assert rows[0]["title"] == "Tema"

    def test_objeto_sin_album_ni_platform_no_rompe(self):
        # Como SoundCloudTrack: sin .album ni .platform.
        track_de_sync = types.SimpleNamespace(
            url="http://x/2", title="Tema de sync", artist="Artista",
        )
        UIController.record_download(self.controller, track_de_sync)
        rows = self.controller.history.get_recent_downloads(10)
        assert len(rows) == 1, "la descarga de sync debe quedar registrada igual"
        assert rows[0]["title"] == "Tema de sync"

    def test_registra_el_tamano_del_archivo_real(self):
        archivo = self.tmp / "cancion.mp3"
        archivo.write_bytes(b"x" * 12345)
        t = TrackInfo(url="http://x/3", title="Con archivo", artist="A", local_path=str(archivo))
        UIController.record_download(self.controller, t)
        rows = self.controller.history.get_recent_downloads(10)
        assert rows[0]["file_size"] == 12345

    def test_sin_archivo_en_disco_tamano_es_cero_no_rompe(self):
        t = TrackInfo(url="http://x/4", title="Sin archivo", artist="A", local_path="no/existe.mp3")
        UIController.record_download(self.controller, t)
        rows = self.controller.history.get_recent_downloads(10)
        assert rows[0]["file_size"] == 0


if __name__ == "__main__":
    unittest.main()
