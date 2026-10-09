"""
Informe de diagnostico para cuando la app falla en el equipo de otra persona.

Si la ventana no carga o algo falla al abrir, se guarda un archivo de texto en
el Escritorio y se avisa con una ventana del sistema, para que la persona lo
mande por mensaje cuando pueda (sin tener que coincidir en una llamada).

Lleva el sistema, la version de WebKit, el final del log y los reportes de
cierre de macOS. Los tokens y claves se tachan antes de escribirlo.
"""
import logging
import platform
import re
import subprocess
import sys
import threading
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

CARPETA_APP = Path.home() / ".music_downloader"
NOMBRE = "MusicDownloader-informe.txt"
LINEAS_DE_LOG = 120

_SECRETOS = [
    (re.compile(r"OAuth\s+[\w-]{8,}", re.I), "OAuth ***"),
    (re.compile(r"(client_id=)[\w-]{8,}", re.I), r"\1***"),
    (re.compile(r"(oauth_token=)[\w-]{8,}", re.I), r"\1***"),
    (re.compile(r"\b2-\d{5,}-\d{3,}-[\w]{6,}\b"), "2-***"),
]


def tachar_secretos(texto: str) -> str:
    for patron, reemplazo in _SECRETOS:
        texto = patron.sub(reemplazo, texto)
    return texto


def carpeta_destino() -> Path:
    """El Escritorio si existe (es donde la persona lo encuentra), si no la carpeta de la app."""
    escritorio = Path.home() / "Desktop"
    return escritorio if escritorio.is_dir() else CARPETA_APP


def _version_webkit() -> str:
    if sys.platform != "darwin":
        return ""
    import plistlib
    partes = []
    for nombre, plist in (("WebKit", "/System/Library/Frameworks/WebKit.framework/Resources/Info.plist"),
                          ("Safari", "/Applications/Safari.app/Contents/Info.plist")):
        try:
            with open(plist, "rb") as f:
                d = plistlib.load(f)
            partes.append(f"{nombre} {d.get('CFBundleShortVersionString', '?')} ({d.get('CFBundleVersion', '?')})")
        except Exception:
            partes.append(f"{nombre} ?")
    return ", ".join(partes)


def _final_del_log() -> str:
    log = CARPETA_APP / "music_downloader.log"
    try:
        lineas = log.read_text(encoding="utf-8", errors="replace").splitlines()
        return "\n".join(lineas[-LINEAS_DE_LOG:])
    except OSError:
        return "(no hay log)"


def _reportes_de_cierre() -> str:
    if sys.platform != "darwin":
        return ""
    carpeta = Path.home() / "Library" / "Logs" / "DiagnosticReports"
    try:
        reportes = sorted((p for p in carpeta.iterdir() if "MusicDownloader" in p.name),
                          key=lambda p: p.stat().st_mtime, reverse=True)
    except OSError:
        return "(no se pudo leer DiagnosticReports)"
    if not reportes:
        return "(ninguno)"
    ultimo = reportes[0]
    try:
        cabeza = "\n".join(ultimo.read_text(encoding="utf-8", errors="replace").splitlines()[:60])
    except OSError:
        cabeza = "(no se pudo leer)"
    return f"{len(reportes)} reporte(s). El mas reciente: {ultimo.name}\n{cabeza}"


def escribir_informe(motivo: str, detalle: str = "") -> Path:
    """Escribe el informe y devuelve donde quedo."""
    error_arranque = CARPETA_APP / "error_arranque.txt"
    secciones = [
        f"Music Downloader: informe de diagnostico ({datetime.now():%Y-%m-%d %H:%M:%S})",
        f"Motivo: {motivo}",
        detalle and f"Detalle:\n{detalle}",
        f"Sistema: {platform.platform()} | {platform.machine()} | Python {platform.python_version()}",
        sys.platform == "darwin" and f"macOS {platform.mac_ver()[0]} | {_version_webkit()}",
        f"Ejecutable: {sys.executable}",
        error_arranque.is_file() and "== Error al arrancar ==\n" + error_arranque.read_text(
            encoding="utf-8", errors="replace"),
        "== Final del log ==\n" + _final_del_log(),
        sys.platform == "darwin" and "== Reportes de cierre de macOS ==\n" + _reportes_de_cierre(),
    ]
    texto = tachar_secretos("\n\n".join(s for s in secciones if s))
    destino = carpeta_destino() / NOMBRE
    try:
        destino.write_text(texto, encoding="utf-8")
    except OSError:
        CARPETA_APP.mkdir(parents=True, exist_ok=True)
        destino = CARPETA_APP / NOMBRE
        destino.write_text(texto, encoding="utf-8")
    logger.warning("Informe de diagnostico guardado en %s (%s)", destino, motivo)
    return destino


def avisar(titulo: str, mensaje: str) -> None:
    """Ventana del sistema que no bloquea la app."""
    try:
        if sys.platform == "darwin":
            seguro = mensaje.replace("\\", "\\\\").replace('"', '\\"')
            titulo_seguro = titulo.replace('"', "'")
            subprocess.Popen(["osascript", "-e",
                              f'display alert "{titulo_seguro}" message "{seguro}" as warning'])
        elif sys.platform == "win32":
            import ctypes
            threading.Thread(
                target=lambda: ctypes.windll.user32.MessageBoxW(None, mensaje, titulo, 0x30),
                daemon=True).start()
    except Exception:
        logger.exception("No se pudo mostrar el aviso")


def informar(motivo: str, detalle: str = "", mostrar: bool = True) -> Path:
    """Escribe el informe y avisa donde quedo."""
    destino = escribir_informe(motivo, detalle)
    if mostrar:
        avisar("Music Downloader tuvo un problema",
               f"{motivo}\n\nSe guardó un informe en:\n{destino}\n\n"
               "Mándaselo a quien te pasó la app para que lo revise. "
               "Si la ventana aparece después, puedes ignorar este aviso.")
    return destino
