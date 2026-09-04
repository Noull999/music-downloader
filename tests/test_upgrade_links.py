"""
Tests de la detección de gates de descarga (sync/upgrade_links.py).

Nunca completa el gate automáticamente: solo detecta que existe y le da
al usuario un link para abrir. Ver el docstring del módulo.
"""
import unittest

from sync.upgrade_links import candidatos_de_mejor_calidad, clasificar, es_gate_de_descarga


class TestClasificar(unittest.TestCase):
    def test_reconoce_hypeddit(self):
        assert clasificar("https://hypeddit.com/artista/tema")[1] == "Hypeddit"

    def test_subdominio_de_bandcamp_se_normaliza(self):
        base, etiqueta = clasificar("https://artista.bandcamp.com/track/tema")
        assert base == "bandcamp.com" and etiqueta == "Bandcamp"

    def test_dominio_desconocido_se_muestra_tal_cual(self):
        # Se reduce a los últimos dos segmentos, igual que con bandcamp:
        # el "www." no aporta nada para identificar el sitio.
        base, etiqueta = clasificar("https://www.prototypesrecords.com/pr109")
        assert etiqueta == "prototypesrecords.com"

    def test_url_invalida_no_rompe(self):
        base, etiqueta = clasificar("no es una url")
        assert base == ""


class TestEsGateDeDescarga(unittest.TestCase):
    def test_hypeddit_es_gate(self):
        assert es_gate_de_descarga("https://hypeddit.com/x")

    def test_beatport_no_es_gate(self):
        # Ahí se paga, no hay nada gratis que la app pueda ofrecer.
        assert not es_gate_de_descarga("https://www.beatport.com/release/x/123")

    def test_spotify_no_es_gate(self):
        assert not es_gate_de_descarga("https://open.spotify.com/track/x")

    def test_vacio_no_es_gate(self):
        assert not es_gate_de_descarga("")


class TestCandidatos(unittest.TestCase):
    def _like(self, url, purchase_url="", downloadable=False, **extra):
        return {"url": url, "title": "T", "artist": "A",
                "purchase_url": purchase_url, "downloadable": downloadable, **extra}

    def test_solo_lo_ya_descargado_entra(self):
        likes = [self._like("u1", purchase_url="https://hypeddit.com/x")]
        assert candidatos_de_mejor_calidad(likes, descargados={}) == []

    def test_con_gate_y_descargado_aparece(self):
        likes = [self._like("u1", purchase_url="https://hypeddit.com/x")]
        descargados = {"u1": {"local_path": "/x.mp3"}}
        out = candidatos_de_mejor_calidad(likes, descargados)
        assert len(out) == 1 and out[0]["servicio"] == "Hypeddit"

    def test_downloadable_no_necesita_gate(self):
        # El artista ya dejó bajar el original nativo; nada que mejorar.
        likes = [self._like("u1", purchase_url="https://hypeddit.com/x", downloadable=True)]
        descargados = {"u1": {"local_path": "/x.mp3"}}
        assert candidatos_de_mejor_calidad(likes, descargados) == []

    def test_sin_purchase_url_no_aparece(self):
        likes = [self._like("u1", purchase_url="")]
        descargados = {"u1": {"local_path": "/x.mp3"}}
        assert candidatos_de_mejor_calidad(likes, descargados) == []

    def test_link_de_compra_no_aparece(self):
        likes = [self._like("u1", purchase_url="https://www.beatport.com/release/x/1")]
        descargados = {"u1": {"local_path": "/x.mp3"}}
        assert candidatos_de_mejor_calidad(likes, descargados) == []


if __name__ == "__main__":
    unittest.main()
