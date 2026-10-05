"""
Tests de la seleccion de temas de una lista de YouTube (album / radio de
temas parecidos) en WebViewAPI.

Antes, pegar el link de un video con "list=" bajaba solo ese video sin
preguntar, y una playlist pura metia TODOS sus temas a la cola. La lista
de prueba (una radio de YouTube Music) tenia 337 temas: la idea es poder
elegir, por ejemplo, 10 de 50.
"""
import threading
import unittest
from unittest.mock import MagicMock, patch

from handlers.base_handler import TrackMetadata
from models import STATUS_SKIP, TrackInfo
from webview_app.api import WebViewAPI


def _meta(n: int, titulo=None) -> TrackMetadata:
    return TrackMetadata(
        url=f"https://youtube.com/watch?v=v{n}", title=titulo or f"Tema {n}",
        artist="Artista", duration=200 + n, platform="YouTube",
    )


def _api(metas=None):
    api = object.__new__(WebViewAPI)
    api._tracks = {}
    api._lock = threading.Lock()
    api._window = None
    api._playlist_cache = {}
    api.controller = MagicMock()
    api.controller.is_track_downloaded.return_value = False
    api._push = MagicMock()
    handler = MagicMock()
    handler.get_playlist_tracks.return_value = metas or []
    api._handler = handler
    return api


class TestLeerLista(unittest.TestCase):
    def test_devuelve_los_temas_con_su_estado(self):
        api = _api([_meta(1), _meta(2), _meta(3)])
        api._tracks[_meta(1).url] = TrackInfo(url=_meta(1).url)         # ya en la cola
        api.controller.is_track_downloaded.side_effect = lambda u: u == _meta(2).url
        with patch("webview_app.api.detect_handler", return_value=api._handler):
            r = api.get_playlist_entries("https://youtube.com/watch?v=x&list=RDx")
        assert r["ok"] is True
        estados = {e["title"]: (e["en_cola"], e["ya_descargada"]) for e in r["entradas"]}
        assert estados == {"Tema 1": (True, False), "Tema 2": (False, True), "Tema 3": (False, False)}

    def test_no_agrega_nada_a_la_cola_al_leerla(self):
        api = _api([_meta(1), _meta(2)])
        with patch("webview_app.api.detect_handler", return_value=api._handler):
            api.get_playlist_entries("https://youtube.com/watch?v=x&list=RDx")
        assert api._tracks == {}
        api._push.assert_not_called()

    def test_lista_vacia_avisa(self):
        api = _api([])
        with patch("webview_app.api.detect_handler", return_value=api._handler):
            r = api.get_playlist_entries("https://youtube.com/watch?v=x&list=RDx")
        assert r["ok"] is False

    def test_error_de_red_no_se_propaga(self):
        api = _api()
        api._handler.get_playlist_tracks.side_effect = RuntimeError("sin red")
        with patch("webview_app.api.detect_handler", return_value=api._handler):
            r = api.get_playlist_entries("https://youtube.com/watch?v=x&list=RDx")
        assert r["ok"] is False and "sin red" in r["error"]

    def test_una_plataforma_sin_listas_avisa(self):
        api = _api()
        sin_listas = MagicMock(spec=[])   # no tiene get_playlist_tracks
        with patch("webview_app.api.detect_handler", return_value=sin_listas):
            r = api.get_playlist_entries("https://soundcloud.com/a/b")
        assert r["ok"] is False


class TestAgregarSeleccion(unittest.TestCase):
    URL = "https://youtube.com/watch?v=x&list=RDx"

    def _abierta(self, n=5):
        api = _api([_meta(i) for i in range(n)])
        with patch("webview_app.api.detect_handler", return_value=api._handler):
            api.get_playlist_entries(self.URL)
        return api

    def test_agrega_solo_los_elegidos(self):
        api = self._abierta(5)
        r = api.add_playlist_selection(self.URL, [_meta(1).url, _meta(3).url])
        assert r == {"ok": True, "agregadas": 2}
        assert set(api._tracks) == {_meta(1).url, _meta(3).url}

    def test_avisa_a_la_vista_de_cada_tema_agregado(self):
        api = self._abierta(3)
        api.add_playlist_selection(self.URL, [_meta(0).url, _meta(2).url])
        eventos = [c[0][0] for c in api._push.call_args_list]
        assert eventos == ["track_added", "track_added"]

    def test_no_duplica_lo_que_ya_esta_en_la_cola(self):
        api = self._abierta(3)
        api._tracks[_meta(1).url] = TrackInfo(url=_meta(1).url)
        r = api.add_playlist_selection(self.URL, [_meta(1).url, _meta(2).url])
        assert r["agregadas"] == 1

    def test_una_ya_descargada_entra_marcada_como_salteada(self):
        api = self._abierta(2)
        api.controller.is_track_downloaded.side_effect = lambda u: u == _meta(0).url
        api.add_playlist_selection(self.URL, [_meta(0).url])
        assert api._tracks[_meta(0).url].status == STATUS_SKIP

    def test_ignora_urls_que_no_son_de_la_lista(self):
        # La vista no deberia mandar otras, pero no se confia en eso.
        api = self._abierta(2)
        r = api.add_playlist_selection(self.URL, ["https://evil.example/x", _meta(0).url])
        assert r["agregadas"] == 1
        assert "https://evil.example/x" not in api._tracks

    def test_sin_abrir_la_lista_avisa(self):
        api = _api()
        r = api.add_playlist_selection(self.URL, [_meta(0).url])
        assert r["ok"] is False


