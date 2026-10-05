"""
Tests del respaldo de YouTube (sync/youtube_fallback.py y SyncManager._descargar).

Los casos de seleccion salen de la medicion sobre las 7 canciones fallidas
reales de la biblioteca (6 con DRM y 1 bloqueada por pais): los titulos,
canales y duraciones de abajo son los que devolvio YouTube.
"""
import sqlite3
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from sync import youtube_fallback
from sync.sync_manager import SyncManager
from sync.youtube_fallback import elegir_candidato, encontrar


def cand(titulo, duracion, canal, url="https://youtube.com/watch?v=x"):
    return {"title": titulo, "duration": duracion, "channel": canal, "url": url}


class TestElegirCandidato(unittest.TestCase):
    def test_prefiere_el_canal_topic(self):
        # Galactxtx - El Boton Color Caramelo: habia un Topic y un canal de
        # un tercero con titulo parecido. Gana el Topic (el master original).
        elegido = elegir_candidato([
            cand("Galactxtx - El Boton Color Caramelo. ,2025", 235, "toniv666", "https://y/otro"),
            cand("El Boton Color Caramelo", 235, "Galactxtx - Topic", "https://y/topic"),
        ], "Galactxtx", "El Boton Color Caramelo", 234)
        assert elegido["url"] == "https://y/topic"

    def test_descarta_el_remix_aunque_el_titulo_coincida(self):
        # "Piquepra (Yago Fuerte Remix)" puntuaba 100% de titulo pero duraba
        # 32 s de mas: es otra version.
        elegido = elegir_candidato([
            cand("Piquepra (Yago Fuerte Remix)", 267, "Noro$t - Topic", "https://y/remix"),
            cand("Noro$t - PIQUEPRA", 236, "NORO$T", "https://y/original"),
        ], "Noro$t", "PIQUEPRA", 235)
        assert elegido["url"] == "https://y/original"

    def test_descarta_la_version_instrumental_de_igual_duracion(self):
        # El caso peligroso: una "Instrumental" de otro canal con 0 s de
        # diferencia. La duracion sola no la frena.
        elegido = elegir_candidato([
            cand("KNTRLVRLST - Psycho (Instrumental)", 255, "TwigWeed STEMS", "https://y/instr"),
        ], "KNTRLVRLST", "Psycho", 255)
        assert elegido is None

    def test_la_variante_se_acepta_si_el_original_ya_la_trae(self):
        # Si el titulo de SoundCloud ya dice "Remix", un candidato con
        # "Remix" no es una version distinta.
        elegido = elegir_candidato([
            cand("Techno Girl (OZMOZ & MALO Remix)", 221, "Mondello' G - Topic"),
        ], "Mondello'G", "Techno Girl (OZMOZ & MALO Remix)", 220)
        assert elegido is not None

    def test_no_baja_nada_si_los_candidatos_son_de_otros(self):
        # Nico Parga - Veneno de Serpiente: solo habia remixes y "car audio"
        # de terceros. Lo correcto era no bajar nada.
        elegido = elegir_candidato([
            cand("VENENO DE SERPIENTE - REMIX - DJ KBZ@ x AXEL CAR", 253, "DJ KBZ@"),
            cand("VENENO DE SERPIENTE GUARACHA TRIVAL NUEVA 2021", 253, "NORBEY GARCIA"),
        ], "Nico Parga", "Veneno de Serpiente", 252)
        assert elegido is None

    def test_respeta_la_tolerancia_de_duracion(self):
        buenos = [cand("Tema", 100 + youtube_fallback.TOLERANCIA_DURACION, "Artista - Topic")]
        malos = [cand("Tema", 101 + youtube_fallback.TOLERANCIA_DURACION, "Artista - Topic")]
        assert elegir_candidato(buenos, "Artista", "Tema", 100) is not None
        assert elegir_candidato(malos, "Artista", "Tema", 100) is None

    def test_sin_duracion_de_referencia_no_adivina(self):
        c = [cand("Tema", 200, "Artista - Topic")]
        assert elegir_candidato(c, "Artista", "Tema", 0) is None
        assert elegir_candidato(c, "Artista", "Tema", None) is None

    def test_ignora_resultados_sin_titulo_o_duracion(self):
        # Un en vivo en curso no trae duracion en la busqueda plana.
        assert elegir_candidato([cand("Tema", 0, "Artista - Topic")], "Artista", "Tema", 200) is None

    def test_canal_del_propio_artista_cuenta_como_confiable(self):
        elegido = elegir_candidato([
            cand("Tema", 200, "Cualquiera", "https://y/ajeno"),
            cand("Tema", 200, "NORO$T", "https://y/propio"),
        ], "Noro$t", "Tema", 200)
        assert elegido["url"] == "https://y/propio"


