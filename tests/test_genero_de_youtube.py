"""
Tests del genero de lo que se baja por link (sync/genre_chain.py y su
conexion en WebViewAPI).

Antes todo lo de YouTube caia en "Sin genero": el handler no guardaba
tags y los titulos casi nunca traen la palabra del genero. Medido sobre 14
temas reales, la app clasificaba 0.

Cadena, de mas a menos confiable: titulo -> tags/hashtags de YouTube -> el
mismo tema en SoundCloud -> voto por artista.
"""
import threading
import time
import unittest
from unittest.mock import MagicMock, patch

from models import TrackInfo
from sync.genre_chain import ResolutorDeGenero, hashtags
from webview_app.api import WebViewAPI


def sc(titulo, usuario, duracion_s, genero="", tags=""):
    return {"title": titulo, "user": {"username": usuario}, "duration": duracion_s * 1000,
            "genre": genero, "tag_list": tags}


class TestHashtags(unittest.TestCase):
    def test_extrae_hashtags(self):
        assert hashtags("Nuevo tema #guaracha #aleteo 2024") == ["guaracha", "aleteo"]

    def test_vacio(self):
        assert hashtags(None) == [] and hashtags("sin hashtags") == []


class TestCadena(unittest.TestCase):
    def test_el_titulo_gana_y_no_sale_a_internet(self):
        buscar = MagicMock(return_value=[])
        r = ResolutorDeGenero(buscar).resolver(title="Tema (Schranz Edit)", artist="A", duration_s=200)
        assert r == "Schranz"
        buscar.assert_not_called()

    def test_tags_de_youtube_con_varias_palabras(self):
        # "hard techno" debe llegar entero: partido en "hard" y "techno" daria
        # Techno en vez de Hard Techno.
        buscar = MagicMock(return_value=[])
        r = ResolutorDeGenero(buscar).resolver(title="Tema", artist="A", duration_s=200,
                                               tags='"hard techno" rave')
        assert r == "Hard Techno"
        buscar.assert_not_called()

    def test_un_tag_cualquiera_no_crea_carpetas(self):
        buscar = MagicMock(return_value=[])
        r = ResolutorDeGenero(buscar).resolver(title="Tema", artist="Alguien", duration_s=200,
                                               tags="music youtube alguien")
        assert r is None

    def test_hashtags_de_la_descripcion(self):
        buscar = MagicMock(return_value=[])
        r = ResolutorDeGenero(buscar).resolver(title="Tema", artist="A", duration_s=200,
                                               description="Out now! #hardgroove #rave")
        assert r == "Hardgroove"

    def test_el_mismo_tema_en_soundcloud(self):
        buscar = MagicMock(return_value=[sc("Noro$t - DIRTY BIT", "NORO$T", 200, genero="Nasty Club")])
        r = ResolutorDeGenero(buscar).resolver(title="Noro$t - DIRTY BIT", artist="NORO$T", duration_s=201)
        assert r == "Nasty Club"

    def test_ignora_el_mismo_titulo_con_otra_duracion(self):
        # Otro tema (o un remix) que se llama igual: no sirve.
        buscar = MagicMock(return_value=[sc("DIRTY BIT", "NORO$T", 340, genero="Techno")])
        assert ResolutorDeGenero(buscar).por_tema_exacto("NORO$T", "DIRTY BIT", 200) is None

    def test_ignora_un_titulo_distinto_aunque_dure_lo_mismo(self):
        buscar = MagicMock(return_value=[sc("Otra cancion distinta", "NORO$T", 200, genero="Techno")])
        assert ResolutorDeGenero(buscar).por_tema_exacto("NORO$T", "DIRTY BIT", 200) is None

    def test_si_el_tema_no_tiene_tags_cae_al_voto_por_artista(self):
        # El tema esta en SoundCloud pero el uploader no puso genero (paso en 5
        # de 16): se sigue con el artista.
        def buscar(q):
            if "DIRTY" in q:
                return [sc("DIRTY BIT", "NORO$T", 200)]  # sin genero ni tags
            return [sc(f"otro {i}", "NORO$T", 200, tags='"latin core"') for i in range(5)]
        r = ResolutorDeGenero(buscar).resolver(title="DIRTY BIT", artist="NORO$T", duration_s=200)
        assert r == "Latin Core"

    def test_sin_duracion_no_busca_el_tema_exacto(self):
        buscar = MagicMock(return_value=[])
        assert ResolutorDeGenero(buscar).por_tema_exacto("A", "T", 0) is None
        buscar.assert_not_called()

    def test_un_error_de_red_no_se_propaga(self):
        buscar = MagicMock(side_effect=ConnectionError("sin red"))
        assert ResolutorDeGenero(buscar).resolver(title="T", artist="A", duration_s=200) is None

    def test_no_repite_la_busqueda_del_mismo_tema(self):
        buscar = MagicMock(return_value=[sc("T", "A", 200, genero="Techno")])
        r = ResolutorDeGenero(buscar)
        r.por_tema_exacto("A", "T", 200)
        r.por_tema_exacto("A", "T", 200)
        assert buscar.call_count == 1


def _api():
    api = object.__new__(WebViewAPI)
    api._lock = threading.Lock()
    api._genero_eventos = {}
    api._genre_chain = MagicMock()
    return api


