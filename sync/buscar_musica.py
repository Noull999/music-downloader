"""
"Buscar musica en este equipo": encuentra las carpetas donde ya hay canciones
para usarlas como biblioteca en la deteccion de duplicados.

Antes la app solo comparaba contra la carpeta que contiene a la de destino, y
en un Mac de prueba no sabia que habia 23 GB de musica en ~/Music: la sync
podia bajar de nuevo temas que ya estaban. Esto recorre la carpeta personal (y
en Windows los demas discos) y devuelve cuantas canciones hay en cada carpeta
principal, para que la persona elija cuales cuentan.

Solo lista nombres de archivo: no abre, mueve ni modifica nada. Se salta
carpetas del sistema, de programas, ocultas y de la nube (abrir una carpeta de
OneDrive/Google Drive puede forzar descargas).
"""
import logging
import os
import sys
import time
from pathlib import Path

from sync import match_utils

logger = logging.getLogger(__name__)

MIN_CANCIONES = 5          # carpetas con menos se ignoran (sonidos de sistema, sueltos)
TIEMPO_MAXIMO_S = 90       # tope por si el disco es enorme o lento

_SALTAR_SIEMPRE = {
    # Windows
    "windows", "program files", "program files (x86)", "programdata", "appdata",
    "$recycle.bin", "system volume information", "recovery", "perflogs", "msocache",
    "$windows.~bt", "$windows.~ws", "windows.old", "intel", "amd", "nvidia",
    # macOS
    "library", "applications", "system", "private", "volumes", "cores",
    # Programas, desarrollo y nube
    "node_modules", "site-packages", "__pycache__", "venv", ".venv",
    "onedrive", "google drive", "icloud drive", "icloud drive (archive)", "dropbox",
    "steam", "steamapps", "epic games",
}


# Carpetas "de todo un poco": se muestran sus subcarpetas por separado, asi un
# proyecto con audios de voz (Escritorioideo-maker) no se confunde con la
# musica que esta al lado.
_CONTENEDORES = {"desktop", "escritorio", "documents", "documentos", "downloads", "descargas"}


def _saltar(nombre: str) -> bool:
    n = nombre.lower()
    return (n.startswith(".") or n.startswith("$") or n in _SALTAR_SIEMPRE
            or n.startswith("onedrive") or n.endswith(".app"))


def _discos_extra_windows() -> list[str]:
    """Discos fijos distintos del del sistema (D:, E:...), sin unidades de red ni de nube."""
    if sys.platform != "win32" or not hasattr(os, "listdrives"):
        return []
    import ctypes
    sistema = os.environ.get("SystemDrive", "C:").upper().rstrip("\\") + "\\"
    discos = []
    for d in os.listdrives():
        if d.upper() == sistema:
            continue
        try:
            if ctypes.windll.kernel32.GetDriveTypeW(d) != 3:   # 3 = disco fijo
                continue
            etiqueta = ctypes.create_unicode_buffer(261)
            ctypes.windll.kernel32.GetVolumeInformationW(d, etiqueta, 261, None, None, None, None, 0)
            if any(x in etiqueta.value.lower() for x in ("google drive", "onedrive", "dropbox")):
                continue
        except Exception:
            continue
        discos.append(d)
    return discos


def raices() -> list[str]:
    return [str(Path.home())] + _discos_extra_windows()


def _contar_arbol(carpeta: str, limite: float) -> tuple[int, bool]:
    """Canciones en `carpeta` y sus subcarpetas. Devuelve (cantidad, se_corto_por_tiempo)."""
    total = 0
    pila = [carpeta]
    while pila:
        if time.monotonic() >= limite:
            return total, True
        actual = pila.pop()
        try:
            with os.scandir(actual) as it:
                for e in it:
                    try:
                        if e.is_symlink():
                            continue
                        if e.is_dir():
                            if not _saltar(e.name):
                                pila.append(e.path)
                        elif (os.path.splitext(e.name)[1].lower() in match_utils.AUDIO_EXTENSIONS
                              and not match_utils.es_basura_del_sistema(Path(e.name))):
                            total += 1
                    except OSError:
                        continue
        except OSError:
            continue
    return total, False


def buscar(raices_a_revisar: list[str] = None, minimo: int = MIN_CANCIONES,
           tiempo_maximo: float = TIEMPO_MAXIMO_S) -> dict:
    """
    Recorre cada raiz y devuelve las carpetas de primer nivel (Escritorio,
    Musica, D:\\Musik...) que tienen al menos `minimo` canciones contando sus
    subcarpetas. No se ofrece la raiz entera (toda la carpeta personal o el
    disco): usarla como biblioteca obligaria a indexar el equipo completo en
    cada sincronizacion.
    """
    inicio = time.monotonic()
    limite = inicio + tiempo_maximo
    carpetas, cortado = [], False

    def revisar(carpeta: str, abrir_contenedores: bool):
        nonlocal cortado
        try:
            entradas = list(os.scandir(carpeta))
        except OSError:
            return
        sueltas = 0
        for e in entradas:
            try:
                if e.is_symlink():
                    continue
                if e.is_dir():
                    if _saltar(e.name):
                        continue
                    if abrir_contenedores and e.name.lower() in _CONTENEDORES:
                        revisar(e.path, False)
                        continue
                    n, corte = _contar_arbol(e.path, limite)
                    cortado = cortado or corte
                    if n >= minimo:
                        carpetas.append({"ruta": e.path, "canciones": n})
                elif (not abrir_contenedores
                      and os.path.splitext(e.name)[1].lower() in match_utils.AUDIO_EXTENSIONS
                      and not match_utils.es_basura_del_sistema(Path(e.name))):
                    sueltas += 1
            except OSError:
                continue
        # Canciones sueltas directo en el Escritorio/Descargas: se ofrece el
        # contenedor entero (nunca la raiz: ver arriba).
        if sueltas >= minimo:
            carpetas.append({"ruta": carpeta, "canciones": sueltas, "sueltas": True})

    for raiz in (raices_a_revisar or raices()):
        revisar(raiz, True)
    carpetas.sort(key=lambda c: c["canciones"], reverse=True)
    return {"carpetas": carpetas, "segundos": round(time.monotonic() - inicio, 1), "incompleto": cortado}
