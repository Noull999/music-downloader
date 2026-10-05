"""
Tests de las listas de SoundCloud en la ventana "elegir temas"
(sync/soundcloud_lists.py y su conexion en WebViewAPI).

Equivalente de lo que ya hacia YouTube: parecidos a un tema, una lista (set) y
los temas de un artista. La ventana muestra siempre UNA plataforma.
"""
import threading
import unittest
from unittest.mock import MagicMock, patch

from handlers.base_handler import TrackMetadata
from sync import soundcloud_lists as L
from sync.soundcloud_api import SoundCloudAPIClient
from webview_app.api import WebViewAPI


def crudo(i, genero="Techno", completo=True):
    if not completo:
        return {"id": i}      # asi manda la API a los temas de una lista que no son los primeros
    return {"id": i, "title": f"Tema {i}", "permalink_url": f"https://soundcloud.com/a/t{i}",
            "user": {"username": "Artista"}, "duration": 200000 + i * 1000,
            "genre": genero, "tag_list": '"hard techno"', "artwork_url": "http://img"}


class TestLinksDeLista(unittest.TestCase):
    def test_perfil_tracks_y_set_son_listas(self):
        for url in ("https://soundcloud.com/luciid", "https://soundcloud.com/luciid/tracks",
                    "https://soundcloud.com/luciid/popular-tracks",
                    "https://soundcloud.com/luciid/sets/mi-set", "https://www.soundcloud.com/luciid"):
            assert L.es_url_de_lista(url), url

    def test_un_tema_suelto_no_es_lista(self):
        assert not L.es_url_de_lista("https://soundcloud.com/luciid/cenith-x-feel")

    def test_las_paginas_del_sitio_no_son_perfiles(self):
        for url in ("https://soundcloud.com/discover", "https://soundcloud.com/stream",
                    "https://soundcloud.com/you"):
            assert not L.es_url_de_lista(url), url

    def test_otras_plataformas_no(self):
        assert not L.es_url_de_lista("https://youtube.com/playlist?list=PL1")
        assert not L.es_url_de_lista("")

    def test_referencia_de_parecidos(self):
        assert L.es_parecidos("sc-related:123") and not L.es_parecidos("https://soundcloud.com/a")


class TestConversion(unittest.TestCase):
    def test_convierte_un_track_crudo(self):
        m = L.a_metadata(crudo(5))
        assert (m.url, m.title, m.artist, m.duration) == ("https://soundcloud.com/a/t5", "Tema 5", "Artista", 205)
        assert m.platform == "SoundCloud" and m.genre == "Techno" and m.track_id == "5"

    def test_descarta_los_incompletos(self):
        assert L.a_metadata({"id": 9}) is None
        assert L.a_metadata({"id": 9, "title": "x"}) is None   # sin permalink_url


