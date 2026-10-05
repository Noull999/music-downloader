"""
Tests de carátula, filtro de archivos basura y ruteo por carpeta de género.
Todos cubren fallos que se encontraron midiendo sobre una biblioteca real.
"""
import io
import os
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from quality.post_processor import PostProcessor
from sync import match_utils
from sync.sync_manager import SyncManager


def _imagen(formato: str, lado: int) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (lado, lado), (10, 20, 30)).save(buf, formato)
    return buf.getvalue()


class TestUrlDeCaratula(unittest.TestCase):
    """
    SoundCloud llama "large" a una miniatura de 100x100: incrustada se ve
    borrosa. Y "original" son 3000x3000 y ~900 KB en cada mp3.
    """

    def test_sube_las_miniaturas_a_500(self):
        for chica in ("-large.jpg", "-t300x300.jpg", "-small.jpg", "-tiny.jpg"):
            url = f"https://i1.sndcdn.com/artworks-abc{chica}"
            assert PostProcessor.upgrade_artwork_url(url).endswith("-t500x500.jpg"), chica

    def test_baja_original_tambien(self):
        url = "https://i1.sndcdn.com/artworks-abc-original.jpg"
        assert PostProcessor.upgrade_artwork_url(url).endswith("-t500x500.jpg")

    def test_deja_igual_lo_que_ya_esta_bien(self):
        url = "https://i1.sndcdn.com/artworks-abc-t500x500.jpg"
        assert PostProcessor.upgrade_artwork_url(url) == url

    def test_url_de_otra_plataforma_no_se_toca(self):
        url = "https://i.ytimg.com/vi/abc/maxresdefault.webp"
        assert PostProcessor.upgrade_artwork_url(url) == url

    def test_vacio_no_rompe(self):
        assert PostProcessor.upgrade_artwork_url("") == ""
        assert PostProcessor.upgrade_artwork_url(None) is None


class TestNormalizacionDeImagen(unittest.TestCase):
    """
    YouTube entrega las miniaturas en WebP, que Serato no muestra como
    carátula; y hay fuentes que dan imágenes enormes.
    """

    def test_webp_se_convierte_a_jpeg(self):
        datos, mime = PostProcessor.normalizar_imagen(_imagen("WEBP", 400))
        assert mime == "image/jpeg"
        assert Image.open(io.BytesIO(datos)).format == "JPEG"

    def test_imagen_gigante_se_achica(self):
        datos, _ = PostProcessor.normalizar_imagen(_imagen("JPEG", 3000), lado_max=600)
        assert max(Image.open(io.BytesIO(datos)).size) <= 600

    def test_jpeg_chico_se_deja_intacto(self):
        original = _imagen("JPEG", 500)
        datos, mime = PostProcessor.normalizar_imagen(original, lado_max=600)
        assert datos == original and mime == "image/jpeg"

    def test_png_se_conserva_como_png(self):
        _, mime = PostProcessor.normalizar_imagen(_imagen("PNG", 300), lado_max=600)
        assert mime == "image/png"

    def test_datos_invalidos_no_rompen(self):
        # Mejor una carátula imperfecta que una excepción a mitad de descarga.
        datos, _ = PostProcessor.normalizar_imagen(b"esto no es una imagen")
        assert datos == b"esto no es una imagen"


class TestBasuraDelSistema(unittest.TestCase):
    """
    macOS deja un "._Cancion.mp3" junto a cada archivo. Como copian la
    extensión, se contaban como música: en una biblioteca real eran 613
    falsos sobre 2036 archivos.
    """

    def test_detecta_appledouble_y_ds_store(self):
        assert match_utils.es_basura_del_sistema(Path("._Cancion.mp3"))
        assert match_utils.es_basura_del_sistema(Path(".DS_Store"))

    def test_no_descarta_musica_real(self):
        assert not match_utils.es_basura_del_sistema(Path("Cancion.mp3"))
        assert not match_utils.es_basura_del_sistema(Path("Tema.aiff"))

    def test_aiff_esta_soportado(self):
        # Formato habitual en Serato; antes quedaba invisible.
        assert ".aiff" in match_utils.AUDIO_EXTENSIONS
        assert ".aif" in match_utils.AUDIO_EXTENSIONS

    def test_el_indice_ignora_la_basura(self):
        tmp = Path(tempfile.mkdtemp())
        (tmp / "buena.mp3").write_bytes(b"x")
        (tmp / "._buena.mp3").write_bytes(b"x")
        (tmp / ".DS_Store").write_bytes(b"x")

        nombres = {p.name for p, _ in match_utils.index_audio_files([str(tmp)])}
        assert nombres == {"buena.mp3"}


class _TrackFalso:
    def __init__(self, genre="", tags="", title="Tema"):
        self.genre, self.tags, self.title = genre, tags, title


class TestRuteoPorGenero(unittest.TestCase):
    """Cada canción debe caer en la carpeta de su subgénero."""

    def setUp(self):
        self.raiz = Path(tempfile.mkdtemp())
        self.dest = self.raiz / "descargas"
        self.dest.mkdir()
        self.sm = SyncManager(
            "OAuth x", "x", str(self.dest), downloader=None,
            library_folders=[str(self.raiz)], subfolder_by_genre=True,
        )

    def _carpeta(self, track):
        return Path(self.sm._build_output_path("Artista", track.title, track)).parent.name

    def test_usa_el_subgenero_de_los_tags(self):
        assert self._carpeta(_TrackFalso("Techno", "schranz")) == "Schranz"

    def test_sin_datos_cae_en_sin_genero(self):
        assert self._carpeta(_TrackFalso("", "", "Tema sin pistas")) == "Sin género"

    def test_reusa_la_carpeta_existente_ignorando_mayusculas(self):
        # Con "hard techno" ya creada, no debe aparecer otra "Hard Techno".
        (self.raiz / "hard techno").mkdir()
        assert self._carpeta(_TrackFalso("Hard Techno")) == "hard techno"

    def test_las_carpetas_van_a_la_raiz_no_a_la_de_descarga(self):
        # Si no, quedarían dos juegos de carpetas separados.
        ruta = Path(self.sm._build_output_path("A", "T", _TrackFalso("Techno", "schranz")))
        assert ruta.parent.parent == self.raiz

    def test_desactivado_baja_a_la_carpeta_de_siempre(self):
        sm = SyncManager("OAuth x", "x", str(self.dest), downloader=None,
                         library_folders=[str(self.raiz)], subfolder_by_genre=False)
        ruta = Path(sm._build_output_path("A", "T", _TrackFalso("Techno", "schranz")))
        assert ruta.parent == self.dest


if __name__ == "__main__":
    unittest.main()
