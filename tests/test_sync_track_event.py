"""
Tests de WebViewAPI._on_sync_track_event: el puente entre la sync y la UI.

Cubre el bug encontrado en la auditoría end-to-end: cuando la sync termina
una canción, solo actualizaba la cola en memoria — nunca quedaba en la
tabla que lee "Últimas descargas". Medido en la base real: 1367 de 1778
descargas de sync (77%) no estaban registradas ahí.
"""
import threading
import types
import unittest
from unittest.mock import MagicMock

from webview_app.api import WebViewAPI


def _api_sin_init() -> WebViewAPI:
    """
    Instancia mínima de WebViewAPI sin pasar por __init__ (que arranca un
    DownloadManager real y abre el historial/config reales): solo los
    atributos que _on_sync_track_event necesita.
    """
    api = object.__new__(WebViewAPI)
    api._tracks = {}
    api._lock = threading.Lock()
    api._window = None
    api.controller = MagicMock()
    return api


def _track_de_sync(url="http://sc/1", title="Tema", artist="Artista", duration_ms=185000):
    return types.SimpleNamespace(
        url=url, title=title, artist=artist, duration_ms=duration_ms, artwork_url="",
    )


class TestOnSyncTrackEvent(unittest.TestCase):
    def test_done_registra_en_el_historial(self):
        api = _api_sin_init()
        track = _track_de_sync()

        api._on_sync_track_event("start", track)
        api._on_sync_track_event("done", track, "D:/Musik/Techno/Tema.mp3")

        api.controller.record_download.assert_called_once()
        registrado = api.controller.record_download.call_args[0][0]
        assert registrado.url == track.url
        assert registrado.local_path == "D:/Musik/Techno/Tema.mp3"
        assert registrado.duration == 185  # duration_ms -> segundos

    def test_duplicado_ya_en_biblioteca_no_cuenta_como_descarga(self):
        # La sync encontró el tema por huella de audio y NO lo descargó: el
        # archivo ya estaba (quizás de hace meses). Debe verse terminado en
        # la cola, pero no entrar a "Últimas descargas" con fecha de hoy.
        api = _api_sin_init()
        track = _track_de_sync()

        api._on_sync_track_event("already_had", track, "D:/Musik/Techno/Viejo.mp3")

        api.controller.record_download.assert_not_called()
        info = api._tracks[track.url]
        assert info.status == "done", "en la cola se ve igual que una terminada"
        assert info.local_path == "D:/Musik/Techno/Viejo.mp3"

    def test_error_no_registra_nada(self):
        api = _api_sin_init()
        api._on_sync_track_event("start", _track_de_sync())
        api._on_sync_track_event("error", _track_de_sync(), "algo falló")
        api.controller.record_download.assert_not_called()

    def test_done_sin_ruta_no_registra(self):
        # "done" sin detail (ruta vacía) no debería insertar una fila fantasma.
        api = _api_sin_init()
        api._on_sync_track_event("done", _track_de_sync(), "")
        api.controller.record_download.assert_not_called()

    def test_fallo_al_registrar_no_rompe_el_evento(self):
        api = _api_sin_init()
        api.controller.record_download.side_effect = RuntimeError("boom")
        # No debe propagar: un error de historial no puede tirar abajo el
        # callback de la sync (que sigue bajando el resto de la cola).
        api._on_sync_track_event("done", _track_de_sync(), "D:/Musik/x.mp3")


if __name__ == "__main__":
    unittest.main()
