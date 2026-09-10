"""
Tests de las URLs de SoundCloud que la app tiene que aceptar.

El bug: can_handle() exigía el dominio EXACTO soundcloud.com, mientras que
utils/validators.py aceptaba también los subdominios. Resultado: el link
que da el botón "Compartir" de la app del teléfono
(https://on.soundcloud.com/xxxx) pasaba el validador, entraba a la cola
como track, y recién al descargar moría con "URL no soportada".

Además yt-dlp entiende soundcloud.com, www. y m., pero NO on.: para esos
hay que seguir la redirección antes de pasárselo.
"""
import unittest
from unittest.mock import MagicMock, patch

from handlers.soundcloud_handler import SoundCloudHandler
from url_detector import detect_handler
from utils.validators import validate_url


class TestCanHandle(unittest.TestCase):
    def setUp(self):
        self.h = SoundCloudHandler()

    def test_acepta_dominio_normal_y_subdominios(self):
        for url in (
            "https://soundcloud.com/artista/tema",
            "https://www.soundcloud.com/artista/tema",
            "https://m.soundcloud.com/artista/tema",
            "https://on.soundcloud.com/abc123",
        ):
            assert self.h.can_handle(url), url

    def test_rechaza_dominio_que_solo_lo_contiene(self):
        # No alcanza con que "soundcloud.com" aparezca en el host.
        for url in (
            "https://soundcloud.com.otrositio.com/x",
            "https://notsoundcloud.com/x",
            "https://ejemplo.com/soundcloud.com",
        ):
            assert not self.h.can_handle(url), url

    def test_validador_y_handler_coinciden(self):
        # Lo que el validador deja entrar a la cola, un handler lo tiene
        # que poder atender: si no, el track falla recién al descargar.
        for url in (
            "https://on.soundcloud.com/abc123",
            "https://m.soundcloud.com/artista/tema",
            "https://soundcloud.com/artista/tema",
        ):
            assert validate_url(url), url
            assert isinstance(detect_handler(url), SoundCloudHandler), url


class TestNormalizeUrl(unittest.TestCase):
    def test_resuelve_el_link_corto(self):
        respuesta = MagicMock(url="https://soundcloud.com/artista/tema-real")
        sesion = MagicMock()
        sesion.head.return_value = respuesta
        with patch("utils.http_session.get_session", return_value=sesion):
            r = SoundCloudHandler.normalize_url("https://on.soundcloud.com/abc123")
        assert r == "https://soundcloud.com/artista/tema-real"

    def test_no_toca_una_url_normal(self):
        # Sin red de por medio: una URL que ya sirve no se resuelve.
        with patch("utils.http_session.get_session") as get_session:
            url = "https://soundcloud.com/artista/tema"
            assert SoundCloudHandler.normalize_url(url) == url
            get_session.assert_not_called()

    def test_si_falla_la_red_devuelve_la_original(self):
        sesion = MagicMock()
        sesion.head.side_effect = ConnectionError("sin red")
        with patch("utils.http_session.get_session", return_value=sesion):
            url = "https://on.soundcloud.com/abc123"
            assert SoundCloudHandler.normalize_url(url) == url

    def test_ignora_una_redireccion_fuera_de_soundcloud(self):
        # Si el acortador termina en otro dominio, no se sigue.
        respuesta = MagicMock(url="https://otrositio.com/loquesea")
        sesion = MagicMock()
        sesion.head.return_value = respuesta
        with patch("utils.http_session.get_session", return_value=sesion):
            url = "https://on.soundcloud.com/abc123"
            assert SoundCloudHandler.normalize_url(url) == url


if __name__ == "__main__":
    unittest.main()