class TestAsegurarGenero(unittest.TestCase):
    def test_completa_el_genero_de_un_tema_de_soundcloud(self):
        api = _api()
        api._genre_chain.resolver.return_value = "Schranz"
        info = TrackInfo(url="u", title="T", artist="A", duration=200, platform="SoundCloud")
        api._asegurar_genero(info)
        assert info.genre == "Schranz"

    def test_no_pisa_si_la_cadena_no_encuentra_nada(self):
        api = _api()
        api._genre_chain.resolver.return_value = None
        info = TrackInfo(url="u", title="T", platform="SoundCloud", genre="Techno")
        api._asegurar_genero(info)
        assert info.genre == "Techno"

    def test_es_idempotente(self):
        api = _api()
        api._genre_chain.resolver.return_value = "Techno"
        info = TrackInfo(url="u", title="T", platform="SoundCloud")
        api._asegurar_genero(info)
        api._asegurar_genero(info)
        assert api._genre_chain.resolver.call_count == 1

    def test_un_error_no_se_propaga_ni_deja_a_otros_esperando(self):
        api = _api()
        api._genre_chain.resolver.side_effect = RuntimeError("boom")
        info = TrackInfo(url="u", title="T", platform="SoundCloud")
        api._asegurar_genero(info)  # no debe levantar
        assert api._genero_eventos["u"].is_set()

    def test_quien_baja_antes_de_que_termine_espera_el_resultado(self):
        # El usuario aprieta "Descargar" mientras el hilo de fondo todavia
        # busca el genero: la descarga espera en vez de ir a "Sin genero".
        api = _api()

        def lenta(**kw):
            time.sleep(0.4)
            return "Latin Core"

        api._genre_chain.resolver.side_effect = lenta
        info = TrackInfo(url="u", title="T", platform="SoundCloud")
        fondo = threading.Thread(target=api._asegurar_genero, args=(info,))
        fondo.start()
        time.sleep(0.1)
        api._asegurar_genero(info)          # el que llega "tarde"
        assert info.genre == "Latin Core"
        fondo.join()

    def test_un_video_de_youtube_trae_sus_tags_antes_de_resolver(self):
        api = _api()
        api._genre_chain.resolver.return_value = "Schranz"
        info = TrackInfo(url="https://youtube.com/watch?v=x", title="T", artist="A",
                         duration=200, platform="YouTube")
        meta = MagicMock(tags='"hard techno" rave', description="#schranz")
        handler = MagicMock()
        handler.get_metadata.return_value = [meta]
        with patch("webview_app.api.detect_handler", return_value=handler):
            api._asegurar_genero(info)
        kw = api._genre_chain.resolver.call_args.kwargs
        assert kw["tags"] == '"hard techno" rave' and kw["description"] == "#schranz"


if __name__ == "__main__":
    unittest.main()


class TestGeneroAceptable(unittest.TestCase):
    """
    Un genero que puso OTRA persona en SoundCloud ("240 Sound") no debe crear
    una carpeta nueva. Si ya existe esa carpeta ("Nasty Club") o es del
    vocabulario, si se acepta.
    """

    def test_el_rechazo_pasa_al_siguiente_paso(self):
        def buscar(q):
            if "DO MARGINAL" in q:
                return [sc("DO MARGINAL", "Artista Uno", 200, genero="240 Sound")]   # inventado
            return [sc(f"otro {i}", "Artista Uno", 200, genero="Techno") for i in range(5)]
        r = ResolutorDeGenero(buscar, aceptar=lambda g: g != "240 Sound").resolver(
            title="DO MARGINAL", artist="Artista Uno", duration_s=200)
        assert r == "Techno", "rechazado el del tema exacto, se sigue con el artista"

    def test_si_tampoco_el_artista_sirve_queda_sin_genero(self):
        buscar = MagicMock(return_value=[sc("DO MARGINAL", "Artista Uno", 200, genero="240 Sound")])
        r = ResolutorDeGenero(buscar, aceptar=lambda g: False).resolver(
            title="DO MARGINAL", artist="Artista Uno", duration_s=200)
        assert r is None

    def test_sin_filtro_acepta_todo(self):
        buscar = MagicMock(return_value=[sc("DIRTY BIT", "NORO$T", 200, genero="Nasty Club")])
        assert ResolutorDeGenero(buscar).resolver(title="DIRTY BIT", artist="NORO$T", duration_s=200) == "Nasty Club"

    def test_el_vocabulario_conocido_se_acepta(self):
        from sync import genre_utils
        assert genre_utils.es_conocido("Guaracha") and genre_utils.es_conocido("hard techno")
        assert not genre_utils.es_conocido("240 Sound") and not genre_utils.es_conocido("")

    def test_una_carpeta_que_ya_existe_se_acepta(self):
        import os, tempfile
        raiz = tempfile.mkdtemp()
        os.mkdir(os.path.join(raiz, "Nasty Club"))
        api = object.__new__(WebViewAPI)
        api.genre_root = lambda: raiz
        assert api._genero_aceptable("nasty club")          # sin importar mayusculas
        assert not api._genero_aceptable("240 Sound")
        assert api._genero_aceptable("Schranz")             # del vocabulario, aunque no exista la carpeta
