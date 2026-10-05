"""
Tests de lo que el historial considera "descargado".

El bug (caso del tema que la app decia tener y no estaba): HistoryManager.
is_downloaded devolvia True para CUALQUIER fila de la tabla `downloads`, aunque
no tuviera archivo. La importacion antigua de likes habia dejado 344 filas
"descargadas" con la ruta vacia, asi que al pegar el link de uno de esos temas
aparecia "ya descargada" y se omitia, sin decir donde estaba porque no estaba
en ningun lado. Ademas el contador "Descargas" sumaba esas filas y las 3275
canciones que ya estaban en la biblioteca (catalogadas como local://).
"""
import os
import tempfile
import unittest
from pathlib import Path

from db.history_manager import HistoryManager


class TestEsDescargada(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        self.h = HistoryManager(db_path=str(self.dir / "h.db"))

    def _archivo(self, nombre="tema.mp3") -> str:
        p = self.dir / nombre
        p.write_bytes(b"x")
        return str(p)

    def test_con_archivo_que_existe_si(self):
        self.h.add_download("u1", title="T", local_path=self._archivo())
        assert self.h.is_downloaded("u1") is True

    def test_fila_sin_ruta_no_cuenta(self):
        # El caso real: la importacion de likes dejaba la fila sin archivo.
        self.h.add_download("u2", title="El Beeper", local_path="")
        assert self.h.is_downloaded("u2") is False

    def test_ruta_que_ya_no_existe_no_cuenta(self):
        ruta = self._archivo()
        self.h.add_download("u3", title="T", local_path=ruta)
        os.remove(ruta)
        assert self.h.is_downloaded("u3") is False

    def test_url_desconocida_no(self):
        assert self.h.is_downloaded("nunca") is False


class TestContadores(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        self.h = HistoryManager(db_path=str(self.dir / "h.db"))
        real = self.dir / "a.mp3"
        real.write_bytes(b"x" * 100)
        self.h.add_download("u1", title="Real", platform="soundcloud", local_path=str(real), file_size=100)
        self.h.add_download("u2", title="Sin archivo", platform="soundcloud", local_path="")
        self.h.add_download("local://D:/serato/x.mp3", title="Ya lo tenias", platform="local",
                            local_path="D:/serato/x.mp3", file_size=999)

    def test_el_total_cuenta_solo_descargas_reales(self):
        assert self.h.get_stats()["total_downloads"] == 1
        assert self.h.get_download_count() == 1

    def test_por_plataforma_y_tamano_tampoco_cuentan_lo_demas(self):
        s = self.h.get_stats()
        assert s["by_platform"] == {"soundcloud": 1}
        assert s["total_size_bytes"] == 100


if __name__ == "__main__":
    unittest.main()


class TestArchivoNoSeParece(unittest.TestCase):
    """Mis Likes avisa cuando un like quedo enlazado a un archivo que no es el suyo."""

    def _f(self, artist, title, archivo):
        from sync.sync_manager import SyncManager
        return SyncManager._archivo_no_se_parece({"artist": artist, "title": title}, archivo)

    def test_un_tema_equivocado_se_marca(self):
        # Dos temas de O.B.I. quedaron enlazados a "Loreen - Tattoo": 31% de parecido.
        assert self._f("O.B.I.", "Schranzformator aka O.B.I. - Sunglasses",
                       "D:/Musik/Trance/Loreen - Tattoo Melodic Remix.mp3") is True

    def test_el_archivo_correcto_no_se_marca(self):
        assert self._f("duncs", "MY HUMPS (HARD TECHNO EDIT)",
                       "D:/Musik/Hard Techno/duncs - MY HUMPS (HARD TECHNO EDIT).mp3") is False

    def test_un_archivo_renombrado_de_verdad_no_se_marca(self):
        # Sin el sello, con guiones bajos: puntua 80-90, no debe dar falsa alarma.
        assert self._f("BMT", "Tryna' Get Me Tipsy [FREE DL]",
                       "D:/Musik/Techno/BMT_TrynaGetMeTipsy_160.wav") is False

    def test_lo_ya_catalogado_y_lo_vacio_no_se_marca(self):
        assert self._f("A", "Tema largo", None) is False
        assert self._f("A", "Tema largo", "local://D:/x/otro.mp3") is False


class TestUrlsDescargadas(unittest.TestCase):
    """Descubrir no sugiere lo que ya bajaste (aunque no sea un like)."""

    def test_solo_las_que_tienen_archivo(self):
        d = Path(tempfile.mkdtemp())
        h = HistoryManager(db_path=str(d / "h.db"))
        real = d / "a.mp3"
        real.write_bytes(b"x")
        borrado = d / "b.mp3"
        borrado.write_bytes(b"x")
        h.add_download("u-real", title="A", local_path=str(real))
        h.add_download("u-borrado", title="B", local_path=str(borrado))
        h.add_download("u-vacio", title="C", local_path="")
        h.add_download("local://x", title="D", local_path=str(real))
        os.remove(borrado)
        assert h.get_downloaded_urls() == {"u-real"}