class TestVideoConLista(unittest.TestCase):
    def test_trackinfo_guarda_la_lista_a_la_que_pertenece(self):
        m = _meta(1)
        m._playlist_url = "https://youtube.com/watch?v=x&list=RDx"
        assert TrackInfo.from_metadata(m).playlist_url == "https://youtube.com/watch?v=x&list=RDx"

    def test_sin_lista_queda_vacio(self):
        assert TrackInfo.from_metadata(_meta(1)).playlist_url == ""


if __name__ == "__main__":
    unittest.main()


class TestRadioDeParecidos(unittest.TestCase):
    """
    YouTube arma una radio de temas parecidos (list=RD<id>) para CUALQUIER
    video, aunque el link pegado no traiga lista. Es lo que la interfaz vieja
    ofrecia al buscar un tema de un artista.
    """

    def _handler(self, url_pegada: str):
        from handlers.youtube_handler import YouTubeHandler
        h = YouTubeHandler()
        track = TrackMetadata(url=url_pegada, title="Tema", artist="A", duration=200,
                              platform="YouTube", track_id="abc123")
        h._fetch_single = MagicMock(return_value=track)
        return h, track

    def test_un_video_sin_lista_ofrece_la_radio(self):
        h, _ = self._handler("https://www.youtube.com/watch?v=abc123")
        t = h.get_metadata("https://www.youtube.com/watch?v=abc123")[0]
        assert t._radio_url == "https://www.youtube.com/watch?v=abc123&list=RDabc123"
        assert not hasattr(t, "_playlist_url"), (
            "no debe marcarlo como 'parte de una playlist': la GUI vieja "
            "preguntaria eso para todos los videos"
        )

    def test_un_video_con_lista_conserva_la_suya(self):
        url = "https://www.youtube.com/watch?v=abc123&list=OLAK5uy_album"
        h, _ = self._handler(url)
        t = h.get_metadata(url)[0]
        assert t._playlist_url == url
        assert not hasattr(t, "_radio_url")

    def test_trackinfo_usa_la_radio_si_no_hay_lista(self):
        m = _meta(1)
        m._radio_url = "https://www.youtube.com/watch?v=abc&list=RDabc"
        assert TrackInfo.from_metadata(m).playlist_url.endswith("list=RDabc")

    def test_trackinfo_prefiere_la_lista_real_a_la_radio(self):
        m = _meta(1)
        m._playlist_url = "https://www.youtube.com/watch?v=abc&list=OLAK5uy_x"
        m._radio_url = "https://www.youtube.com/watch?v=abc&list=RDabc"
        assert "OLAK5uy_x" in TrackInfo.from_metadata(m).playlist_url

    def test_la_radio_se_pide_con_tope(self):
        from webview_app.api import LIMITE_RADIO
        api = _api([_meta(1)])
        with patch("webview_app.api.detect_handler", return_value=api._handler):
            r = api.get_playlist_entries("https://www.youtube.com/watch?v=abc&list=RDabc")
        api._handler.get_playlist_tracks.assert_called_once_with(
            "https://www.youtube.com/watch?v=abc&list=RDabc", limite=LIMITE_RADIO)
        assert r["es_radio"] is True

    def test_una_lista_normal_se_pide_entera(self):
        api = _api([_meta(1)])
        with patch("webview_app.api.detect_handler", return_value=api._handler):
            r = api.get_playlist_entries("https://www.youtube.com/watch?v=abc&list=OLAK5uy_x")
        api._handler.get_playlist_tracks.assert_called_once_with(
            "https://www.youtube.com/watch?v=abc&list=OLAK5uy_x")
        assert r["es_radio"] is False