class TestEncontrar(unittest.TestCase):
    def test_un_error_de_red_no_se_propaga(self):
        def buscar(q):
            raise ConnectionError("sin internet")
        assert encontrar("A", "T", 200, buscar=buscar) is None

    def test_busca_con_artista_y_titulo(self):
        consultas = []
        def buscar(q):
            consultas.append(q)
            return []
        encontrar("Noro$t", "ESO HPTA", 213, buscar=buscar)
        assert consultas == ["Noro$t ESO HPTA"]


class TestVacleProbarYoutube(unittest.TestCase):
    def test_errores_que_youtube_puede_resolver(self):
        for e in ("This video is DRM protected", "Track requiere SoundCloud Go+ (de pago)",
                  "This video is not available from your location due to geo restriction",
                  "HTTP Error 404: Not Found"):
            assert SyncManager._vale_probar_youtube(e), e

    def test_errores_que_no(self):
        for e in ("cancelled", "Connection reset by peer", "timed out", "", "private track"):
            assert not SyncManager._vale_probar_youtube(e), e


def _sync_con_historial_temporal(**kw):
    """SyncManager sin __init__ (que arma API, historial real, etc)."""
    from db.history import DownloadHistory
    sm = object.__new__(SyncManager)
    sm.history = DownloadHistory(db_path=str(Path(tempfile.mkdtemp()) / "h.db"))
    sm.downloader = MagicMock()
    sm.quality_preset = "mp3_320"
    sm._stop_event = threading.Event()
    sm.activity_log_callback = None
    sm.youtube_fallback_enabled = kw.get("habilitado", True)
    return sm


def _track(url="https://soundcloud.com/a/t"):
    t = MagicMock()
    t.url, t.title, t.artist, t.duration_ms = url, "Tema", "Artista", 200000
    return t


class TestDescargar(unittest.TestCase):
    def test_soundcloud_ok_no_toca_youtube(self):
        sm = _sync_con_historial_temporal()
        sm.downloader.download.return_value = "D:/x.mp3"
        with patch.object(youtube_fallback, "encontrar") as buscar:
            assert sm._descargar(_track(), "D:/x") == ("D:/x.mp3", "soundcloud")
            buscar.assert_not_called()

    def test_drm_cae_a_youtube(self):
        sm = _sync_con_historial_temporal()
        sm.downloader.download.side_effect = RuntimeError("This video is DRM protected")
        t = _track()
        sm.history.mark_failed(t.url, t.title, t.artist, "DRM", permanent=True)
        with patch.object(youtube_fallback, "encontrar", return_value={"url": "https://y/1"}), \
             patch("handlers.youtube_handler.YouTubeHandler") as YT:
            YT.return_value.download.return_value = "D:/x.mp3"
            r = sm._descargar(t, "D:/x")
        assert r == ("D:/x.mp3", "youtube")
        assert YT.return_value.download.call_args[0][0] == "https://y/1"
        assert sm.history.get_failed() == [], "al recuperarla se limpia de las fallidas"

    def test_sin_candidato_relanza_el_error_original(self):
        sm = _sync_con_historial_temporal()
        sm.downloader.download.side_effect = RuntimeError("This video is DRM protected")
        with patch.object(youtube_fallback, "encontrar", return_value=None):
            with self.assertRaises(RuntimeError) as cm:
                sm._descargar(_track(), "D:/x")
        assert "DRM" in str(cm.exception), "tiene que seguir clasificandose como DRM"

    def test_un_error_de_red_no_busca_en_youtube(self):
        sm = _sync_con_historial_temporal()
        sm.downloader.download.side_effect = RuntimeError("Connection reset by peer")
        with patch.object(youtube_fallback, "encontrar") as buscar:
            with self.assertRaises(RuntimeError):
                sm._descargar(_track(), "D:/x")
            buscar.assert_not_called()

    def test_la_cancelacion_no_busca_en_youtube(self):
        sm = _sync_con_historial_temporal()
        sm.downloader.download.side_effect = RuntimeError("cancelled")
        with patch.object(youtube_fallback, "encontrar") as buscar:
            with self.assertRaises(RuntimeError):
                sm._descargar(_track(), "D:/x")
            buscar.assert_not_called()

    def test_deshabilitado_no_busca(self):
        sm = _sync_con_historial_temporal(habilitado=False)
        sm.downloader.download.side_effect = RuntimeError("This video is DRM protected")
        with patch.object(youtube_fallback, "encontrar") as buscar:
            with self.assertRaises(RuntimeError):
                sm._descargar(_track(), "D:/x")
            buscar.assert_not_called()

    def test_si_youtube_tambien_falla_el_error_conserva_el_motivo(self):
        sm = _sync_con_historial_temporal()
        sm.downloader.download.side_effect = RuntimeError("This video is DRM protected")
        with patch.object(youtube_fallback, "encontrar", return_value={"url": "https://y/1"}), \
             patch("handlers.youtube_handler.YouTubeHandler") as YT:
            YT.return_value.download.side_effect = RuntimeError("HTTP 403")
            with self.assertRaises(RuntimeError) as cm:
                sm._descargar(_track(), "D:/x")
        assert "DRM" in str(cm.exception) and "403" in str(cm.exception)

    def test_anota_que_ya_se_busco_en_youtube(self):
        # Para no volver a buscar en cada sync una cancion que no esta.
        sm = _sync_con_historial_temporal()
        sm.downloader.download.side_effect = RuntimeError("This video is DRM protected")
        t = _track()
        sm.history.mark_failed(t.url, t.title, t.artist, "DRM", permanent=True)
        assert t.url in sm.history.get_youtube_pending()
        with patch.object(youtube_fallback, "encontrar", return_value=None):
            with self.assertRaises(RuntimeError):
                sm._descargar(t, "D:/x")
        assert t.url not in sm.history.get_youtube_pending()


