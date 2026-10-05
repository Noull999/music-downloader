"""
Tests de lo que muestra "Ultimas descargas" (WebViewAPI.get_recent_activity)
y del orden en que se guardan las descargas.

Dos bugs:
1. Cada descarga de la sync quedaba en DOS tablas (sync_downloads y
   downloads, de ahi lee el panel) y el panel mezcla ambas: aparecia
   repetida. Medido: 430 canciones en las dos.
2. Al terminar una descarga por link, se avisaba a la interfaz ANTES de
   guardarla en el historial. La vista refresca el panel apenas recibe el
   aviso, asi que a veces no encontraba la fila y la descarga no aparecia.
"""
import threading
import types
import unittest
from unittest.mock import MagicMock

from webview_app.api import WebViewAPI


def _api():
    api = object.__new__(WebViewAPI)
    api._tracks = {}
    api._lock = threading.Lock()
    api._window = None
    api.controller = MagicMock()
    api._sync_manager = MagicMock()
    return api


class TestSinDuplicados(unittest.TestCase):
    def test_una_cancion_en_las_dos_tablas_aparece_una_vez(self):
        api = _api()
        api.controller.get_recent_downloads.return_value = [
            {"url": "u1", "title": "A", "artist": "x", "platform": "soundcloud",
             "local_path": "D:/m/a.mp3", "download_date": "2026-10-01 10:00:00"},
        ]
        api._sync_manager.history.get_all_downloads.return_value = [
            {"url": "u1", "title": "A", "artist": "x", "platform": "soundcloud",
             "file_path": "D:/m/a.mp3", "downloaded_at": "2026-10-01 10:00:00"},
        ]
        r = api.get_recent_activity(30)
        assert len(r) == 1, f"aparece {len(r)} veces"
        assert r[0]["source"] == "sync", "si esta en ambas gana la de la sync"

    def test_las_distintas_siguen_apareciendo_todas(self):
        api = _api()
        api.controller.get_recent_downloads.return_value = [
            {"url": "m1", "title": "Manual", "artist": "", "platform": "YouTube",
             "local_path": "D:/m/m.mp3", "download_date": "2026-10-05 12:26:14"},
        ]
        api._sync_manager.history.get_all_downloads.return_value = [
            {"url": "s1", "title": "Sync", "artist": "", "platform": "soundcloud",
             "file_path": "D:/m/s.mp3", "downloaded_at": "2026-10-04 09:00:00"},
        ]
        r = api.get_recent_activity(30)
        assert [x["title"] for x in r] == ["Manual", "Sync"], "orden: la mas nueva primero"

    def test_los_local_siguen_excluidos(self):
        api = _api()
        api.controller.get_recent_downloads.return_value = [
            {"url": "local://D:/x.mp3", "title": "Viejo", "download_date": "2026-01-01"},
        ]
        api._sync_manager.history.get_all_downloads.return_value = []
        assert api.get_recent_activity(30) == []


class TestOrdenAlTerminar(unittest.TestCase):
    def test_en_la_sync_se_guarda_antes_de_avisar_a_la_vista(self):
        api = _api()
        orden = []
        api.controller.record_download.side_effect = lambda info: orden.append("guardar")
        api._push = lambda evento, payload: orden.append(f"avisar:{evento}")
        track = types.SimpleNamespace(url="u", title="T", artist="A", duration_ms=1000,
                                      artwork_url="")
        api._on_sync_track_event("start", track)
        orden.clear()
        api._on_sync_track_event("done", track, "D:/m/t.mp3")
        assert orden.index("guardar") < orden.index("avisar:track_status"), orden


class TestRevelarEnCarpeta(unittest.TestCase):
    def test_un_archivo_que_no_existe_avisa(self):
        r = _api().reveal_in_folder("D:/no/existe.mp3")
        assert r["ok"] is False

    def test_ruta_vacia_avisa(self):
        assert _api().reveal_in_folder("")["ok"] is False


if __name__ == "__main__":
    unittest.main()
