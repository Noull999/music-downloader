"""La interfaz se entrega como un solo HTML, sin servidor local ni archivos aparte."""
import re
import unittest
from pathlib import Path

from webview_app.armar_vista import armar_html

VISTA = Path(__file__).resolve().parents[1] / "webview_app" / "view.html"


class TestArmarVista(unittest.TestCase):
    def setUp(self):
        self.html = armar_html(str(VISTA))

    def test_no_queda_ninguna_referencia_a_archivos_locales(self):
        assert "fonts/fonts.css" not in self.html
        assert re.findall(r"url\((?!data:)[^)]*\.woff2\)", self.html) == []

    def test_lleva_las_tipografias_adentro(self):
        for familia in ("Pixelify Sans", "Silkscreen", "JetBrains Mono"):
            assert familia in self.html
        assert self.html.count("data:font/woff2;base64,") >= 8

    def test_conserva_la_pagina(self):
        assert self.html.rstrip().endswith("</html>")
        assert "window.__erroresJS" in self.html


if __name__ == "__main__":
    unittest.main()
