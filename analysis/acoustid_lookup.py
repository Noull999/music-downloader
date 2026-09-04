"""
Completa título y artista de archivos con tags vacíos/rotos, identificando
la canción por su huella de audio contra el servicio web de AcoustID
(gratuito, requiere una API key personal: https://acoustid.org/api-key).

No toca género: eso necesitaría una segunda consulta a MusicBrainz por
canción (los tags de AcoustID no traen género), y queda fuera de esta
primera versión. Solo llena título/artista cuando el archivo no los tiene,
y nunca pisa un tag que ya existe: si algo está mal pero no vacío, esto no
lo toca (evita reemplazar un tag bueno por un match dudoso).
"""
import logging
from pathlib import Path
from typing import Optional

from analysis.fingerprint import fingerprint_comprimida

logger = logging.getLogger(__name__)

# Un match por debajo de esto es más probable que sea ruido que la canción
# real: AcoustID puntúa 0-1 según qué tan bien coincide el audio.
SCORE_MINIMO = 0.5


def identificar(path: str, api_key: str) -> Optional[dict]:
    """
    Returns: {"title": ..., "artist": ..., "score": float} o None si no
    hay match confiable, no hay key configurada, o falla la consulta (sin
    conexión, servicio caído, etc. — nunca levanta excepción hacia arriba).
    """
    if not api_key:
        return None

    huella = fingerprint_comprimida(path)
    if not huella:
        return None
    duracion, fp = huella

    try:
        import acoustid
        respuesta = acoustid.lookup(api_key, fp, duracion, meta=["recordings"])
    except Exception:
        logger.exception("Error consultando AcoustID para %s", path)
        return None

    if respuesta.get("status") != "ok":
        logger.warning("AcoustID respondió error para %s: %s", path, respuesta.get("error"))
        return None

    resultados = respuesta.get("results") or []
    if not resultados:
        return None

    mejor = max(resultados, key=lambda r: r.get("score", 0))
    if mejor.get("score", 0) < SCORE_MINIMO:
        return None

    grabaciones = mejor.get("recordings") or []
    if not grabaciones:
        return None
    grabacion = grabaciones[0]

    title = grabacion.get("title")
    artistas = grabacion.get("artists") or []
    artist = ", ".join(a.get("name", "") for a in artistas if a.get("name")) or None

    if not title and not artist:
        return None

    return {"title": title, "artist": artist, "score": mejor["score"]}


def aplicar_tags(path: str, resultado: dict) -> bool:
    """
    Escribe título/artista SOLO en los campos que están vacíos. Nunca pisa
    un tag existente, aunque sea distinto al que devolvió AcoustID.
    """
    try:
        from mutagen import File as MFile
        audio = MFile(path, easy=True)
        if audio is None:
            return False

        cambios = {}
        if resultado.get("title") and not (audio.get("title") or [""])[0].strip():
            cambios["title"] = resultado["title"]
        if resultado.get("artist") and not (audio.get("artist") or [""])[0].strip():
            cambios["artist"] = resultado["artist"]

        if not cambios:
            return False

        for campo, valor in cambios.items():
            audio[campo] = valor
        audio.save()
        return True
    except Exception:
        logger.exception("No se pudo escribir tags en %s", path)
        return False


def archivos_con_tags_vacios(carpetas: list[str]) -> list[Path]:
    """
    Busca archivos sin título o sin artista en las carpetas dadas.
    """
    from sync import match_utils

    faltantes = []
    for path, _ in match_utils.index_audio_files(carpetas):
        try:
            from mutagen import File as MFile
            audio = MFile(path, easy=True)
        except Exception:
            audio = None
        if audio is None:
            continue
        title = (audio.get("title") or [""])[0].strip()
        artist = (audio.get("artist") or [""])[0].strip()
        if not title or not artist:
            faltantes.append(path)
    return faltantes