class TestObtener(unittest.TestCase):
    def test_parecidos(self):
        cli = MagicMock()
        cli.get_related.return_value = [crudo(1), crudo(2)]
        metas = L.obtener(cli, "sc-related:777")
        cli.get_related.assert_called_once_with("777", L.LIMITE_PARECIDOS)
        assert [m.title for m in metas] == ["Tema 1", "Tema 2"]

    def test_set_completa_por_lotes_los_temas_que_vienen_solo_con_id(self):
        # La API manda completos solo los primeros temas del set; del resto
        # apenas el id. Sin completarlos, el set de 134 quedaba casi vacio.
        cli = MagicMock()
        cli.resolve.return_value = {"kind": "playlist",
                                    "tracks": [crudo(1)] + [crudo(i, completo=False) for i in range(2, 8)]}
        cli.get_tracks_by_ids.side_effect = lambda ids: [crudo(i) for i in ids]
        metas = L.obtener(cli, "https://soundcloud.com/a/sets/x")
        assert [m.title for m in metas] == [f"Tema {i}" for i in range(1, 8)], "debe respetar el orden"

    def test_set_largo_se_pide_en_varios_lotes(self):
        cli = MagicMock()
        cli.resolve.return_value = {"kind": "playlist",
                                    "tracks": [crudo(i, completo=False) for i in range(1, 121)]}
        cli.get_tracks_by_ids.side_effect = lambda ids: [crudo(i) for i in ids]
        metas = L.obtener(cli, "https://soundcloud.com/a/sets/x")
        assert len(metas) == 120
        assert all(len(c.args[0]) <= 50 for c in cli.get_tracks_by_ids.call_args_list)
        assert cli.get_tracks_by_ids.call_count == 3

    def test_perfil(self):
        cli = MagicMock()
        cli.resolve.return_value = {"kind": "user", "id": 42}
        cli.get_user_tracks.return_value = [crudo(1), crudo(2)]
        assert len(L.obtener(cli, "https://soundcloud.com/luciid")) == 2
        cli.get_user_tracks.assert_called_once_with(42, L.LIMITE_PERFIL)

    def test_un_tema_suelto_no_es_una_lista(self):
        cli = MagicMock()
        cli.resolve.return_value = {"kind": "track"}
        with self.assertRaises(RuntimeError):
            L.obtener(cli, "https://soundcloud.com/a/b")

    def test_un_link_que_no_existe_avisa(self):
        cli = MagicMock()
        cli.resolve.return_value = None
        with self.assertRaises(RuntimeError):
            L.obtener(cli, "https://soundcloud.com/nadie")


class TestPaginacionDelPerfil(unittest.TestCase):
    def test_sigue_las_paginas_hasta_que_se_acaban(self):
        # Un perfil de 79 temas devolvia 29 si no se seguia 'next_href'.
        cli = SoundCloudAPIClient("OAuth 2-xxxxx-xxxxx-xxxxx-xxxxxxxx", "cid")
        paginas = [
            {"collection": [crudo(i) for i in range(29)], "next_href": "https://api/p2"},
            {"collection": [crudo(i) for i in range(29, 32)], "next_href": "https://api/p3"},
            {"collection": [crudo(i) for i in range(32, 40)], "next_href": None},
        ]
        cli._get_json = MagicMock(return_value=paginas[0])
        cli._get_json_url = MagicMock(side_effect=[paginas[1], paginas[2]])
        assert len(cli.get_user_tracks(1, limit=200)) == 40

    def test_respeta_el_limite(self):
        cli = SoundCloudAPIClient("OAuth 2-xxxxx-xxxxx-xxxxx-xxxxxxxx", "cid")
        cli._get_json = MagicMock(return_value={"collection": [crudo(i) for i in range(29)], "next_href": "https://api/p2"})
        cli._get_json_url = MagicMock(return_value={"collection": [crudo(i) for i in range(29, 58)], "next_href": "https://api/p3"})
        assert len(cli.get_user_tracks(1, limit=40)) == 40

    def test_una_pagina_que_falla_corta_sin_romper(self):
        cli = SoundCloudAPIClient("OAuth 2-xxxxx-xxxxx-xxxxx-xxxxxxxx", "cid")
        cli._get_json = MagicMock(return_value={"collection": [crudo(1)], "next_href": "https://api/p2"})
        cli._get_json_url = MagicMock(return_value=None)
        assert len(cli.get_user_tracks(1)) == 1


def _api(cliente=None):
    api = object.__new__(WebViewAPI)
    api._tracks = {}
    api._lock = threading.Lock()
    api._window = None
    api._playlist_cache = {}
    api._enviadas = set()
    api._auto_iniciar = MagicMock()   # el inicio automatico se prueba en test_auto_inicio.py
    api.controller = MagicMock()
    api.controller.is_track_downloaded.return_value = False
    api._push = MagicMock()
    api._sc_client = lambda: cliente
    return api


