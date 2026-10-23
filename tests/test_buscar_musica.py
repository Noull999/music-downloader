"""'Buscar musica en este equipo': que carpetas ofrece como biblioteca."""
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import MagicMock

from sync import buscar_musica


def _arbol(base: Path, archivos: dict):
    for ruta, n in archivos.items():
        d = base / ruta
        d.mkdir(parents=True, exist_ok=True)
        for i in range(n):
            (d / f"tema{i}.mp3").write_bytes(b"x")


class TestBuscar(unittest.TestCase):
    def setUp(self):
        self.raiz = Path(tempfile.mkdtemp())

    def _buscar(self, **kw):
        return buscar_musica.buscar([str(self.raiz)], **kw)

    def test_cuenta_subcarpetas_y_ordena_de_mas_a_menos(self):
        _arbol(self.raiz, {"Musik/Schranz": 7, "Musik/Techno": 3, "Music": 6})
        r = self._buscar()
        assert [(Path(c["ruta"]).name, c["canciones"]) for c in r["carpetas"]] == [("Musik", 10), ("Music", 6)]

    def test_el_escritorio_se_muestra_por_subcarpeta(self):
        # Un proyecto con audios de voz no se mezcla con la musica de al lado.
        _arbol(self.raiz, {"Desktop/Musica DJ": 8, "Desktop/video-maker/audio": 9, "Desktop": 0})
        for i in range(6):
            (self.raiz / "Desktop" / f"suelta{i}.mp3").write_bytes(b"x")
        r = sorted((str(Path(c["ruta"]).relative_to(self.raiz)), c["canciones"]) for c in self._buscar()["carpetas"])
        assert r == [("Desktop", 6), (str(Path("Desktop/Musica DJ")), 8), (str(Path("Desktop/video-maker")), 9)]

    def test_ignora_carpetas_con_pocas_canciones(self):
        _arbol(self.raiz, {"Sonidos": 2, "Musica": 5})
        assert [Path(c["ruta"]).name for c in self._buscar()["carpetas"]] == ["Musica"]

    def test_salta_sistema_programas_ocultas_y_nube(self):
        _arbol(self.raiz, {"Library/Audio": 9, "AppData/x": 9, ".cache": 9, "OneDrive - Personal": 9,
                           "Google Drive": 9, "node_modules/pkg": 9, "Steam.app": 9, "Musica": 6})
        assert [Path(c["ruta"]).name for c in self._buscar()["carpetas"]] == ["Musica"]

    def test_no_cuenta_basura_de_macos(self):
        d = self.raiz / "Musica"
        d.mkdir()
        for i in range(6):
            (d / f"._tema{i}.mp3").write_bytes(b"x")
        assert self._buscar()["carpetas"] == []

    def test_no_ofrece_la_raiz_entera(self):
        _arbol(self.raiz, {"": 0})
        for i in range(8):
            (self.raiz / f"suelta{i}.mp3").write_bytes(b"x")
        assert self._buscar()["carpetas"] == []

    def test_respeta_el_tiempo_maximo(self):
        _arbol(self.raiz, {"Musica": 6})
        r = self._buscar(tiempo_maximo=0)
        assert r["incompleto"] is True


class TestEnLaApi(unittest.TestCase):
    def test_marca_las_que_ya_cuentan_como_biblioteca(self):
        from webview_app.api import WebViewAPI
        api = object.__new__(WebViewAPI)
        api._lock = threading.Lock()
        api._library_folders = lambda: ["D:/Musik", "C:/Users/x/Desktop"]
        from unittest.mock import patch
        hallado = {"carpetas": [{"ruta": "D:/Musik", "canciones": 9}, {"ruta": "C:/Users/x/Music", "canciones": 6},
                                {"ruta": "C:/Users/x/Desktop/Musica DJ", "canciones": 5}],
                   "segundos": 1.0, "incompleto": False}
        with patch("sync.buscar_musica.buscar", return_value=hallado):
            r = api.buscar_musica_en_equipo()
        assert [c["incluida"] for c in r["carpetas"]] == [True, False, True]


if __name__ == "__main__":
    unittest.main()


class TestDondeSeGuarda(unittest.TestCase):
    """Las carpetas de biblioteca son para buscar duplicados, no para guardar."""

    def test_los_generos_van_dentro_de_la_carpeta_de_descarga(self):
        from webview_app.api import WebViewAPI
        api = object.__new__(WebViewAPI)
        api.controller = MagicMock()
        api.controller.get_config_value.side_effect = lambda k, d=None: {
            "dest_folder": "/Users/x/Desktop/All Music/musik_app",
            "library_folders": ["/Users/x/Desktop", "/Users/x/Music"]}.get(k, d)
        assert api.genre_root() == "/Users/x/Desktop/All Music/musik_app"

    def test_la_sync_tambien(self):
        from sync.sync_manager import SyncManager
        sm = SyncManager("OAuth x", "y" * 32, "/dest/musik_app", MagicMock(),
                         library_folders=["/Users/x/Desktop", "/Users/x/Music"])
        assert sm.genre_root == "/dest/musik_app"
