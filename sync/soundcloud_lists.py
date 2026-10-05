"""
Listas de SoundCloud para la ventana "elegir temas": los parecidos a un tema,
una lista (set) y los temas de un artista. Es el equivalente de lo que ya
hace el handler de YouTube con sus listas y su radio de parecidos.

Todo sale de la API interna con las credenciales que la app ya usa para la
sync. Se convierte al mismo TrackMetadata que usa YouTube, asi que la ventana,
la cola y la descarga no distinguen de donde vino cada tema.

Medido: ~50 parecidos en 0.8 s, una lista de 134 temas en ~1.2 s, 50 temas de
un perfil en ~2.5 s.
"""
import logging
from typing import Optional
from urllib.parse import urlparse

from handlers.base_handler import TrackMetadata

logger = logging.getLogger(__name__)

PREFIJO_PARECIDOS = "sc-related:"
LIMITE_PARECIDOS = 50
LIMITE_PERFIL = 200
_LOTE_IDS = 50   # la API acepta pocos ids por pedido


def es_parecidos(ref: str) -> bool:
    return (ref or "").startswith(PREFIJO_PARECIDOS)


def es_url_de_lista(url: str) -> bool:
    """
    True si el link de SoundCloud es una lista de temas y no un tema suelto:
    un perfil (soundcloud.com/artista), sus temas (/tracks, /popular-tracks) o
    un set (/artista/sets/nombre).
    """
    try:
        p = urlparse((url or "").strip())
    except Exception:
        return False
    if p.netloc.lower().replace("www.", "") != "soundcloud.com":
        return False
    partes = [x for x in p.path.split("/") if x]
    if len(partes) == 1:
        return partes[0] not in ("discover", "stream", "you", "upload", "search")
    if len(partes) == 2:
        return partes[1] in ("tracks", "popular-tracks")
    return len(partes) >= 3 and partes[1] == "sets"


def a_metadata(t: dict) -> Optional[TrackMetadata]:
    """Un track crudo de la API de SoundCloud -> TrackMetadata."""
    url = t.get("permalink_url")
    if not url or not t.get("title"):
        return None
    return TrackMetadata(
        url=url,
        title=t["title"],
        artist=(t.get("user") or {}).get("username") or "",
        duration=int((t.get("duration") or 0) / 1000),
        thumbnail_url=t.get("artwork_url") or "",
        platform="SoundCloud",
        track_id=str(t.get("id") or ""),
        genre=t.get("genre") or "",
        tags=t.get("tag_list") or "",
    )


def _convertir(crudos: list[dict]) -> list[TrackMetadata]:
    return [m for m in (a_metadata(t) for t in crudos) if m]


def _completar_ids(cli, tracks: list[dict]) -> list[dict]:
    """
    Una lista de la API trae completos solo los primeros temas; del resto
    manda apenas el id. Se piden los que faltan por lotes, respetando el orden.
    """
    faltan = [t["id"] for t in tracks if not t.get("title") and t.get("id")]
    completos = {}
    for i in range(0, len(faltan), _LOTE_IDS):
        lote = faltan[i:i + _LOTE_IDS]
        for t in cli.get_tracks_by_ids(lote):
            completos[t["id"]] = t
    return [completos.get(t.get("id"), t) if not t.get("title") else t for t in tracks]


def obtener(cli, ref: str) -> list[TrackMetadata]:
    """
    Los temas de `ref`, que puede ser "sc-related:<id>" (parecidos a ese tema)
    o la URL de un set o de un perfil. Lanza RuntimeError con un mensaje
    legible si no se puede.
    """
    if es_parecidos(ref):
        track_id = ref[len(PREFIJO_PARECIDOS):]
        return _convertir(cli.get_related(track_id, LIMITE_PARECIDOS))

    objeto = cli.resolve(ref)
    if not objeto:
        raise RuntimeError("SoundCloud no encontró esa lista.")
    tipo = objeto.get("kind")
    if tipo == "playlist":
        return _convertir(_completar_ids(cli, objeto.get("tracks") or []))
    if tipo == "user":
        return _convertir(cli.get_user_tracks(objeto["id"], LIMITE_PERFIL))
    raise RuntimeError("Ese link no es una lista de SoundCloud.")
