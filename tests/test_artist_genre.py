"""
Tests de sync/artist_genre.py: resolver el género preguntando por el
artista real en SoundCloud, cuando el track vino sin genre ni tags.

La búsqueda se inyecta, así que estos tests no tocan la red.
"""
import unittest

from sync.artist_genre import (
    ArtistGenreResolver,
    artistas_del_titulo,
    elegir_por_votos,
)


def track(usuario: str, genre: str = "", tags: str = "") -> dict:
    return {"user": {"username": usuario}, "genre": genre, "tag_list": tags}


class TestArtistasDelTitulo(unittest.TestCase):
    def test_separador_de_barra(self):
        assert artistas_del_titulo("Vlace & KSN | Hurt You") == ["Vlace", "KSN"]

    def test_separador_de_guion(self):
        assert artistas_del_titulo("DXPE - Mental Disease") == ["DXPE"]

    def test_ignora_parentesis_y_corchetes(self):
        # "[Proclam Rec.]" es el sello, no el artista.
        assert artistas_del_titulo("DXPE - Mental Disease [Proclam Rec.]") == ["DXPE"]
        # "(FREE DOWNLOAD)" fuera; "B2" también, por corto (ver test de abajo).
        assert artistas_del_titulo("B2 & Triptykh - Onyra (FREE DOWNLOAD)") == ["Triptykh"]

    def test_colaboracion_con_x(self):
        assert artistas_del_titulo("TNMN X A B P - KICK BACK") == ["TNMN", "A B P"]

    def test_descarta_nombres_demasiado_cortos(self):
        # "AB" no llega al mínimo: buscarlo traería cualquier cosa.
        assert artistas_del_titulo("AB - Tema") == []

    def test_titulo_vacio(self):
        assert artistas_del_titulo("") == []
        assert artistas_del_titulo(None) == []

    def test_corta_en_dos_artistas(self):
        # Más de dos son casi siempre un volcado, no una colaboración real.
        r = artistas_del_titulo("Uno & Dos & Tres & Cuatro - Tema")
        assert len(r) == 2


class TestElegirPorVotos(unittest.TestCase):
    def test_consenso_claro_gana(self):
        assert elegir_por_votos(["Schranz"] * 9 + ["Hard Techno"]) == "Schranz"

    def test_pocos_votos_no_alcanza(self):
        # Dos tracks del artista no son evidencia suficiente.
        assert elegir_por_votos(["Schranz", "Schranz"]) is None

    def test_votos_repartidos_no_alcanza(self):
        # 4 de 11 es un empate disfrazado: mejor sin género que mal ubicado.
        votos = ["Hardstyle"] * 4 + ["Hard Techno"] * 4 + ["Industrial Techno"] * 3
        assert elegir_por_votos(votos) is None

    def test_justo_en_el_umbral(self):
        # 5 de 10 = 50%, el mínimo aceptado (mayoría absoluta justa).
        assert elegir_por_votos(["Techno"] * 5 + ["House"] * 5) == "Techno"

    def test_apenas_por_debajo_del_umbral(self):
        # 4 de 9 = 44%: el ganador no llega a la mitad, no alcanza.
        assert elegir_por_votos(["Techno"] * 4 + ["House"] * 3 + ["Trance"] * 2) is None

    def test_lista_vacia(self):
        assert elegir_por_votos([]) is None


class TestArtistGenreResolver(unittest.TestCase):
    def test_resuelve_con_los_tags_del_artista(self):
        def buscar(nombre):
            return [track("Luciid", "Techno", "schranz")] * 9 + [track("Luciid", "Techno", "")]

        assert ArtistGenreResolver(buscar).resolver("Luciid | Reeky") == "Schranz"

    def test_ignora_tracks_de_otros_usuarios(self):
        # La búsqueda trae remixes ajenos que mencionan al artista: si se
        # contaran, el género saldría del remixer y no del artista.
        def buscar(nombre):
            return [track("OtroDJ", "", "hardstyle")] * 10

        assert ArtistGenreResolver(buscar).resolver("Luciid | Reeky") is None

    def test_sin_resultados(self):
        assert ArtistGenreResolver(lambda n: []).resolver("Alguien - Tema") is None

    def test_error_de_red_no_se_propaga(self):
        def buscar(nombre):
            raise ConnectionError("sin internet")

        assert ArtistGenreResolver(buscar).resolver("Luciid | Reeky") is None

    def test_cachea_por_artista(self):
        llamadas = []

        def buscar(nombre):
            llamadas.append(nombre)
            return [track("Luciid", "", "schranz")] * 5

        r = ArtistGenreResolver(buscar)
        r.resolver("Luciid | Tema Uno")
        r.resolver("Luciid | Tema Dos")
        r.resolver("Luciid | Tema Tres")
        assert llamadas == ["Luciid"], "debería consultar una sola vez por artista"

    def test_suma_votos_de_ambos_artistas(self):
        def buscar(nombre):
            if nombre == "Vlace":
                return [track("Vlace", "", "techno")] * 4
            return [track("KSN", "", "schranz")] * 6

        # 6 de 10 para Schranz: pasa el umbral.
        assert ArtistGenreResolver(buscar).resolver("Vlace & KSN | Hurt You") == "Schranz"


if __name__ == "__main__":
    unittest.main()