class TestFiltroDeFallidas(unittest.TestCase):
    def test_una_fallida_permanente_sin_probar_youtube_pasa_una_vez(self):
        sm = _sync_con_historial_temporal()
        t = _track()
        sm.history.mark_failed(t.url, t.title, t.artist, "This video is DRM protected", permanent=True)
        pendientes, omitidas = sm._filter_unrecoverable([t])
        assert pendientes == [t] and omitidas == []

    def test_ya_probada_en_youtube_se_omite(self):
        sm = _sync_con_historial_temporal()
        t = _track()
        sm.history.mark_failed(t.url, t.title, t.artist, "This video is DRM protected", permanent=True)
        sm.history.mark_youtube_tried(t.url)
        pendientes, omitidas = sm._filter_unrecoverable([t])
        assert pendientes == [] and len(omitidas) == 1

    def test_deshabilitado_se_omite_como_siempre(self):
        sm = _sync_con_historial_temporal(habilitado=False)
        t = _track()
        sm.history.mark_failed(t.url, t.title, t.artist, "This video is DRM protected", permanent=True)
        pendientes, omitidas = sm._filter_unrecoverable([t])
        assert pendientes == [] and len(omitidas) == 1

    def test_una_fallida_de_otro_tipo_sigue_omitida(self):
        sm = _sync_con_historial_temporal()
        t = _track()
        sm.history.mark_failed(t.url, t.title, t.artist, "private track", permanent=True)
        pendientes, omitidas = sm._filter_unrecoverable([t])
        assert pendientes == [] and len(omitidas) == 1


if __name__ == "__main__":
    unittest.main()


class TestReintentarConYoutube(unittest.TestCase):
    """El boton "Probar desde YouTube" del panel de fallidas."""

    def _preparar(self, duracion_ms=200000):
        sm = _sync_con_historial_temporal()
        sm.track_event_callback = None
        sm.checker = MagicMock()
        sm.subfolder_by_genre = False
        sm.subfolder_by_artist = False
        sm.download_folder = tempfile.mkdtemp()
        sm.filename_pattern = "{artist} - {title}"
        sm.genre_root = sm.download_folder
        sm._post_process = MagicMock()
        url = "https://soundcloud.com/a/t"
        sm.history.mark_failed(url, "Tema", "Artista", "This video is DRM protected", permanent=True)
        import types
        sm.history.save_likes([types.SimpleNamespace(
            id=7, url=url, title="Tema", artist="Artista", duration_ms=duracion_ms,
            artwork_url="", genre="", tags="", created_at="2026-01-01",
        )])
        return sm, url

    def test_no_figura_como_fallida(self):
        sm, _ = self._preparar()
        r = sm.reintentar_con_youtube("https://soundcloud.com/otra/cosa")
        assert r["ok"] is False

    def test_sin_duracion_no_adivina(self):
        sm, url = self._preparar(duracion_ms=0)
        with patch.object(youtube_fallback, "encontrar") as buscar:
            r = sm.reintentar_con_youtube(url)
        assert r["ok"] is False and "duracion" in r["error"]
        buscar.assert_not_called()

    def test_sin_candidato_confiable_avisa_y_no_baja(self):
        sm, url = self._preparar()
        with patch.object(youtube_fallback, "encontrar", return_value=None), \
             patch("handlers.youtube_handler.YouTubeHandler") as YT:
            r = sm.reintentar_con_youtube(url)
        assert r["ok"] is False and "confiable" in r["error"]
        YT.return_value.download.assert_not_called()
        assert [f["url"] for f in sm.history.get_failed()] == [url], "sigue como fallida"

    def test_exito_registra_como_youtube_y_limpia_la_fallida(self):
        sm, url = self._preparar()
        with patch.object(youtube_fallback, "encontrar", return_value={"url": "https://y/1"}), \
             patch("handlers.youtube_handler.YouTubeHandler") as YT:
            YT.return_value.download.return_value = "D:/Musik/x.mp3"
            r = sm.reintentar_con_youtube(url)
        assert r == {"ok": True, "archivo": "D:/Musik/x.mp3"}
        assert sm.history.get_failed() == []
        fila = sm.history.conn.execute(
            "SELECT platform, file_path FROM sync_downloads WHERE url = ?", (url,)
        ).fetchone()
        assert fila == ("youtube", "D:/Musik/x.mp3")
        sm._post_process.assert_called_once()
