"""
Tests de WebViewAPI.get_preview_url: escuchar un fragmento de un tema en la
ventana de seleccion sin descargarlo.

Medido con temas reales: el enlace de audio se obtiene en 1-3 s y dura ~6 h.
El formato importa: el principal de SoundCloud (HLS) no lo toca un reproductor
de pagina, hay que pedir el MP3 directo.
"""
import threading
import unittest
from unittest.mock import MagicMock, patch

from webview_app.api import WebViewAPI, _motivo_sin_vista_previa


def _api(token=""):
    api = object.__new__(WebViewAPI)
    api._lock = threading.Lock()
    api.controller = MagicMock()
    api.controller.get_config_value.side_effect = lambda k, d=None: (
        {"oauth_token": token} if k == "soundcloud" else d)
    return api


def _con_yt_dlp(info=None, error=None):
    """Parche de yt_dlp.YoutubeDL que devuelve `info` (o lanza `error`) y guarda las opciones."""
    capturado = {}

    class FalsoYDL:
        def __init__(self, opts):
            capturado["opts"] = opts

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def extract_info(self, url, download=False):
            capturado["url"] = url
            if error:
                raise error
            return info

    return patch("yt_dlp.YoutubeDL", FalsoYDL), capturado


class TestVistaPrevia(unittest.TestCase):
    def test_devuelve_el_enlace_y_la_duracion(self):
        parche, cap = _con_yt_dlp({"url": "https://cdn/audio.m4a", "duration": 211, "protocol": "https"})
        with parche:
            r = _api().get_preview_url("https://www.youtube.com/watch?v=x")
        assert r == {"ok": True, "url": "https://cdn/audio.m4a", "duracion": 211}

    def test_no_descarga_nada(self):
        parche, cap = _con_yt_dlp({"url": "https://cdn/a.m4a", "protocol": "https"})
        with parche:
            _api().get_preview_url("https://www.youtube.com/watch?v=x")
        assert cap["opts"]["skip_download"] is True

    def test_youtube_pide_m4a(self):
        parche, cap = _con_yt_dlp({"url": "https://cdn/a.m4a", "protocol": "https"})
        with parche:
            _api().get_preview_url("https://www.youtube.com/watch?v=x")
        assert "m4a" in cap["opts"]["format"]

    def test_soundcloud_pide_el_mp3_directo_y_no_hls(self):
        parche, cap = _con_yt_dlp({"url": "https://cdn/a.mp3", "protocol": "http"})
        with parche:
            _api().get_preview_url("https://soundcloud.com/a/t")
        assert cap["opts"]["format"].startswith("http_mp3_1_0")

    def test_soundcloud_usa_el_token_si_hay(self):
        parche, cap = _con_yt_dlp({"url": "https://cdn/a.mp3", "protocol": "http"})
        with parche:
            _api(token="OAuth 2-abc").get_preview_url("https://soundcloud.com/a/t")
        assert cap["opts"]["extractor_args"] == {"soundcloud": {"oauth_token": ["OAuth 2-abc"]}}

    def test_un_formato_hls_se_rechaza(self):
        # Un reproductor de pagina no toca m3u8: mejor avisar que quedar mudo.
        parche, _ = _con_yt_dlp({"url": "https://cdn/a.m3u8", "protocol": "m3u8_native"})
        with parche:
            r = _api().get_preview_url("https://soundcloud.com/a/t")
        assert r["ok"] is False and "formato" in r["error"]

    def test_sin_enlace_avisa(self):
        parche, _ = _con_yt_dlp({"duration": 100})
        with parche:
            assert _api().get_preview_url("https://youtube.com/watch?v=x")["ok"] is False

    def test_un_error_de_yt_dlp_no_se_propaga(self):
        parche, _ = _con_yt_dlp(error=RuntimeError("This video is DRM protected"))
        with parche:
            r = _api().get_preview_url("https://soundcloud.com/a/t")
        assert r == {"ok": False, "error": "Este tema está protegido (DRM): no hay vista previa."}


class TestMotivo(unittest.TestCase):
    def test_mensajes_legibles(self):
        assert "DRM" in _motivo_sin_vista_previa("This video is DRM protected")
        assert "país" in _motivo_sin_vista_previa("not available from your location due to geo restriction")
        assert "edad" in _motivo_sin_vista_previa("Sign in to confirm your age")
        assert "disponible" in _motivo_sin_vista_previa("HTTP Error 404: Not Found")

    def test_lo_desconocido_no_expone_el_error_crudo(self):
        m = _motivo_sin_vista_previa("Traceback (most recent call last): ...")
        assert m == "No se pudo obtener el audio."


if __name__ == "__main__":
    unittest.main()
