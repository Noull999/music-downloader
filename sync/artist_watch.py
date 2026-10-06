"""
"Nuevos de mis artistas": los temas que subieron, desde la ultima vez que se
miro, los artistas que mas likeas.

Que artistas se vigilan sale de los likes de ahora mismo (los que tienen al
menos MIN_LIKES), asi la lista cambia sola a medida que likeas a otros. Nada
se baja solo: el resultado se muestra en la misma ventana de seleccion que
"Descubrir".

Medido con una cuenta real (460 likes): 328 artistas distintos, 59 con 2 o mas
likes; resolver los likes a artistas tarda ~7 s y pedir los temas recientes de
esos 59 artistas unos pocos segundos mas.
"""
import logging
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from typing import Optional

from sync.soundcloud_lists import a_metadata, _LOTE_IDS

logger = logging.getLogger(__name__)

REF_ARTISTAS = "sc-artists"
MIN_LIKES = 2                # likes de un artista para vigilarlo
MAX_ARTISTAS = 80            # tope, por si la biblioteca crece mucho
TEMAS_POR_ARTISTA = 10       # los mas recientes de cada uno
DIAS_PRIMERA_VEZ = 30        # la primera vez no hay "ultima revision"
DIAS_MAXIMOS = 60            # aunque pase mucho tiempo, no se mira mas atras
MAXIMO_RESULTADOS = 100
HILOS = 8                    # pedidos a la vez a SoundCloud


def calcular_desde(ultima_revision: str, ahora: Optional[datetime] = None) -> datetime:
    """Desde cuando buscar: la ultima revision, sin pasar de DIAS_MAXIMOS atras."""
    ahora = ahora or datetime.now(timezone.utc)
    limite = ahora - timedelta(days=DIAS_MAXIMOS)
    ultima = _fecha(ultima_revision)
    if ultima is None:
        return ahora - timedelta(days=DIAS_PRIMERA_VEZ)
    return max(ultima, limite)


def _fecha(texto) -> Optional[datetime]:
    if not texto:
        return None
    try:
        d = datetime.fromisoformat(str(texto).replace("Z", "+00:00"))
    except ValueError:
        return None
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


def artistas_vigilados(tracks: list[dict], minimo: int = MIN_LIKES,
                       maximo: int = MAX_ARTISTAS) -> list[tuple]:
    """[(id, nombre, likes)] de los artistas con >= `minimo` likes, de mas a menos."""
    cuenta: Counter = Counter()
    nombres: dict = {}
    for t in tracks:
        u = t.get("user") or {}
        if u.get("id"):
            cuenta[u["id"]] += 1
            nombres[u["id"]] = u.get("username") or ""
    ranking = [(uid, nombres[uid], n) for uid, n in cuenta.most_common() if n >= minimo]
    return ranking[:maximo]


def nuevos_de_artistas(cli, like_ids: list, excluir: set, desde: datetime,
                       minimo: int = MIN_LIKES) -> list[tuple]:
    """
    Temas subidos desde `desde` por los artistas vigilados.
    Devuelve [(TrackMetadata, fecha_iso, likes_del_artista)], del mas nuevo al
    mas viejo. `excluir` son URLs que no tiene sentido sugerir (likes y lo ya
    descargado).
    """
    lotes = [like_ids[i:i + _LOTE_IDS] for i in range(0, len(like_ids), _LOTE_IDS)]
    with ThreadPoolExecutor(max_workers=HILOS) as pool:
        tracks = [t for lote in pool.map(cli.get_tracks_by_ids, lotes) for t in lote]
    artistas = artistas_vigilados(tracks, minimo)
    if not artistas:
        return []

    def recientes(a):
        try:
            return cli.get_user_tracks(a[0], TEMAS_POR_ARTISTA)
        except Exception:
            logger.warning("No se pudieron leer los temas de %s", a[1], exc_info=True)
            return []

    with ThreadPoolExecutor(max_workers=HILOS) as pool:
        listas = list(pool.map(recientes, artistas))

    vistos: set = set()
    resultado = []
    for (uid, _nombre, likes), lista in zip(artistas, listas):
        for crudo in lista:
            fecha = _fecha(crudo.get("display_date") or crudo.get("created_at"))
            if fecha is None or fecha < desde:
                continue
            meta = a_metadata(crudo)
            if meta is None or meta.url in excluir or meta.url in vistos:
                continue
            vistos.add(meta.url)
            resultado.append((meta, fecha.isoformat(), likes))
    resultado.sort(key=lambda r: r[1], reverse=True)
    return resultado[:MAXIMO_RESULTADOS]
