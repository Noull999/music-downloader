"""Informe de diagnostico: se escribe donde la persona lo encuentra y sin secretos."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from utils import informe


class TestTacharSecretos(unittest.TestCase):
    def test_tacha_token_client_id_y_cookie(self):
        texto = ("Authorization: OAuth 2-123456-7890-AbCdEfGhIj | "
                 "https://api-v2.soundcloud.com/x?client_id=abcdefghijklmnop12345678 | "
                 "oauth_token=2-999999-111-zzzzzzzz | suelto 2-555555-222-qwertyui")
        limpio = informe.tachar_secretos(texto)
        for secreto in ("2-123456-7890-AbCdEfGhIj", "abcdefghijklmnop12345678",
                        "2-999999-111-zzzzzzzz", "2-555555-222-qwertyui"):
            assert secreto not in limpio
        assert "client_id=***" in limpio

    def test_no_toca_texto_normal(self):
        t = "Interfaz cargada: 2026-10-09 12:04:03 BPM 160 (Schranz) 2-3 temas"
        assert informe.tachar_secretos(t) == t


class TestEscribirInforme(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        self.app = self.dir / ".music_downloader"
        self.app.mkdir()
        (self.app / "music_downloader.log").write_text(
            "linea vieja\nAuthorization: OAuth 2-123456-7890-AbCdEfGhIj\nInterfaz NO cargo\n", encoding="utf-8")
        self.escritorio = self.dir / "Desktop"
        self.escritorio.mkdir()

    def _escribir(self, *a):
        with patch.object(informe, "CARPETA_APP", self.app), \
             patch.object(informe, "carpeta_destino", return_value=self.escritorio):
            return informe.escribir_informe(*a)

    def test_queda_en_el_escritorio_con_el_motivo_y_el_log(self):
        destino = self._escribir("La ventana no cargó", "detalle X")
        assert destino == self.escritorio / informe.NOMBRE
        texto = destino.read_text(encoding="utf-8")
        assert "La ventana no cargó" in texto and "detalle X" in texto
        assert "Interfaz NO cargo" in texto

    def test_el_token_del_log_no_aparece(self):
        texto = self._escribir("x").read_text(encoding="utf-8")
        assert "2-123456-7890-AbCdEfGhIj" not in texto

    def test_incluye_el_error_de_arranque_si_existe(self):
        (self.app / "error_arranque.txt").write_text("Falta ffmpeg", encoding="utf-8")
        assert "Falta ffmpeg" in self._escribir("x").read_text(encoding="utf-8")

    def test_si_el_escritorio_no_se_puede_escribir_va_a_la_carpeta_de_la_app(self):
        with patch.object(informe, "CARPETA_APP", self.app), \
             patch.object(informe, "carpeta_destino", return_value=self.dir / "no_existe"):
            destino = informe.escribir_informe("x")
        assert destino == self.app / informe.NOMBRE and destino.is_file()

    def test_informar_avisa_solo_si_se_pide(self):
        with patch.object(informe, "escribir_informe", return_value=Path("x.txt")), \
             patch.object(informe, "avisar") as aviso:
            informe.informar("m", mostrar=False)
            aviso.assert_not_called()
            informe.informar("m")
            aviso.assert_called_once()


if __name__ == "__main__":
    unittest.main()
