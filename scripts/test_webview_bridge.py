#!/usr/bin/env python3
"""
Test del puente webview_app.api.WebViewAPI SIN abrir ventana real
(este entorno no tiene display). Verifica que la orquestación de
config, historial y descarga funciona igual que gui/main_window.py.

IMPORTANTE: usa un config.json y una BD SQLite TEMPORALES via monkeypatch
de HistoryManager. Nunca toca ~/.music_downloader/history.db ni el
config.json real del proyecto.
"""
import json
import os
import re
import sys
import tempfile
import time
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from db.history_manager import HistoryManager

_FAILURES: list[str] = []


def check(name: str, cond: bool) -> None:
    print(f"  [{'OK' if cond else 'FAIL'}] {name}")
    if not cond:
        _FAILURES.append(name)


class _FakeWindow:
    """Sustituye la ventana pywebview real: registra evaluate_js sin ejecutar JS."""

    def __init__(self):
        self.events: list[tuple[str, dict]] = []

    def evaluate_js(self, js: str) -> None:
        # js == 'window.__bridgeEvent && window.__bridgeEvent("<name>", <payload>)'
        inner = js.split("window.__bridgeEvent(", 1)[1]
        inner = inner[: inner.rfind(")")]
        name_json, payload_json = inner.split(",", 1)
        self.events.append((json.loads(name_json), json.loads(payload_json)))

    def create_file_dialog(self, *a, **kw):
        return None


def _temp_history_factory(tmp_dir):
    def _factory(*_args, **_kwargs):
        return HistoryManager(db_path=os.path.join(tmp_dir, "test_history.db"))
    return _factory


def run() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        with patch("gui.ui_controller.HistoryManager", side_effect=_temp_history_factory(tmp)):
            from webview_app.api import WebViewAPI
            from models import TrackInfo, STATUS_DONE, STATUS_ERROR

            api = WebViewAPI(base_dir=tmp)

            print("\n== Config ==")
            cfg = api.get_config()
            check("get_config trae dest_folder", "dest_folder" in cfg)
            r = api.set_config_value("max_workers", 5)
            check("set_config_value ok=True", r["ok"] is True)
            check("cambio persistido en config", api.get_config()["max_workers"] == 5)
            check("config.json quedó en el tmp dir, no en el repo",
                  os.path.exists(os.path.join(tmp, "config.json")))

            print("\n== browse_folder sin ventana asignada ==")
            check("no crashea, retorna None", api.browse_folder() is None)

            print("\n== Historial / stats vacíos ==")
            check("get_recent_downloads() == []", api.get_recent_downloads() == [])
            check("get_stats total_downloads == 0", api.get_stats().get("total_downloads") == 0)

            print("\n== import_soundcloud_likes sin credenciales ==")
            r = api.import_soundcloud_likes()
            check("success=False", r["success"] is False)
            check("mensaje de error menciona token/config",
                  "token" in (r["error"] or "").lower() or "client_id" in (r["error"] or "").lower())

            print("\n== add_urls con entrada inválida ==")
            r = api.add_urls("esto no es una url")
            check("ok=False cuando no hay URLs válidas", r["ok"] is False)

            print("\n== Ciclo completo de descarga (handler falso, sin red/ffmpeg) ==")
            fake_win = _FakeWindow()
            api._window = fake_win

            fake_track = TrackInfo(url="https://soundcloud.com/fake/track",
                                    title="Fake Track", artist="Fake Artist")
            with api._lock:
                api._tracks[fake_track.url] = fake_track

            class FakeHandler:
                def download(self, url, output_path, quality_preset, progress_cb, cancel_check, **kw):
                    progress_cb(0.5)
                    progress_cb(1.0)
                    return None  # sin archivo -> debe resolver a STATUS_ERROR, no crashear

            with patch("webview_app.api.detect_handler", return_value=FakeHandler()):
                api.controller.set_config_value("dest_folder", tmp)
                result = api.start_download(fake_track.url)
                check("start_download acepta el track en cola", result["ok"] is True)

                deadline = time.time() + 5
                while time.time() < deadline and fake_track.status not in (STATUS_DONE, STATUS_ERROR):
                    time.sleep(0.05)

            check("el worker terminó en estado final (no se cuelga)",
                  fake_track.status in (STATUS_DONE, STATUS_ERROR))
            check("se emitieron eventos de progreso al frontend",
                  any(e[0] == "track_progress" for e in fake_win.events))
            check("se emitió track_status con el estado final",
                  any(e[0] == "track_status" and e[1]["status"] == fake_track.status
                      for e in fake_win.events))
            check("no se llamó record_download en camino de error (historial sigue vacío)",
                  api.get_stats().get("total_downloads") == 0)

            print("\n== Re-fetch de la misma URL no duplica en self._tracks ==")
            before = len(api._tracks)
            with patch("webview_app.api.detect_handler", return_value=FakeHandler()):
                api.add_urls(fake_track.url)
            check("no se agregó un track duplicado", len(api._tracks) == before)

            api.shutdown()

    print("\n" + "=" * 55)
    if _FAILURES:
        print(f"❌ {len(_FAILURES)} check(s) fallaron: {_FAILURES}")
        sys.exit(1)
    print("✅ Todos los checks del puente pywebview pasaron")


if __name__ == "__main__":
    run()
