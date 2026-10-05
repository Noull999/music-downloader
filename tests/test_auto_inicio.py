"""Lo que se agrega a la cola (por link o marcado en una lista) empieza a bajar solo."""
import threading
import unittest
from unittest.mock import MagicMock

from models import STATUS_DONE, STATUS_PENDING, STATUS_SKIP, TrackInfo
from webview_app.api import WebViewAPI


def _api(auto=True, dest="D:/Musik"):
    api = object.__new__(WebViewAPI)
    api._tracks = {}
    api._enviadas = set()
    api._lock = threading.Lock()
    api._push = MagicMock()
    api._submit_one = MagicMock()
    api.controller = MagicMock()
    api.controller.get_config_value.side_effect = lambda k, d=None: {
        "auto_start_downloads": auto, "dest_folder": dest}.get(k, d)
    return api


def _t(n, status=STATUS_PENDING):
    t = TrackInfo(url=f"u{n}", title=f"T{n}")
    t.status = status
    return t


class TestAutoIniciar(unittest.TestCase):
    def test_manda_a_bajar_los_pendientes(self):
        api = _api()
        api._auto_iniciar([_t(1), _t(2)])
        assert api._submit_one.call_count == 2

    def test_no_toca_lo_que_ya_esta_descargado_o_saltado(self):
        api = _api()
        api._auto_iniciar([_t(1, STATUS_SKIP), _t(2, STATUS_DONE)])
        api._submit_one.assert_not_called()

    def test_no_manda_dos_veces_el_mismo(self):
        api = _api()
        t = _t(1)
        api._auto_iniciar([t])
        api._auto_iniciar([t])
        assert api._submit_one.call_count == 1

    def test_desactivado_en_configuracion_no_baja_nada(self):
        api = _api(auto=False)
        api._auto_iniciar([_t(1)])
        api._submit_one.assert_not_called()

    def test_sin_carpeta_de_destino_no_baja_nada(self):
        api = _api(dest="")
        api._auto_iniciar([_t(1)])
        api._submit_one.assert_not_called()

    def test_descargar_pendientes_no_repite_lo_ya_enviado(self):
        api = _api()
        a, b = _t(1), _t(2)
        api._tracks = {a.url: a, b.url: b}
        api._auto_iniciar([a])
        api.start_all_pending()
        enviados = [c.args[0].url for c in api._submit_one.call_args_list]
        assert sorted(enviados) == ["u1", "u2"]   # u1 una sola vez

    def test_al_terminar_se_puede_reintentar(self):
        api = _api()
        api._tracks = {"u1": _t(1)}
        api._enviadas.add("u1")
        api._push_status("u1", "error", "fallo")
        assert "u1" not in api._enviadas


if __name__ == "__main__":
    unittest.main()