class TestVentanaSoundCloud(unittest.TestCase):
    def test_parecidos_muestran_su_genero_y_la_plataforma(self):
        cli = MagicMock()
        cli.get_related.return_value = [crudo(1, "Schranz"), crudo(2, "")]
        r = _api(cli).get_playlist_entries("sc-related:777")
        assert r["ok"] and r["plataforma"] == "SoundCloud" and r["es_radio"] is True
        assert [e["genero"] for e in r["entradas"]][0] == "Schranz"

    def test_sin_cuenta_conectada_avisa(self):
        r = _api(None).get_playlist_entries("sc-related:777")
        assert r["ok"] is False and "Conect" in r["error"]

    def test_un_set_no_es_radio(self):
        cli = MagicMock()
        cli.resolve.return_value = {"kind": "playlist", "tracks": [crudo(1)]}
        r = _api(cli).get_playlist_entries("https://soundcloud.com/a/sets/x")
        assert r["ok"] and r["es_radio"] is False and r["plataforma"] == "SoundCloud"

    def test_no_mezcla_plataformas_en_una_ventana(self):
        # Un link de YouTube nunca debe tocar el cliente de SoundCloud.
        cli = MagicMock()
        api = _api(cli)
        handler = MagicMock()
        handler.get_playlist_tracks.return_value = [TrackMetadata(
            url="https://youtube.com/watch?v=1", title="T", artist="A", duration=100, platform="YouTube")]
        with patch("webview_app.api.detect_handler", return_value=handler):
            r = api.get_playlist_entries("https://www.youtube.com/watch?v=x&list=RDx")
        assert r["plataforma"] == "YouTube"
        cli.get_related.assert_not_called()
        cli.resolve.assert_not_called()

    def test_agregar_lo_elegido_de_soundcloud_conserva_genero_y_tags(self):
        cli = MagicMock()
        cli.get_related.return_value = [crudo(1, "Schranz"), crudo(2), crudo(3)]
        api = _api(cli)
        api._asegurar_generos_en_segundo_plano = MagicMock()
        api.get_playlist_entries("sc-related:777")
        r = api.add_playlist_selection("sc-related:777", ["https://soundcloud.com/a/t1"])
        assert r["agregadas"] == 1
        agregada = api._tracks["https://soundcloud.com/a/t1"]
        assert agregada.genre == "Schranz" and agregada.platform == "SoundCloud"


class TestLinksDeListaEnLaCola(unittest.TestCase):
    def test_una_playlist_de_youtube_abre_la_ventana_en_vez_de_llenar_la_cola(self):
        api = _api()
        api._tracks["https://youtube.com/playlist?list=PL1"] = MagicMock()
        api._fetch_worker("https://youtube.com/playlist?list=PL1")
        eventos = [c.args[0] for c in api._push.call_args_list]
        assert eventos == ["abrir_lista"]
        assert api._tracks == {}, "la fila de carga se descarta"

    def test_un_set_de_soundcloud_tambien(self):
        api = _api()
        api._fetch_worker("https://soundcloud.com/luciid/sets/mi-set")
        assert [c.args[0] for c in api._push.call_args_list] == ["abrir_lista"]

    def test_un_video_de_youtube_con_lista_sigue_siendo_un_video(self):
        api = _api()
        assert api._es_link_de_lista("https://youtube.com/watch?v=x&list=RDx") is False

    def test_un_tema_de_soundcloud_no_es_lista(self):
        assert _api()._es_link_de_lista("https://soundcloud.com/luciid/cenith-x-feel") is False


class TestHandlerMarcaSusParecidos(unittest.TestCase):
    def test_un_tema_de_soundcloud_guarda_la_referencia_de_parecidos(self):
        from handlers.soundcloud_handler import SoundCloudHandler
        h = SoundCloudHandler()
        info = {"id": 12345, "title": "T", "uploader": "A", "duration": 100, "webpage_url": "https://soundcloud.com/a/t"}
        with patch("handlers.soundcloud_handler.yt_dlp.YoutubeDL") as Y:
            Y.return_value.__enter__.return_value.extract_info.return_value = info
            h._full_info = MagicMock(return_value=info)
            t = h.get_metadata("https://soundcloud.com/a/t")[0]
        assert t._radio_url == "sc-related:12345"


if __name__ == "__main__":
    unittest.main()
