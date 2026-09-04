"""
Tests de la resolución de subgénero (sync/genre_utils.py).

Los casos salen de datos reales de una biblioteca de 402 likes: el campo
`genre` de SoundCloud lo escribe el uploader y tira a lo genérico, mientras
el subgénero de verdad suele estar en los tags o en el propio título.
"""
import unittest

from sync.genre_utils import genre_folder, resolve_genre, split_tags


class TestPrioridadDeEspecificidad(unittest.TestCase):
    """Entre varias coincidencias, gana la más específica."""

    def test_tag_especifico_le_gana_al_genero_generico(self):
        # Caso real: el uploader puso "Techno", los tags dicen schranz.
        assert resolve_genre("Techno", "schranz hardtechno") == "Schranz"

    def test_hardgroove_le_gana_a_techno(self):
        assert resolve_genre("Techno", "hardgroove") == "Hardgroove"

    def test_industrial_techno_le_gana_a_hard_techno(self):
        assert resolve_genre("Hard Techno", "industrial techno") == "Industrial Techno"

    def test_sin_tags_se_queda_con_el_genero(self):
        assert resolve_genre("Hard Techno", "") == "Hard Techno"


class TestVariantesDeEscritura(unittest.TestCase):
    """El mismo género escrito de mil formas cae en una sola carpeta."""

    def test_variantes_de_hard_techno(self):
        for escrito in ("Hard Techno", "hardtechno", "HARDTECHNO",
                        "Hardtechno", "hard techno", "Hard Tehno"):
            assert resolve_genre(escrito, "") == "Hard Techno", escrito

    def test_sin_espacios_tambien_se_reconoce(self):
        # En SoundCloud es habitual etiquetar todo junto.
        assert resolve_genre("", "hardcoretechno") == "Hardcore Techno"
        assert resolve_genre("", "industrialhardtechno") == "Industrial Techno"

    def test_acentos_y_mayusculas_no_importan(self):
        assert resolve_genre("SCHRANZ", "") == "Schranz"


class TestFiltroDeBasura(unittest.TestCase):
    """Lo que no es un género no debe terminar siendo una carpeta."""

    def test_categorias_de_youtube_se_descartan(self):
        # YouTube pone su CATEGORÍA en el campo género.
        for basura in ("Music", "Entertainment", "People & Blogs"):
            assert resolve_genre(basura, "") is None, basura

    def test_palabras_de_promo_se_descartan(self):
        for basura in ("PREMIERE", "Free Download", "Edit", "Other"):
            assert resolve_genre(basura, "") is None, basura

    def test_volcado_de_tags_se_descarta(self):
        # Un uploader pegó su lista de tags dentro del campo género.
        assert resolve_genre("charli xcx, von dutch, brat, remix, psy", "") is None

    def test_hashtags_se_descartan(self):
        assert resolve_genre("#psybass #hardtechno", "") is None

    def test_nombre_de_sello_con_corchetes_se_descarta(self):
        assert resolve_genre("PREMIERE, Valeriø, [Schissma Records]", "") is None


class TestGeneroCompuesto(unittest.TestCase):
    def test_barra_separa_candidatos_y_gana_el_conocido(self):
        # Sin esto se creaba una carpeta con barra, que anida directorios.
        assert resolve_genre("Industrial Techno/Bochka", "") == "Industrial Techno"


class TestDesdeElTitulo(unittest.TestCase):
    """Último recurso: el título, solo con géneros inequívocos."""

    def test_schranz_en_el_titulo_se_reconoce(self):
        assert resolve_genre(None, None, "12 Inch (Dirtytech Schranz Edit)") == "Schranz"

    def test_palabras_ambiguas_no_se_toman_del_titulo(self):
        # "Acid Drop" es el nombre del tema, no el género Acid Techno.
        assert resolve_genre(None, None, "[FREE DL] Acid Drop - XTS") is None

    def test_el_titulo_es_ultimo_recurso_no_pisa_al_genero(self):
        # Con un género válido declarado, el título ni se mira.
        assert resolve_genre("Drum & Bass", None, "algo con schranz") == "Drum & Bass"
        # Sin género ni tags, ahí sí entra el título.
        assert resolve_genre(None, None, "algo con schranz") == "Schranz"


class TestSplitTags(unittest.TestCase):
    """tag_list usa espacios, con comillas para tags de varias palabras."""

    def test_separa_por_espacios(self):
        assert split_tags("Rave Hardtechno") == ["Rave", "Hardtechno"]

    def test_respeta_comillas(self):
        assert split_tags('"hard techno" rave') == ["hard techno", "rave"]

    def test_vacio_no_rompe(self):
        assert split_tags("") == []
        assert split_tags(None) == []


class TestNombreDeCarpeta(unittest.TestCase):
    def test_sin_datos_cae_en_el_fallback(self):
        assert genre_folder(None, None, None) == "Sin género"

    def test_no_devuelve_separadores_de_ruta(self):
        # Una barra en el nombre anidaría carpetas sin querer.
        nombre = genre_folder("Industrial Techno/Bochka", None, None)
        assert "/" not in nombre and "\\" not in nombre


if __name__ == "__main__":
    unittest.main()
