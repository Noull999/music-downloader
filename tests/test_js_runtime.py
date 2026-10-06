"""Motor JavaScript para YouTube: se ofrece a yt-dlp en todas las llamadas."""
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

from utils import js_runtime


class TestRuntimes(unittest.TestCase):
    def test_ofrece_deno_node_y_quickjs(self):
        assert set(js_runtime.runtimes()) == {"deno", "node", "quickjs"}

    def test_usa_el_quickjs_incluido_si_existe(self):
        with patch.object(js_runtime, "_quickjs_incluido", return_value="C:/x/qjs.exe"):
            assert js_runtime.runtimes()["quickjs"] == {"path": "C:/x/qjs.exe"}

    def test_sin_quickjs_incluido_lo_busca_en_el_path(self):
        with patch.object(js_runtime, "_quickjs_incluido", return_value=None):
            assert js_runtime.runtimes()["quickjs"] == {}

    def test_aplicar_no_pisa_lo_que_ya_viene(self):
        o = js_runtime.aplicar({"js_runtimes": {"node": {}}})
        assert o["js_runtimes"] == {"node": {}}
        assert "quickjs" in js_runtime.aplicar({})["js_runtimes"]

    def test_empaquetado_lo_busca_dentro_del_ejecutable(self):
        d = Path(__file__).resolve().parent / "_qjs_tmp" / "quickjs"
        d.mkdir(parents=True, exist_ok=True)
        nombre = "qjs.exe" if sys.platform == "win32" else "qjs"
        (d / nombre).write_bytes(b"x")
        try:
            with patch.object(sys, "frozen", True, create=True), \
                 patch.object(sys, "_MEIPASS", str(d.parent), create=True):
                assert js_runtime._quickjs_incluido() == str(d / nombre)
        finally:
            (d / nombre).unlink()
            d.rmdir(); d.parent.rmdir()

    def test_todos_los_usos_de_yt_dlp_pasan_por_aplicar(self):
        # Si alguien agrega un YoutubeDL nuevo sin el motor, YouTube vuelve al
        # modo obsoleto sin avisar: este test lo detecta.
        raiz = Path(__file__).resolve().parents[1]
        sin_motor = []
        for p in raiz.rglob("*.py"):
            if any(x in p.parts for x in ("build", "dist", "tests", "__pycache__")):
                continue
            for n, linea in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
                if "yt_dlp.YoutubeDL(" in linea and "js_runtime.aplicar(" not in linea:
                    sin_motor.append(f"{p.relative_to(raiz)}:{n}")
        assert sin_motor == []


if __name__ == "__main__":
    unittest.main()
