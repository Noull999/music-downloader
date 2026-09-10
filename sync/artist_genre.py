"""
Último recurso para resolver el género: preguntarle a SoundCloud por el
ARTISTA REAL del track.

El caso que resuelve: un sello sube un track sin `genre` ni `tag_list`
(pasa, y entonces no hay nada que clasificar). Pero el artista real suele
estar en el título — "Vlace & KSN | Hurt You" subido por Kobosil — y ese
artista sí etiqueta su propia música. Preguntando por él se recupera el
dato en vez de mandar el tema a "Sin género".

Medido sobre 97 tracks reales sin tags de la biblioteca: 40 (41%) se
resuelven con consenso alto. Los dos casos de Kobosil dieron Schranz,
que es donde el usuario los había puesto a mano.

Se usa SOLO cuando `genre_utils.resolve_genre` no encontró nada: nunca
pisa un género que ya existe, igual que el criterio de AcoustID.
"""
import logging
import re
from typing import Callable, Optional

from sync import genre_utils

logger = logging.getLogger(__name__)

# Mayoría absoluta: el ganador tiene que ser al menos la mitad de los votos.
# Por debajo de eso es un empate disfrazado y conviene "Sin género" antes que
# una carpeta equivocada, que después hay que deshacer a mano.
# Calibrado sobre los 97 tracks sin tags de la biblioteca real: con 0.5 se
# clasifica el 46%, con 0.6 el 41%, y de 0.7 para arriba cae al 19%.
MIN_CONSENSO = 0.5
MIN_VOTOS = 3

# Nombres demasiado cortos o genéricos traen a cualquiera en la búsqueda.
_LARGO_MIN = 3
_LARGO_MAX = 30


def artistas_del_titulo(title: Optional[str]) -> list[str]:
    """
    Extrae los nombres de artista de un título.

    La parte antes del primer separador ("|", "-") es por convención el
    artista; lo de después es el nombre del tema. Se parten además las
    colaboraciones ("Vlace & KSN" -> ["Vlace", "KSN"]).
    """
    if not title:
        return []
    # Quitar (Free DL), [Label], etc: no son parte del nombre del artista.
    base = re.sub(r"\s*[\(\[].*?[\)\]]\s*", " ", title)
    cabeza = re.split(r"[|\-–—]", base)[0].strip()
    partes = re.split(r"\s*(?:&|,|\bx\b|\bX\b|\bfeat\.?\b|\bft\.?\b|\bvs\.?\b)\s*", cabeza)
    return [p.strip() for p in partes if _LARGO_MIN <= len(p.strip()) <= _LARGO_MAX][:2]


def elegir_por_votos(generos: list[str]) -> Optional[str]:
    """
    Género ganador entre los de los tracks del artista, o None si la
    evidencia es floja (pocos tracks, o repartida entre varios géneros).
    """
    if len(generos) < MIN_VOTOS:
        return None
    conteo: dict[str, int] = {}
    for g in generos:
        conteo[g] = conteo.get(g, 0) + 1
    ganador, votos = max(conteo.items(), key=lambda x: x[1])
    if votos / len(generos) < MIN_CONSENSO:
        return None
    return ganador


class ArtistGenreResolver:
    """
    Resuelve el género consultando los tracks del artista en SoundCloud.

    `buscar_tracks` recibe un nombre y devuelve la lista de tracks crudos
    de la API. Se inyecta para poder testear sin red.
    """

    def __init__(self, buscar_tracks: Callable[[str], list[dict]]):
        self._buscar = buscar_tracks
        # Varios tracks comparten artista: sin caché se repite la misma
        # búsqueda una vez por track.
        self._cache: dict[str, list[str]] = {}

    def _generos_de(self, artista: str) -> list[str]:
        if artista in self._cache:
            return self._cache[artista]
        try:
            tracks = self._buscar(artista)
        except Exception:
            logger.exception("Error buscando tracks de %s en SoundCloud", artista)
            tracks = []
        generos = []
        for t in tracks:
            # Solo cuentan los tracks que ese artista subió: la búsqueda
            # trae también remixes ajenos que lo mencionan en el título.
            usuario = (t.get("user") or {}).get("username", "")
            if artista.lower() not in usuario.lower():
                continue
            g = genre_utils.resolve_genre(t.get("genre") or "", t.get("tag_list") or "", None)
            if g:
                generos.append(g)
        self._cache[artista] = generos
        return generos

    def resolver(self, title: Optional[str]) -> Optional[str]:
        """Género del track según los tags del artista, o None."""
        votos: list[str] = []
        for artista in artistas_del_titulo(title):
            votos.extend(self._generos_de(artista))
        elegido = elegir_por_votos(votos)
        if elegido:
            logger.info("Género por artista para %r: %s", title, elegido)
        return elegido
