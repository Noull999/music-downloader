"""Etiquetas encontrables en Serato: casos reales de la biblioteca medida."""
import tempfile
import unittest
import wave
from pathlib import Path
from unittest.mock import patch

from analysis import tag_cleanup as tc


class TestLimpiar(unittest.TestCase):
    def test_codificacion_rota(self):
        assert tc.limpiar("TiÃ«sto") == "Tiesto"
        assert tc.limpiar("Patrice BÃ¤umel") == "Patrice Baumel"

    def test_letras_que_no_salen_del_teclado(self):
        assert tc.limpiar("KØZLØV x DORUKSEN") == "KOZLOV x DORUKSEN"
        assert tc.limpiar("VirtuаI Riоt") == "VirtuaI Riot"          # а y о cirílicas
        assert tc.limpiar("Axwell Λ Ingrosso") == "Axwell A Ingrosso"

    def test_lo_que_si_se_escribe_en_espanol_no_cambia(self):
        assert tc.limpiar("Canción del Niño ¿Qué?") == "Canción del Niño ¿Qué?"

    def test_un_titulo_entero_en_cirilico_no_se_toca(self):
        assert tc.limpiar("Привет") == "Привет"

    def test_quita_la_promo(self):
        assert tc.limpiar("FREE DL | Barbie Girl - Toxic Machinery remix") == "Barbie Girl - Toxic Machinery remix"
        assert tc.limpiar("LØINAM - Jumpscare (Original Mix) [FREE DOWNLOAD]") == "LOINAM - Jumpscare (Original Mix)"
        assert tc.limpiar("Tema (Temporary Free Download)") == "Tema"
        assert tc.limpiar("KØZLØV - SMASH - FREE DL") == "KOZLOV - SMASH"
        assert tc.limpiar("PREMIERE | Valeriø - Motivations [Schissma]") == "Valerio - Motivations [Schissma]"

    def test_no_se_come_titulos_legitimos(self):
        assert tc.limpiar("Free Download") == "Free Download"
        assert tc.limpiar("La Premiere") == "La Premiere"
        assert tc.limpiar("Freedom [TFT089]") == "Freedom [TFT089]"


class TestPropuesta(unittest.TestCase):
    def test_sin_artista_y_titulo_con_guion_se_separa(self):
        assert tc.propuesta("x.wav", "Fantasm - She Cheated On You", "") == ("She Cheated On You", "Fantasm")

    def test_sin_nada_sale_del_nombre_del_archivo(self):
        assert tc.propuesta("XTS, Kakarottomax - Accept Your Fate.mp3", "", "") == (
            "Accept Your Fate", "XTS, Kakarottomax")

    def test_con_artista_el_titulo_no_se_separa(self):
        assert tc.propuesta("x.mp3", "Tema - Extended Mix", "Artista") == ("Tema - Extended Mix", "Artista")

    def test_sin_guion_el_artista_queda_vacio(self):
        assert tc.propuesta("x.mp3", "Toro (Luciid Schranz Edit)", "") == ("Toro (Luciid Schranz Edit)", "")


class TestEnArchivoReal(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        self.wav = self.dir / "Veseli - Bass Gets Moved.wav"
        with wave.open(str(self.wav), "wb") as w:
            w.setnchannels(1); w.setsampwidth(2); w.setframerate(8000); w.writeframes(b"\0\0" * 800)

    def test_buscar_y_aplicar_en_un_wav_sin_etiquetas(self):
        cambios = tc.buscar_cambios([str(self.dir)])
        assert [c["despues"] for c in cambios] == [{"title": "Bass Gets Moved", "artist": "Veseli"}]
        with patch.object(tc, "CARPETA_RESPALDO", self.dir):
            r = tc.aplicar(cambios)
        assert r["aplicados"] == 1 and r["errores"] == 0 and Path(r["respaldo"]).is_file()
        _, t, a = tc._leer(str(self.wav))
        assert (t, a) == ("Bass Gets Moved", "Veseli")
        assert tc.buscar_cambios([str(self.dir)]) == []      # ya no hay nada que arreglar


if __name__ == "__main__":
    unittest.main()


class TestVerificaLoEscrito(unittest.TestCase):
    def test_si_no_quedo_escrito_cuenta_como_error(self):
        d = Path(tempfile.mkdtemp())
        wav = d / "Veseli - Bass Gets Moved.wav"
        with wave.open(str(wav), "wb") as w:
            w.setnchannels(1); w.setsampwidth(2); w.setframerate(8000); w.writeframes(b"\0\0" * 800)
        cambios = tc.buscar_cambios([str(d)])
        with patch.object(tc, "CARPETA_RESPALDO", d), \
             patch("mutagen.wave.WAVE.save", lambda *a, **k: None):   # "guarda" sin escribir
            r = tc.aplicar(cambios)
        assert (r["aplicados"], r["errores"]) == (0, 1)
