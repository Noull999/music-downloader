"""Tests de la exportación de playlists M3U8 (sync/playlist_export.py)."""
import tempfile
import unittest
from pathlib import Path

from sync.playlist_export import exportar_por_carpeta


class TestExportarPorCarpeta(unittest.TestCase):
    def setUp(self):
        self.biblioteca = Path(tempfile.mkdtemp())
        self.destino = Path(tempfile.mkdtemp())

    def _tema(self, carpeta: str, nombre: str) -> Path:
        d = self.biblioteca / carpeta
        d.mkdir(exist_ok=True)
        p = d / nombre
        p.write_bytes(b"\x00" * 100)  # no es audio real, mutagen lo ignora sin romper
        return p

    def test_una_playlist_por_carpeta(self):
        self._tema("Schranz", "a.mp3")
        self._tema("Schranz", "b.mp3")
        self._tema("Guaracha", "c.mp3")

        out = exportar_por_carpeta(str(self.biblioteca), str(self.destino))

        nombres = {p["nombre"] for p in out}
        assert nombres == {"Schranz", "Guaracha"}
        cantidades = {p["nombre"]: p["canciones"] for p in out}
        assert cantidades == {"Schranz": 2, "Guaracha": 1}

    def test_el_archivo_tiene_formato_m3u8_valido(self):
        self._tema("Techno", "tema.mp3")
        out = exportar_por_carpeta(str(self.biblioteca), str(self.destino))

        contenido = Path(out[0]["archivo"]).read_text(encoding="utf-8")
        lineas = contenido.strip().splitlines()
        assert lineas[0] == "#EXTM3U"
        assert lineas[1].startswith("#EXTINF:")
        assert lineas[2].endswith("tema.mp3")

    def test_carpeta_vacia_no_genera_playlist(self):
        (self.biblioteca / "Vacia").mkdir()
        out = exportar_por_carpeta(str(self.biblioteca), str(self.destino))
        assert out == []

    def test_carpetas_excluidas_se_saltean(self):
        self._tema("Sin género", "a.mp3")
        self._tema("Schranz", "b.mp3")
        out = exportar_por_carpeta(str(self.biblioteca), str(self.destino),
                                   carpetas_excluidas={"sin género"})
        assert {p["nombre"] for p in out} == {"Schranz"}

    def test_ignora_basura_del_sistema(self):
        self._tema("Schranz", "real.mp3")
        self._tema("Schranz", "._real.mp3")
        (self.biblioteca / "Schranz" / ".DS_Store").write_bytes(b"x")

        out = exportar_por_carpeta(str(self.biblioteca), str(self.destino))
        assert out[0]["canciones"] == 1

    def test_carpeta_de_biblioteca_inexistente_no_rompe(self):
        assert exportar_por_carpeta(str(self.biblioteca / "no_existe"), str(self.destino)) == []

    def test_crea_la_carpeta_destino_si_no_existe(self):
        self._tema("Schranz", "a.mp3")
        destino_nuevo = self.destino / "una" / "ruta" / "que_no_existe"
        exportar_por_carpeta(str(self.biblioteca), str(destino_nuevo))
        assert destino_nuevo.is_dir()

    def test_nombre_de_playlist_es_seguro_como_archivo(self):
        # "Drum & Bass" no tiene caracteres inválidos en Windows, pero
        # confirma que el nombre de carpeta pasa por sanitize_filename.
        self._tema("Drum & Bass", "a.mp3")
        out = exportar_por_carpeta(str(self.biblioteca), str(self.destino))
        assert Path(out[0]["archivo"]).name == "Drum & Bass.m3u8"


if __name__ == "__main__":
    unittest.main()
