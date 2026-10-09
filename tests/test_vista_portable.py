"""
La interfaz tiene que abrir en cualquier equipo, sin internet y en WebKit viejo
(un Mac con Catalina): la ventana quedaba en negro mientras esperaba las
tipografias de Google Fonts.
"""
import re
import unittest
from pathlib import Path

VISTA = Path(__file__).resolve().parents[1] / "webview_app"


class TestVistaPortable(unittest.TestCase):
    def setUp(self):
        self.html = (VISTA / "view.html").read_text(encoding="utf-8")

    def test_no_carga_estilos_ni_scripts_de_internet(self):
        externos = re.findall(r'<(?:link|script)[^>]+(?:href|src)="(https?://[^"]+)"', self.html)
        assert externos == []

    def test_las_tipografias_incluidas_existen(self):
        css = (VISTA / "fonts" / "fonts.css").read_text(encoding="utf-8")
        archivos = set(re.findall(r"url\(([^)]+)\)", css))
        assert archivos, "fonts.css no referencia ninguna tipografia"
        faltan = [a for a in archivos if not (VISTA / "fonts" / a).is_file()]
        assert faltan == []

    def test_javascript_sin_sintaxis_de_2020(self):
        # ?. y ?? necesitan Safari 13.1+; con un WebKit mas viejo el script
        # entero no se lee y la app no responde.
        codigo = "\n".join(re.findall(r"<script>(.*?)</script>", self.html, re.S))
        sin_textos = re.sub(r'"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'|`(?:\\.|[^`\\])*`', '""', codigo)
        sin_regex_ni_comentarios = re.sub(r"//[^\n]*", "", sin_textos)
        assert "?." not in sin_regex_ni_comentarios
        assert "??" not in sin_regex_ni_comentarios


if __name__ == "__main__":
    unittest.main()
