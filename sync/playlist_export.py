"""
Exporta las carpetas de género como playlists M3U8, importables en Serato,
Rekordbox, VLC y prácticamente cualquier reproductor o software de DJ.

Se eligió M3U8 en vez del formato binario propio de cada software (los
.crate de Serato, el XML de Rekordbox) porque un solo formato sirve para
los dos sin tener que mantener dos exportadores, y ninguno de los dos
necesita nada instalado para leerlo: es texto plano.
"""
import logging
from pathlib import Path
from typing import Optional

from sync import match_utils
from sync.sync_manager import sanitize_filename

logger = logging.getLogger(__name__)


def _duracion_segundos(path: Path) -> int:
    """Duración en segundos, o -1 si no se puede leer (el estándar M3U lo permite)."""
    try:
        from mutagen import File as MFile
        audio = MFile(path)
        if audio and audio.info and audio.info.length:
            return int(audio.info.length)
    except Exception:
        pass
    return -1


def exportar_por_carpeta(
    raiz_biblioteca: str,
    destino: str,
    carpetas_excluidas: Optional[set[str]] = None,
) -> list[dict]:
    """
    Genera un .m3u8 por cada subcarpeta directa de `raiz_biblioteca` que
    tenga música (cada carpeta de género es una playlist).

    Args:
        raiz_biblioteca: carpeta que contiene las carpetas de género
                         (D:\\Musik en el caso típico de esta app).
        destino: carpeta donde escribir los .m3u8.
        carpetas_excluidas: nombres de carpeta a saltear en minúsculas
                            (p.ej. "sin género").

    Returns: [{"nombre": ..., "archivo": ..., "canciones": N}, ...]
    """
    raiz = Path(raiz_biblioteca)
    salida = Path(destino)
    salida.mkdir(parents=True, exist_ok=True)
    excluidas = {c.lower() for c in (carpetas_excluidas or set())}

    resultado = []
    if not raiz.is_dir():
        return resultado

    for carpeta in sorted(raiz.iterdir()):
        if not carpeta.is_dir() or carpeta.name.lower() in excluidas:
            continue

        canciones = [
            p for p in sorted(carpeta.iterdir())
            if p.is_file()
            and p.suffix.lower() in match_utils.AUDIO_EXTENSIONS
            and not match_utils.es_basura_del_sistema(p)
        ]
        if not canciones:
            continue

        lineas = ["#EXTM3U"]
        for cancion in canciones:
            dur = _duracion_segundos(cancion)
            lineas.append(f"#EXTINF:{dur},{cancion.stem}")
            lineas.append(str(cancion))

        archivo = salida / f"{sanitize_filename(carpeta.name)}.m3u8"
        try:
            archivo.write_text("\n".join(lineas) + "\n", encoding="utf-8")
        except OSError:
            logger.exception("No se pudo escribir la playlist de %s", carpeta.name)
            continue

        resultado.append({
            "nombre": carpeta.name,
            "archivo": str(archivo),
            "canciones": len(canciones),
        })
        logger.info("Playlist exportada: %s (%d temas)", archivo.name, len(canciones))

    return resultado
