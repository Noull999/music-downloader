"""
Tamaño real en disco de una carpeta de biblioteca musical.

Separado de webview_app/api.py para poder testearlo sin instanciar toda
la API (DownloadManager, UIController, etc).
"""
import os

AUDIO_EXTENSIONS = (".mp3", ".flac", ".wav", ".aiff", ".m4a")


def audio_bytes_in(folder: str) -> int:
    """
    Suma el tamaño de todos los archivos de audio bajo `folder`, recursivo.
    Se usa en vez de sumar una columna 'file_size' guardada en el historial:
    esa columna queda vieja en cuanto una canción se mueve, se renombra, o
    el historial viene migrado desde otra carpeta/máquina (los local_path
    ya no apuntan a nada real), y termina subestimando el tamaño real.
    """
    if not folder or not os.path.isdir(folder):
        return 0
    total = 0
    for root, _dirs, files in os.walk(folder):
        for f in files:
            if f.lower().endswith(AUDIO_EXTENSIONS):
                try:
                    total += os.path.getsize(os.path.join(root, f))
                except OSError:
                    pass
    return total
