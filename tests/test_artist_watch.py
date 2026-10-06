"""'Nuevos de mis artistas': que artistas se vigilan y que temas se muestran."""
import threading
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

from sync import artist_watch

AHORA = datetime(2026, 10, 6, 12, 0, tzinfo=timezone.utc)


def _like(uid, nombre="A"):
    return {"id": uid * 100, "user": {"id": uid, "username": nombre}}


def _tema(n, dias_atras, uid=1):
    f = (AHORA - timedelta(days=dias_atras)).isoformat().replace("+00:00", "Z")
    return {"id": n, "title": f"Tema {n}", "permalink_url": f"https://soundcloud.com/a/t{n}",
            "display_date": f, "created_at": f, "duration": 200000, "user": {"id": uid, "username": f"art{uid}"}}


class TestCalcularDesde(unittest.TestCase):
    def test_primera_vez_mira_30_dias(self):
        assert artist_watch.calcular_desde("", AHORA) == AHORA - timedelta(days=30)

    def test_usa_la_ultima_revision(self):
        ultima = (AHORA - timedelta(days=5)).isoformat()
        assert artist_watch.calcular_desde(ultima, AHORA) == AHORA - timedelta(days=5)

    def test_no_mira_mas_atras_del_tope(self):
        ultima = (AHORA - timedelta(days=400)).isoformat()
        assert artist_watch.calcular_desde(ultima, AHORA) == AHORA - timedelta(days=60)

    def test_fecha_ilegible_cuenta_como_primera_vez(self):
        assert artist_watch.calcular_desde("basura", AHORA) == AHORA - timedelta(days=30)


class TestArtistasVigilados(unittest.TestCase):
    def test_solo_los_que_tienen_dos_likes_o_mas_de_mas_a_menos(self):
        tracks = [_like(1)] * 3 + [_like(2)] * 2 + [_like(3)]
        assert [(u, n) for u, _, n in artist_watch.artistas_vigilados(tracks)] == [(1, 3), (2, 2)]

    def test_cambia_solo_si_se_da_like_a_otro_artista(self):
        tracks = [_like(1)] * 2 + [_like(3)]
        assert [u for u, _, _ in artist_watch.artistas_vigilados(tracks)] == [1]
        tracks.append(_like(3))
        assert {u for u, _, _ in artist_watch.artistas_vigilados(tracks)} == {1, 3}

    def test_respeta_el_tope(self):
        tracks = [_like(u) for u in range(1, 11) for _ in range(2)]
        assert len(artist_watch.artistas_vigilados(tracks, maximo=4)) == 4


class TestNuevosDeArtistas(unittest.TestCase):
    def _cli(self, likes, por_artista):
        cli = MagicMock()
        cli.get_tracks_by_ids.side_effect = lambda ids: [t for t in likes if t["id"] in ids]
        cli.get_user_tracks.side_effect = lambda uid, limit: por_artista.get(uid, [])
        return cli

    def test_solo_lo_posterior_a_la_ultima_revision(self):
        likes = [_like(1), _like(1)]
        likes[0]["id"], likes[1]["id"] = 100, 101
        cli = self._cli(likes, {1: [_tema(1, 2), _tema(2, 10)]})
        r = artist_watch.nuevos_de_artistas(cli, [100, 101], set(), AHORA - timedelta(days=5))
        assert [m.title for m, _f, _n in r] == ["Tema 1"]

    def test_excluye_likes_y_descargados(self):
        likes = [_like(1), _like(1)]
        likes[0]["id"], likes[1]["id"] = 100, 101
        cli = self._cli(likes, {1: [_tema(1, 1), _tema(2, 1)]})
        r = artist_watch.nuevos_de_artistas(
            cli, [100, 101], {"https://soundcloud.com/a/t1"}, AHORA - timedelta(days=5))
        assert [m.title for m, _f, _n in r] == ["Tema 2"]

    def test_ordena_del_mas_nuevo_al_mas_viejo_entre_artistas(self):
        likes = [_like(1), _like(1), _like(2), _like(2)]
        for i, l in enumerate(likes):
            l["id"] = 100 + i
        cli = self._cli(likes, {1: [_tema(1, 4, 1)], 2: [_tema(2, 1, 2)]})
        r = artist_watch.nuevos_de_artistas(cli, [100, 101, 102, 103], set(), AHORA - timedelta(days=30))
        assert [m.title for m, _f, _n in r] == ["Tema 2", "Tema 1"]

    def test_un_artista_que_falla_no_rompe_a_los_demas(self):
        likes = [_like(1), _like(1), _like(2), _like(2)]
        for i, l in enumerate(likes):
            l["id"] = 100 + i
        cli = self._cli(likes, {2: [_tema(2, 1, 2)]})
        orig = cli.get_user_tracks.side_effect
        cli.get_user_tracks.side_effect = lambda uid, limit: (_ for _ in ()).throw(RuntimeError("x")) if uid == 1 else orig(uid, limit)
        r = artist_watch.nuevos_de_artistas(cli, [100, 101, 102, 103], set(), AHORA - timedelta(days=30))
        assert [m.title for m, _f, _n in r] == ["Tema 2"]

    def test_sin_artistas_con_dos_likes_no_hay_nada(self):
        cli = self._cli([_like(1)], {})
        assert artist_watch.nuevos_de_artistas(cli, [100], set(), AHORA) == []


class TestEnLaApi(unittest.TestCase):
    def test_guarda_la_ultima_revision_solo_si_salio_bien(self):
        from webview_app.api import WebViewAPI
        api = object.__new__(WebViewAPI)
        api._lock = threading.Lock()
        api._sync_manager = MagicMock()
        api._sync_manager.history.load_likes.return_value = [{"id": 1, "url": "u1"}]
        api.controller = MagicMock()
        api.controller.get_config_value.return_value = ""
        api.controller.history.get_downloaded_urls.return_value = set()
        from unittest.mock import patch
        with patch.object(artist_watch, "nuevos_de_artistas", side_effect=RuntimeError("sin red")):
            with self.assertRaises(RuntimeError):
                api._artistas_nuevos(MagicMock())
        api.controller.set_config_value.assert_not_called()
        with patch.object(artist_watch, "nuevos_de_artistas", return_value=[]):
            api._artistas_nuevos(MagicMock())
        assert api.controller.set_config_value.call_args.args[0] == "artist_watch_last_check"


if __name__ == "__main__":
    unittest.main()
