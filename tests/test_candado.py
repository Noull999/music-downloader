"""Nunca dos sincronizaciones a la vez (la app y la automatica son procesos distintos)."""
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

from sync.candado import CandadoDeSync


class TestCandado(unittest.TestCase):
    def setUp(self):
        self.ruta = Path(tempfile.mkdtemp()) / "sync.lock"

    def test_otro_proceso_no_puede_tomarlo_mientras_esta_tomado(self):
        a = CandadoDeSync(self.ruta)
        assert a.tomar()
        codigo = textwrap.dedent(f"""
            import sys
            sys.path.insert(0, {str(Path(__file__).resolve().parents[1])!r})
            from sync.candado import CandadoDeSync
            print(CandadoDeSync({str(self.ruta)!r}).tomar())
        """)
        otro = subprocess.run([sys.executable, "-c", codigo], capture_output=True, text=True)
        assert otro.stdout.strip() == "False", otro.stderr
        a.soltar()
        otro = subprocess.run([sys.executable, "-c", codigo], capture_output=True, text=True)
        assert otro.stdout.strip() == "True", otro.stderr

    def test_se_libera_si_el_proceso_termina_sin_soltarlo(self):
        codigo = textwrap.dedent(f"""
            import sys
            sys.path.insert(0, {str(Path(__file__).resolve().parents[1])!r})
            from sync.candado import CandadoDeSync
            CandadoDeSync({str(self.ruta)!r}).tomar()
        """)
        subprocess.run([sys.executable, "-c", codigo], check=True)
        b = CandadoDeSync(self.ruta)
        assert b.tomar()
        b.soltar()

    def test_tomarlo_dos_veces_en_el_mismo_objeto_no_bloquea(self):
        a = CandadoDeSync(self.ruta)
        assert a.tomar() and a.tomar()
        a.soltar()


class TestSyncOcupada(unittest.TestCase):
    def test_sync_once_se_omite_si_otra_tiene_el_candado(self):
        from unittest.mock import MagicMock
        from sync.sync_manager import SyncManager
        ruta = Path(tempfile.mkdtemp()) / "sync.lock"
        ajeno = CandadoDeSync(ruta)
        codigo = textwrap.dedent(f"""
            import sys, time
            sys.path.insert(0, {str(Path(__file__).resolve().parents[1])!r})
            from sync.candado import CandadoDeSync
            c = CandadoDeSync({str(ruta)!r}); c.tomar(); print("ok", flush=True); time.sleep(20)
        """)
        p = subprocess.Popen([sys.executable, "-c", codigo], stdout=subprocess.PIPE, text=True)
        try:
            assert p.stdout.readline().strip() == "ok"
            sm = SyncManager("OAuth x", "y" * 32, tempfile.mkdtemp(), MagicMock())
            sm._candado = CandadoDeSync(ruta)
            sm.api = MagicMock()
            r = sm.sync_once()
            assert r.get("otra_en_curso") is True
            sm.api.get_likes.assert_not_called()
            assert sm._is_syncing is False
        finally:
            p.kill()
        del ajeno


if __name__ == "__main__":
    unittest.main()
