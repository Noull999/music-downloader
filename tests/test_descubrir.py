"""
Tests de "Descubrir" y de los botones de parecidos en la sync y en Mis Likes.

Descubrir junta los parecidos de tus ultimos likes y los ordena por CUANTOS de
ellos coinciden en recomendar el mismo tema. Nada se baja solo: solo se listan
para elegir.
"""
import threading
import types
import unittest
from unittest.mock import MagicMock

from sync import soundcloud_lists as L
from webview_app.api import WebViewAPI


def crudo(i):
    return {"id": i, "title": f"Tema {i}", "permalink_url": f"https://soundcloud.com/a/t{i}",
            "user": {"username": "Artista"}, "duration": 200000, "genre": "Techno", "tag_list": ""}


def cli_con(parecidos_por_semilla: dict):
    cli = MagicMock()
    cli.get_related.side_effect = lambda semilla, limite: [crudo(i) for i in parecidos_por_semilla[semilla]]
    return cli


class TestDescubrir(unittest.TestCase):
    def test_ordena_por_cuantas_semillas_lo_recomiendan(self):
        # Los de una sola coincidencia (100, 200, 300) aparecen PRIMERO en las
        # listas de SoundCloud; los mas recomendados (9 y 7) vienen despues. Si
        # solo se respetara el orden de aparicion, saldrian al final.
        cli = cli_con({1: [100, 9], 2: [200, 9], 3: [300, 9, 7], 4: [7]})
        res = L.descubrir(cli, [1, 2, 3, 4], excluir=set())
        assert [(m.title, n) for m, n in res][:2] == [("Tema 9", 3), ("Tema 7", 2)]
        assert [n for _, n in res] == sorted((n for _, n in res), reverse=True)

    def test_no_sugiere_lo_que_ya_tenes(self):
        cli = cli_con({1: [9, 7]})
        res = L.descubrir(cli, [1], excluir={"https://soundcloud.com/a/t9"})
        assert [m.title for m, _ in res] == ["Tema 7"]

    def test_un_tema_repetido_en_una_lista_cuenta_una_vez(self):
        cli = cli_con({1: [5, 5, 5], 2: [6]})
        res = dict((m.title, n) for m, n in L.descubrir(cli, [1, 2], excluir=set()))
        assert res["Tema 5"] == 1, "tres veces en la lista de UNA semilla es una sola coincidencia"

    def test_a_igualdad_conserva_el_orden_de_soundcloud(self):
        cli = cli_con({1: [30, 10, 20]})
        assert [m.title for m, _ in L.descubrir(cli, [1], excluir=set())] == ["Tema 30", "Tema 10", "Tema 20"]

    def test_respeta_el_maximo(self):
        cli = cli_con({1: list(range(100, 160))})
        assert len(L.descubrir(cli, [1], excluir=set(), maximo=10)) == 10

    def test_sin_semillas_no_consulta(self):
        cli = MagicMock()
        assert L.descubrir(cli, [], excluir=set()) == []
        cli.get_related.assert_not_called()

    def test_una_semilla_sin_parecidos_no_rompe(self):
        cli = cli_con({1: [], 2: [4]})
        assert [m.title for m, _ in L.descubrir(cli, [1, 2], excluir=set())] == ["Tema 4"]


def _api(likes, cliente):
    api = object.__new__(WebViewAPI)
    api._tracks = {}
    api._lock = threading.Lock()
    api._window = None
    api._playlist_cache = {}
    api.controller = MagicMock()
    api.controller.is_track_downloaded.return_value = False
    api._push = MagicMock()
    api._sc_client = lambda: cliente
    api._sync_manager = MagicMock()
    api._sync_manager.history.load_likes.return_value = likes
    return api


def like(i):
    return {"id": i, "url": f"https://soundcloud.com/likes/l{i}", "title": f"Like {i}", "artist": "X"}


class TestPanelDescubrir(unittest.TestCase):
    def test_parte_de_los_ultimos_likes_y_muestra_las_coincidencias(self):
        cli = cli_con({1: [9, 7], 2: [9]})
        r = _api([like(1), like(2)], cli).get_playlist_entries("sc-discover")
        assert r["ok"] and r["descubrir"] is True and r["plataforma"] == "SoundCloud"
        assert [(e["title"], e["coincidencias"]) for e in r["entradas"]] == [("Tema 9", 2), ("Tema 7", 1)]

    def test_solo_usa_los_likes_mas_recientes(self):
        likes = [like(i) for i in range(1, 40)]
        cli = MagicMock()
        cli.get_related.return_value = []
        _api(likes, cli).get_playlist_entries("sc-discover")
        assert cli.get_related.call_count == L.SEMILLAS_DESCUBRIR

    def test_sin_likes_guardados_explica_que_hacer(self):
        r = _api([], MagicMock()).get_playlist_entries("sc-discover")
        assert r["ok"] is False and "Sincronizar" in r["error"]

    def test_sin_cuenta_conectada_avisa(self):
        r = _api([like(1)], None).get_playlist_entries("sc-discover")
        assert r["ok"] is False and "Conect" in r["error"]

    def test_no_baja_nada_solo(self):
        cli = cli_con({1: [9]})
        api = _api([like(1)], cli)
        api.get_playlist_entries("sc-discover")
        assert api._tracks == {}, "las sugerencias no entran a la cola sin que las elijas"

    def test_lo_elegido_se_agrega_a_la_cola(self):
        cli = cli_con({1: [9, 7]})
        api = _api([like(1)], cli)
        api._asegurar_generos_en_segundo_plano = MagicMock()
        api.get_playlist_entries("sc-discover")
        r = api.add_playlist_selection("sc-discover", ["https://soundcloud.com/a/t9"])
        assert r["agregadas"] == 1 and list(api._tracks) == ["https://soundcloud.com/a/t9"]


class TestParecidosEnLaSync(unittest.TestCase):
    def test_un_tema_que_baja_la_sync_ofrece_parecidos(self):
        api = _api([], None)
        track = types.SimpleNamespace(url="https://soundcloud.com/a/t1", title="T", artist="A",
                                      duration_ms=1000, artwork_url="", id=555)
        api._on_sync_track_event("start", track)
        assert api._tracks["https://soundcloud.com/a/t1"].playlist_url == "sc-related:555"

    def test_sin_id_no_inventa_la_referencia(self):
        api = _api([], None)
        track = types.SimpleNamespace(url="https://soundcloud.com/a/t2", title="T", artist="A",
                                      duration_ms=1000, artwork_url="")
        api._on_sync_track_event("start", track)
        assert api._tracks["https://soundcloud.com/a/t2"].playlist_url == ""


if __name__ == "__main__":
    unittest.main()
