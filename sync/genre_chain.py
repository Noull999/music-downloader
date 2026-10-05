"""
Cadena para decidir el genero de un tema que NO viene de SoundCloud (por
ejemplo uno bajado de YouTube, que no trae genero ni tags utiles).

Antes todo lo de YouTube caia en "Sin genero": medido sobre 14 temas reales,
la app hoy no clasificaba ninguno. Cada paso de abajo se prueba solo si el
anterior no encontro nada, de mas a menos confiable:

1. Palabras inequivocas del TITULO ("schranz", "hardgroove"...).
2. Tags y hashtags del video en YouTube. Se miran solo contra el vocabulario
   de generos conocido: un tag cualquiera ("music", el nombre del artista)
   nunca se convierte en carpeta.
3. El MISMO TEMA en SoundCloud (mismo titulo, duracion a +-3 s): el uploader
   original suele haberlo etiquetado. De 24 temas de YouTube, 16 existian en
   SoundCloud, aunque 5 sin tags utiles.
4. Voto por ARTISTA (sync/artist_genre.py): los tags de los otros temas del
   mismo artista en SoundCloud. Es lo menos preciso, por eso va ultimo.

Si ninguno encuentra nada devuelve None y el tema va a "Sin genero": mejor
eso que una carpeta equivocada.
"""
import logging
import re
from typing import Callable, Optional

from sync import genre_utils, match_utils
from sync.artist_genre import ArtistGenreResolver

logger = logging.getLogger(__name__)

# Segundos de diferencia aceptados entre la duracion del tema en YouTube y la
# del mismo tema en SoundCloud.
TOLERANCIA_DURACION = 3
UMBRAL_TITULO = 90

_HASHTAG = re.compile(r"#([\w\-]+)", re.UNICODE)


def hashtags(texto: Optional[str]) -> list[str]:
    """Hashtags de una descripcion ('#guaracha #aleteo' -> ['guaracha', 'aleteo'])."""
    return _HASHTAG.findall(texto or "")


class ResolutorDeGenero:
    """
    `buscar_tracks` recibe una consulta y devuelve los tracks crudos de la API
    de busqueda de SoundCloud. Se inyecta para poder testear sin red.
    """

    def __init__(
        self,
        buscar_tracks: Callable[[str], list[dict]],
        aceptar: Optional[Callable[[str], bool]] = None,
    ):
        """
        `aceptar` filtra lo que encuentran los pasos 3 y 4 (los que leen el
        genero que puso OTRA persona en SoundCloud). Sin esto, un genero
        inventado por quien subio el tema ("240 Sound") se volvia una carpeta
        nueva. Si rechaza el resultado de un paso, se sigue con el siguiente.
        """
        self._aceptar = aceptar or (lambda g: True)
        self._buscar = buscar_tracks
        self._por_artista = ArtistGenreResolver(buscar_tracks)
        self._cache_tema: dict[str, Optional[str]] = {}

    # ── paso 3: el mismo tema en SoundCloud ─────────────────────────────── #

    def por_tema_exacto(self, artista: str, titulo: str, duracion_s: float) -> Optional[str]:
        """Genero del mismo tema en SoundCloud, o None si no esta o no tiene tags."""
        if not titulo or not duracion_s:
            return None
        clave = f"{artista}|{titulo}|{int(duracion_s)}"
        if clave in self._cache_tema:
            return self._cache_tema[clave]

        genero = None
        try:
            candidatos = match_utils.like_candidates(artista, titulo)
            for t in self._buscar(f"{artista} {titulo}".strip()):
                titulo_sc = t.get("title") or ""
                usuario = (t.get("user") or {}).get("username", "")
                puntaje = max(
                    match_utils.best_score(candidatos, match_utils.like_candidates(usuario, titulo_sc)),
                    match_utils.best_score(candidatos, match_utils.file_candidates(titulo_sc)),
                )
                if puntaje < UMBRAL_TITULO:
                    continue
                if abs((t.get("duration") or 0) / 1000 - duracion_s) > TOLERANCIA_DURACION:
                    continue
                genero = genre_utils.resolve_genre(t.get("genre") or "", t.get("tag_list") or "", None)
                if genero:
                    break
        except Exception:
            logger.exception("Error buscando %s - %s en SoundCloud", artista, titulo)
        self._cache_tema[clave] = genero
        return genero

    # ── la cadena completa ──────────────────────────────────────────────── #

    def resolver(
        self,
        *,
        genre: Optional[str] = "",
        tags=None,
        title: Optional[str] = "",
        artist: str = "",
        duration_s: float = 0,
        description: str = "",
    ) -> Optional[str]:
        # 1 y 2: lo que ya trae el tema (titulo, genero, tags), sin red.
        local = genre_utils.resolve_genre(genre, tags, title)
        if local:
            return local

        # 2b: hashtags de la descripcion. Son una eleccion deliberada de quien
        # subio el tema, asi que cuentan como tags.
        ht = hashtags(description)
        if ht:
            por_hashtag = genre_utils.resolve_genre("", ht, None)
            if por_hashtag:
                return por_hashtag

        # 3: el mismo tema en SoundCloud.
        exacto = self.por_tema_exacto(artist, title or "", duration_s)
        if exacto and self._aceptar(exacto):
            return exacto

        # 4: voto por artista.
        por_artista = self._por_artista.resolver(f"{artist} - {title}" if artist else title)
        return por_artista if por_artista and self._aceptar(por_artista) else None
