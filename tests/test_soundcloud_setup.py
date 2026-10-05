"""Conexion guiada de SoundCloud: Client ID leido de la web y token leido de las cookies."""
import unittest
from http.cookies import SimpleCookie
from unittest.mock import MagicMock

from sync import soundcloud_setup as ss

ID = "a" * 32


class TestClientId(unittest.TestCase):
    def test_lo_saca_del_script(self):
        assert ss.client_id_en_js('x={api:"v2",client_id:"%s",env:1}' % ID) == ID

    def test_ignora_ids_de_largo_equivocado(self):
        assert ss.client_id_en_js('client_id:"corto"') is None
        assert ss.client_id_en_js("") is None

    def test_scripts_de_la_portada(self):
        html = ('<script src="https://a-v2.sndcdn.com/assets/0-a.js"></script>'
                '<script src="https://otro.com/x.js"></script>'
                '<script crossorigin src="https://a-v2.sndcdn.com/assets/1-b.js"></script>')
        assert ss.scripts_de_la_portada(html) == [
            "https://a-v2.sndcdn.com/assets/0-a.js", "https://a-v2.sndcdn.com/assets/1-b.js"]

    def test_detectar_recorre_de_atras_hacia_adelante(self):
        html = ('<script src="https://a-v2.sndcdn.com/assets/0.js"></script>'
                '<script src="https://a-v2.sndcdn.com/assets/1.js"></script>')
        paginas = {
            "https://soundcloud.com/": html,
            "https://a-v2.sndcdn.com/assets/0.js": "nada",
            "https://a-v2.sndcdn.com/assets/1.js": 'client_id:"%s"' % ID,
        }
        s = MagicMock()
        s.get.side_effect = lambda url, **kw: MagicMock(text=paginas[url])
        assert ss.detectar_client_id(s) == ID

    def test_sin_red_devuelve_none(self):
        import requests
        s = MagicMock()
        s.get.side_effect = requests.ConnectionError("sin red")
        assert ss.detectar_client_id(s) is None


class TestTokenDeCookies(unittest.TestCase):
    def test_cookie_de_pywebview(self):
        c = SimpleCookie()
        c["otra"] = "x"
        c["oauth_token"] = "2-123-456-abc"
        assert ss.token_de_cookies([c]) == "OAuth 2-123-456-abc"

    def test_diccionario(self):
        assert ss.token_de_cookies([{"name": "oauth_token", "value": '"2-1-2-z"'}]) == "OAuth 2-1-2-z"

    def test_si_ya_trae_el_prefijo_no_se_duplica(self):
        assert ss.token_de_cookies([{"name": "oauth_token", "value": "OAuth 2-1-2-z"}]) == "OAuth 2-1-2-z"

    def test_sin_sesion(self):
        c = SimpleCookie()
        c["otra"] = "x"
        assert ss.token_de_cookies([c]) is None
        assert ss.token_de_cookies([]) is None
        assert ss.token_de_cookies(None) is None


if __name__ == "__main__":
    unittest.main()
