"""
Tests de analysis/acoustid_lookup.py: completar título/artista de archivos
con tags rotos identificando la canción por su huella de audio contra el
servicio web de AcoustID.

Todo lo que toca red (acoustid.lookup) y disco (fingerprint_comprimida,
mutagen) va mockeado: estos tests validan la lógica de decisión (cuándo
hay match confiable, cuándo no pisar un tag existente), no la integración
real con el servicio ni con archivos de audio de verdad.
"""
import unittest
from unittest.mock import MagicMock, patch

from analysis import acoustid_lookup


class TestIdentificar(unittest.TestCase):
    def test_sin_api_key_no_consulta_nada(self):
        with patch("analysis.acoustid_lookup.fingerprint_comprimida") as fp:
            resultado = acoustid_lookup.identificar("cancion.mp3", "")
        assert resultado is None
        fp.assert_not_called()

    def test_sin_huella_no_hay_match(self):
        with patch("analysis.acoustid_lookup.fingerprint_comprimida", return_value=None):
            resultado = acoustid_lookup.identificar("cancion.mp3", "key123")
        assert resultado is None

    def test_respuesta_con_error_no_hay_match(self):
        with patch("analysis.acoustid_lookup.fingerprint_comprimida", return_value=(180, "fp")):
            with patch.dict("sys.modules", {"acoustid": MagicMock(
                lookup=MagicMock(return_value={"status": "error", "error": {"message": "bad key"}})
            )}):
                resultado = acoustid_lookup.identificar("cancion.mp3", "key123")
        assert resultado is None

    def test_sin_resultados_no_hay_match(self):
        with patch("analysis.acoustid_lookup.fingerprint_comprimida", return_value=(180, "fp")):
            with patch.dict("sys.modules", {"acoustid": MagicMock(
                lookup=MagicMock(return_value={"status": "ok", "results": []})
            )}):
                resultado = acoustid_lookup.identificar("cancion.mp3", "key123")
        assert resultado is None

    def test_score_bajo_no_es_match_confiable(self):
        respuesta = {
            "status": "ok",
            "results": [{
                "score": 0.2,
                "recordings": [{"title": "Tema", "artists": [{"name": "Artista"}]}],
            }],
        }
        with patch("analysis.acoustid_lookup.fingerprint_comprimida", return_value=(180, "fp")):
            with patch.dict("sys.modules", {"acoustid": MagicMock(
                lookup=MagicMock(return_value=respuesta)
            )}):
                resultado = acoustid_lookup.identificar("cancion.mp3", "key123")
        assert resultado is None

    def test_sin_recordings_no_hay_match(self):
        respuesta = {"status": "ok", "results": [{"score": 0.9, "recordings": []}]}
        with patch("analysis.acoustid_lookup.fingerprint_comprimida", return_value=(180, "fp")):
            with patch.dict("sys.modules", {"acoustid": MagicMock(
                lookup=MagicMock(return_value=respuesta)
            )}):
                resultado = acoustid_lookup.identificar("cancion.mp3", "key123")
        assert resultado is None

    def test_match_confiable_devuelve_titulo_y_artista(self):
        respuesta = {
            "status": "ok",
            "results": [{
                "score": 0.95,
                "recordings": [{
                    "title": "Tema Real",
                    "artists": [{"name": "DJ Uno"}, {"name": "DJ Dos"}],
                }],
            }],
        }
        with patch("analysis.acoustid_lookup.fingerprint_comprimida", return_value=(180, "fp")):
            with patch.dict("sys.modules", {"acoustid": MagicMock(
                lookup=MagicMock(return_value=respuesta)
            )}):
                resultado = acoustid_lookup.identificar("cancion.mp3", "key123")
        assert resultado == {"title": "Tema Real", "artist": "DJ Uno, DJ Dos", "score": 0.95}

    def test_elige_el_resultado_de_mayor_score(self):
        respuesta = {
            "status": "ok",
            "results": [
                {"score": 0.6, "recordings": [{"title": "Peor match", "artists": []}]},
                {"score": 0.9, "recordings": [{"title": "Mejor match", "artists": []}]},
            ],
        }
        with patch("analysis.acoustid_lookup.fingerprint_comprimida", return_value=(180, "fp")):
            with patch.dict("sys.modules", {"acoustid": MagicMock(
                lookup=MagicMock(return_value=respuesta)
            )}):
                resultado = acoustid_lookup.identificar("cancion.mp3", "key123")
        assert resultado["title"] == "Mejor match"

    def test_excepcion_en_la_consulta_no_se_propaga(self):
        modulo_roto = MagicMock()
        modulo_roto.lookup.side_effect = RuntimeError("sin conexión")
        with patch("analysis.acoustid_lookup.fingerprint_comprimida", return_value=(180, "fp")):
            with patch.dict("sys.modules", {"acoustid": modulo_roto}):
                resultado = acoustid_lookup.identificar("cancion.mp3", "key123")
        assert resultado is None


class TestAplicarTags(unittest.TestCase):
    def _mock_audio(self, title="", artist=""):
        audio = MagicMock()
        audio.get.side_effect = lambda campo, default=None: {
            "title": [title] if title else [],
            "artist": [artist] if artist else [],
        }.get(campo, default)
        audio.__setitem__ = MagicMock()
        return audio

    def test_no_pisa_tags_existentes(self):
        audio = self._mock_audio(title="Ya tiene título", artist="Ya tiene artista")
        with patch("mutagen.File", return_value=audio):
            cambiado = acoustid_lookup.aplicar_tags(
                "cancion.mp3", {"title": "Otro título", "artist": "Otro artista"}
            )
        assert cambiado is False
        audio.__setitem__.assert_not_called()
        audio.save.assert_not_called()

    def test_completa_solo_el_campo_vacio(self):
        audio = self._mock_audio(title="", artist="Ya tiene artista")
        with patch("mutagen.File", return_value=audio):
            cambiado = acoustid_lookup.aplicar_tags(
                "cancion.mp3", {"title": "Tema Real", "artist": "Otro artista"}
            )
        assert cambiado is True
        audio.__setitem__.assert_called_once_with("title", "Tema Real")
        audio.save.assert_called_once()

    def test_sin_cambios_no_guarda(self):
        audio = self._mock_audio(title="Algo", artist="Alguien")
        with patch("mutagen.File", return_value=audio):
            cambiado = acoustid_lookup.aplicar_tags("cancion.mp3", {})
        assert cambiado is False
        audio.save.assert_not_called()

    def test_archivo_no_soportado_no_rompe(self):
        with patch("mutagen.File", return_value=None):
            cambiado = acoustid_lookup.aplicar_tags("cancion.raro", {"title": "X"})
        assert cambiado is False

    def test_excepcion_al_guardar_no_se_propaga(self):
        audio = self._mock_audio(title="")
        audio.save.side_effect = OSError("disco lleno")
        with patch("mutagen.File", return_value=audio):
            cambiado = acoustid_lookup.aplicar_tags("cancion.mp3", {"title": "Tema"})
        assert cambiado is False


if __name__ == "__main__":
    unittest.main()
