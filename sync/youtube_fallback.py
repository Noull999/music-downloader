"""
Respaldo para canciones que SoundCloud no deja bajar: buscarlas en YouTube.

Qué resuelve: SoundCloud sirve cifradas (DRM) las canciones de catálogo de
sello y las Go+, y a otras las bloquea por país. yt-dlp no puede con eso, y
la canción quedaba como fallida para siempre. Pero casi siempre existe en
YouTube, y en los canales automáticos "Artista - Topic" es el MISMO master
del distribuidor.

Medido sobre las 7 fallidas reales de la biblioteca: 6 se recuperan con la
versión correcta. La séptima (Nico Parga - Veneno de Serpiente) no estaba, y
lo correcto era no bajar nada: los candidatos eran remixes de otros.

Es una heurística, no una prueba: para una canción con DRM no hay audio de
referencia con el que comparar huellas. Por eso las reglas son estrictas y,
ante la duda, no se baja nada (la canción queda como fallida, igual que antes).

El título solo no alcanza: "Piquepra (Yago Fuerte Remix)" puntuaba 100% de
título contra "Piquepra" pero duraba 32 s de diferencia. Y la duración sola
tampoco: una versión "Instrumental" de otro canal duraba exacto lo mismo que
el original. Hacen falta las tres cosas: título, duración y que no cambie la
versión.
"""
import logging
import re
from typing import Callable, Optional

from sync import match_utils
from utils import js_runtime

logger = logging.getLogger(__name__)

# Segundos de diferencia aceptados con la duración que informa SoundCloud.
# Los canales Topic coinciden a ±1 s; más que esto ya es otra edición.
TOLERANCIA_DURACION = 3
UMBRAL_TITULO = 80
RESULTADOS_A_REVISAR = 8

# Palabras que cambian el audio. Si el candidato las trae y el título original
# no, es otra versión y se descarta.
_VARIANTES = (
    "instrumental", "acapella", "a cappella", "slowed", "reverb", "sped up",
    "speed up", "nightcore", "8d", "karaoke", "cover", "live", "remix",
    "edit", "bootleg", "mashup", "vip", "rework", "flip", "stems", "loop",
)


def _norm(texto: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s]", " ", (texto or "").lower())).strip()


def _variantes_de(titulo: str) -> set[str]:
    t = f" {_norm(titulo)} "
    return {v for v in _VARIANTES if f" {v} " in t}


def _es_canal_confiable(canal: str, artista: str) -> bool:
    """Canal automático "Artista - Topic", o el propio canal del artista."""
    c = _norm(canal)
    if c.endswith(" topic"):
        return True
    a = _norm(artista)
    return bool(a) and len(a) >= 3 and (a in c or c in a)


def _puntaje_titulo(artista: str, titulo_sc: str, canal: str, titulo_yt: str) -> int:
    original = match_utils.like_candidates(artista, titulo_sc)
    return max(
        match_utils.best_score(original, match_utils.like_candidates(canal, titulo_yt)),
        match_utils.best_score(original, match_utils.file_candidates(titulo_yt)),
    )


def elegir_candidato(
    candidatos: list[dict], artista: str, titulo: str, duracion_s: float
) -> Optional[dict]:
    """
    El mejor candidato de YouTube, o None si ninguno es confiable.

    Sin duración de referencia no se intenta: sería adivinar.
    """
    if not duracion_s or duracion_s <= 0:
        return None

    variantes_originales = _variantes_de(titulo)
    validos = []
    for c in candidatos:
        titulo_yt = c.get("title") or ""
        duracion_yt = c.get("duration") or 0
        canal = c.get("channel") or c.get("uploader") or ""
        if not titulo_yt or not duracion_yt:
            continue
        dif = abs(duracion_yt - duracion_s)
        if dif > TOLERANCIA_DURACION:
            continue
        if _variantes_de(titulo_yt) - variantes_originales:
            continue
        puntaje = _puntaje_titulo(artista, titulo, canal, titulo_yt)
        if puntaje < UMBRAL_TITULO:
            continue
        validos.append((
            _es_canal_confiable(canal, artista), puntaje, -dif, c,
        ))

    if not validos:
        return None
    # Canal confiable primero; después el mejor título; después la duración
    # más cercana.
    validos.sort(key=lambda v: v[:3], reverse=True)
    return validos[0][3]


def buscar_en_youtube(query: str) -> list[dict]:
    """Resultados crudos de la búsqueda de YouTube (sin descargar nada)."""
    import yt_dlp

    opts = {"quiet": True, "no_warnings": True, "extract_flat": True,
            "skip_download": True}
    with yt_dlp.YoutubeDL(js_runtime.aplicar(opts)) as ydl:
        info = ydl.extract_info(f"ytsearch{RESULTADOS_A_REVISAR}:{query}", download=False)
    resultados = []
    for r in (info or {}).get("entries") or []:
        if not r:
            continue
        url = r.get("url") or (
            f"https://www.youtube.com/watch?v={r['id']}" if r.get("id") else ""
        )
        if url:
            resultados.append({**r, "url": url})
    return resultados


def encontrar(
    artista: str,
    titulo: str,
    duracion_s: float,
    buscar: Callable[[str], list[dict]] = buscar_en_youtube,
) -> Optional[dict]:
    """Busca la canción en YouTube y devuelve el candidato confiable, si hay."""
    try:
        candidatos = buscar(f"{artista} {titulo}".strip())
    except Exception:
        logger.exception("Error buscando %s - %s en YouTube", artista, titulo)
        return None
    elegido = elegir_candidato(candidatos, artista, titulo, duracion_s)
    if elegido:
        logger.info("Respaldo YouTube para %s - %s: %s (%s)", artista, titulo,
                    elegido.get("title"), elegido.get("channel") or elegido.get("uploader"))
    else:
        logger.info("Sin candidato confiable en YouTube para %s - %s", artista, titulo)
    return elegido
