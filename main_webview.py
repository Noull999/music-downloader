"""
Music Downloader — entry point con pywebview.
Ejecutar: python main_webview.py

No reemplaza main.py/gui/ (sigue intacto). Vista HTML/CSS en vez de
CustomTkinter, misma lógica de negocio (UIController, DownloadManager).

Requiere: pip install pywebview
"""
import io
import os
import shutil
import sys
from pathlib import Path

# Empaquetado con console=False, stdout/stderr pueden ser None o tener
# encoding cp1252 (los prints/logs de abajo llevan emojis) -> crash al
# abrir. Se arregla ANTES de cualquier print.
for _name in ("stdout", "stderr"):
    _stream = getattr(sys, _name)
    if _stream is None:
        setattr(sys, _name, io.StringIO())
    elif hasattr(_stream, "reconfigure"):
        try:
            _stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

from config.manager import DEFAULT_CONFIG_PATH
from utils.logger import setup_logging
from utils.dependencies import validate_all_dependencies
from utils.exceptions import DependencyNotFoundError

# ── Base portable: desarrollo (.py) y PyInstaller (.exe) ───────────────
if getattr(sys, "frozen", False):
    _BASE = str(Path(sys.executable).parent)
    # Los datas empaquetados (webview_app/, assets/) se extraen a _MEIPASS,
    # no a la carpeta del .exe.
    _RESOURCES = getattr(sys, "_MEIPASS", _BASE)
else:
    _BASE = str(Path(__file__).resolve().parent)
    _RESOURCES = _BASE

_VIEW_HTML = os.path.join(_RESOURCES, "webview_app", "view.html")

# config.json vive en ~/.music_downloader/ (estable, igual que la BD) y no
# junto al ejecutable: en el .exe empaquetado esa ruta es una carpeta
# temporal que Windows borra al cerrar, así que se perderían los ajustes en
# cada arranque. Misma ubicación que usa la GUI de tkinter, para que ambas
# interfaces compartan configuración en vez de divergir.
_CONFIG_PATH = str(DEFAULT_CONFIG_PATH)
if not os.path.isfile(_CONFIG_PATH):
    _legacy_config = os.path.join(_BASE, "config.json")
    if os.path.isfile(_legacy_config):
        os.makedirs(os.path.dirname(_CONFIG_PATH), exist_ok=True)
        shutil.copy2(_legacy_config, _CONFIG_PATH)


def validate_startup() -> bool:
    try:
        print("🔍 Validando dependencias...")
        results = validate_all_dependencies()
        print("\n✓ Dependencias validadas:")
        for dep, info in results.items():
            status = "✓" if info["status"] == "OK" else "⚠"
            version = f" v{info.get('version', 'N/A')}" if "version" in info else ""
            print(f"  {status} {dep}{version}")
        return True
    except DependencyNotFoundError as e:
        print(f"\n❌ ERROR DE DEPENDENCIA:\n{e}\n")
        return False
    except Exception as e:
        print(f"\n❌ ERROR AL VALIDAR:\n{e}\n")
        return False


def main():
    # Modo sin interfaz para la tarea programada. Permite que el .exe corra
    # la sincronización por sí mismo, sin depender de la carpeta del
    # proyecto ni de tener Python instalado.
    if "--auto-sync" in sys.argv:
        from sync import auto_sync_runner
        sys.exit(auto_sync_runner.run(
            _CONFIG_PATH, validate_only="--validate" in sys.argv
        ))

    if not validate_startup():
        sys.exit(1)

    try:
        import webview
    except ImportError:
        print(
            "\n❌ Falta pywebview. Instálalo con:\n\n"
            "    pip install pywebview\n\n"
            "En Windows/macOS no requiere nada más. En Linux necesita "
            "el backend GTK (WebKit2) o QT ya presente en la mayoría de "
            "distros de escritorio.\n"
        )
        sys.exit(1)

    if not os.path.exists(_VIEW_HTML):
        print(f"\n❌ No se encontró la vista: {_VIEW_HTML}")
        sys.exit(1)

    logger = setup_logging(log_level="INFO")
    logger.info("=" * 60)
    logger.info("🎵 Music Downloader (webview) iniciado")
    logger.info("=" * 60)

    from webview_app.api import WebViewAPI

    api = WebViewAPI(base_dir=_BASE, config_path=_CONFIG_PATH)

    window = webview.create_window(
        "Music Downloader",
        _VIEW_HTML,
        js_api=api,
        width=1180,
        height=760,
        min_size=(860, 580),
        background_color="#060507",
    )
    api.attach_window(window)

    try:
        webview.start(debug=os.environ.get("MD_WEBVIEW_DEBUG") == "1")
    finally:
        api.shutdown()


if __name__ == "__main__":
    main()
