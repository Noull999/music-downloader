"""
Music Downloader — entry point con pywebview.
Ejecutar: python main_webview.py

Vista HTML/CSS embebida; la lógica de negocio vive en UIController y
DownloadManager.

Requiere: pip install pywebview
"""
import io
import logging
import os
import shutil
import sys
import threading
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
# cada arranque.
# interfaces compartan configuración en vez de divergir.
_CONFIG_PATH = str(DEFAULT_CONFIG_PATH)
if not os.path.isfile(_CONFIG_PATH):
    _legacy_config = os.path.join(_BASE, "config.json")
    if os.path.isfile(_legacy_config):
        os.makedirs(os.path.dirname(_CONFIG_PATH), exist_ok=True)
        shutil.copy2(_legacy_config, _CONFIG_PATH)


def _error_fatal(titulo: str, detalle: str) -> None:
    """
    Muestra el error en una ventana del sistema, lo guarda en
    ~/.music_downloader/error_arranque.txt y cierra la app.

    Antes, si algo fallaba al arrancar, la app se cerraba sin mostrar nada
    (sobre todo en macOS, donde no hay consola): imposible saber por que.
    """
    texto = f"{titulo}\n\n{detalle}".strip()
    archivo = Path.home() / ".music_downloader" / "error_arranque.txt"
    try:
        archivo.parent.mkdir(parents=True, exist_ok=True)
        archivo.write_text(texto, encoding="utf-8")
    except OSError:
        archivo = None
    aviso = texto[-1500:]
    if archivo:
        aviso += f"\n\n(Guardado en {archivo})"
    try:
        if sys.platform == "darwin":
            import subprocess
            seguro = aviso.replace("\\", "\\\\").replace('"', '\\"')
            subprocess.run(
                ["osascript", "-e",
                 f'display alert "Music Downloader no pudo abrir" message "{seguro}" as critical'],
                timeout=600,
            )
        elif sys.platform == "win32":
            import ctypes
            ctypes.windll.user32.MessageBoxW(None, aviso, "Music Downloader no pudo abrir", 0x10)
    except Exception:
        pass
    print(texto, file=sys.stderr)
    sys.exit(1)


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
        _error_fatal("Falta una dependencia", str(e))
    except Exception as e:
        _error_fatal("Error al validar las dependencias", str(e))
    return False


def _limpiar_cache_de_imagenes() -> None:
    """
    Borra las carátulas cacheadas ya vencidas, en background.

    ImageCacheManager tenía el método pero nadie lo llamaba nunca: las
    entradas vencidas dejaban de leerse pero seguían ocupando lugar para
    siempre (los bytes de la imagen viven en la misma tabla). Va en un
    hilo aparte para no demorar el arranque de la ventana.
    """
    def tarea():
        try:
            from utils.image_cache import ImageCacheManager
            ImageCacheManager().cleanup_expired()
        except Exception:
            logging.getLogger(__name__).exception(
                "No se pudo limpiar el caché de imágenes (no es crítico)"
            )

    threading.Thread(target=tarea, daemon=True).start()


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
        _error_fatal("Falta un archivo de la app", f"No se encontró la vista: {_VIEW_HTML}")

    logger = setup_logging(log_level="INFO")
    logger.info("=" * 60)
    logger.info("🎵 Music Downloader (webview) iniciado")
    logger.info("=" * 60)

    from webview_app.api import WebViewAPI

    api = WebViewAPI(base_dir=_BASE, config_path=_CONFIG_PATH)
    _limpiar_cache_de_imagenes()

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
    try:
        main()
    except SystemExit:
        raise
    except BaseException:
        import traceback
        _error_fatal("Error inesperado al abrir la app", traceback.format_exc())
