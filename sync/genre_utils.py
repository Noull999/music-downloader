"""
Resolución de subgénero a partir de los metadatos de SoundCloud.

El problema que resuelve: el campo `genre` de SoundCloud lo elige el uploader
de una lista corta y tira a lo genérico. Medido sobre una biblioteca real de
402 likes, 137 (34%) tenían `genre` genérico o vacío mientras el subgénero
real estaba en `tag_list`, un campo que la app ignoraba por completo:

    "Santigold - Disparate Youth (BRXTEK Schranz Edit)"
        genre = "Techno"
        tags  = schranz, hardtechno, schranz edit, melodic schranz

"schranz" aparecía 57 veces en los tags contra 14 en el campo genre: usando
solo `genre` se perdía tres cuartas partes de la información.

La estrategia es simple y sin sorpresas: se juntan `genre` + `tag_list`, se
normalizan, y gana el candidato MÁS ESPECÍFICO según SPECIFICITY. Los tags
que no son géneros conocidos ("rave", "remix", "free download", nombres de
artista) se ignoran, así que un tag raro nunca se convierte en carpeta.
"""
import re
import unicodedata
from typing import Iterable, Optional

# Cuanto más alto, más específico: un track etiquetado "techno" + "schranz"
# se resuelve como Schranz. Los valores solo importan entre sí.
SPECIFICITY: dict[str, tuple[str, int]] = {}


def _register(canonical: str, score: int, *aliases: str) -> None:
    """
    Registra un género y todas las formas en que aparece escrito.

    Además de los alias explícitos se registra la variante sin espacios de
    cada uno: en SoundCloud es habitual etiquetar "hardcoretechno" o
    "industrialhardtechno" todo junto, y sin esto esos tags no se
    reconocían y el track caía en "(sin género)".
    """
    for alias in (canonical, *aliases):
        key = _norm(alias)
        SPECIFICITY.setdefault(key, (canonical, score))
        nospace = key.replace(" ", "")
        if nospace != key:
            SPECIFICITY.setdefault(nospace, (canonical, score))


def _norm(text: str) -> str:
    """Minúsculas, sin acentos, sin signos, espacios colapsados."""
    text = unicodedata.normalize("NFKD", text or "")
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = re.sub(r"[^\w\s&]+", " ", text.lower())
    return re.sub(r"\s+", " ", text).strip()


# ── Vocabulario ──────────────────────────────────────────────────────── #
# Subgéneros específicos (ganan sobre los amplios)
_register("Schranz", 100, "schranz techno", "melodic schranz", "schranz edit")
_register("Frenchcore", 95, "french core")
_register("Uptempo Hardcore", 95, "uptempo", "uptempo hardcore")
_register("Industrial Hardcore", 95, "industrial hardcore")
_register("Hardgroove", 90, "hard groove", "hardgroove techno", "groove techno")
_register("Industrial Techno", 90, "industrial hard techno", "industrial raw", "industrial")
_register("Guaracha", 90, "aleteo", "zapateo", "guaracha aleteo", "uwuaracha", "waracha")
_register("Acid Techno", 85, "acid")
_register("Hardcore Techno", 85, "hardcore techno")
_register("Rawstyle", 85, "raw style", "rawphoric")
_register("Latin Core", 85, "latincore", "latin tek", "latin bass", "latin club")
_register("Hardstyle", 80, "hard style")
_register("Hard Techno", 70, "hardtechno", "hard tehno", "ht")
_register("Tech House", 70, "techhouse")
_register("Drum & Bass", 70, "drum and bass", "dnb", "d&b", "drum n bass")
_register("Hardcore", 60, "hard core")
_register("Hard Dance", 60, "harddance", "hard er style", "hard dance")
_register("Trance", 60, "psytrance", "hardtrance", "hard trance")
_register("Dubstep", 60, "riddim")
_register("Bass", 45, "bass music")
# Géneros amplios (solo ganan si no hay nada más específico)
_register("Techno", 30)
_register("House", 30, "tribal house")
_register("Latin", 25, "reggaeton", "moombahton")
_register("Electronic", 10, "electronica", "dance & edm", "dance edm", "edm", "dance")


# Palabras que los uploaders ponen en el campo `genre` pero no son géneros.
# Sin esto terminan como carpeta ("Premiere/", "Free Download/").
_NO_ES_GENERO = {
    "premiere", "free download", "free dl", "freedl", "edit", "remix",
    "original mix", "extended mix", "dj", "mix", "set", "bootleg",
    "out now", "preview", "master", "wip", "other", "n a", "na", "none",
    # Categorías de YouTube: vienen en el tag de género de archivos bajados
    # de ahí y no dicen nada del estilo musical.
    "music", "musica", "entertainment", "people & blogs", "people blogs",
    "film & animation", "gaming", "education", "news & politics", "comedy",
    "howto & style", "sports", "travel & events", "science & technology",
    "autos & vehicles", "pets & animals", "nonprofits & activism", "shows",
    "trailers", "short movies", "unknown", "varios", "misc",
}


def _parece_basura(texto: str) -> bool:
    """
    Detecta valores que no son un género aunque estén en el campo género:
    volcados de tags ("Charli Xcx, Von Dutch, Brat, Remix"), hashtags
    ("#Psybass #Hardtechno") o nombres de sello con corchetes. Sin esto
    cada uno de estos genera su propia carpeta.
    """
    t = (texto or "").strip()
    if len(t) > 28:
        return True
    if "#" in t or "[" in t or "]" in t:
        return True
    if t.count(",") >= 2:
        return True
    return False


def split_tags(tag_list) -> list[str]:
    """
    Parte el `tag_list` de SoundCloud. Es un formato con dos convenciones
    mezcladas en la misma biblioteca: separado por espacios con comillas
    para los tags de varias palabras ('rave "hard techno"'), y a veces
    separado por comas ('hardcore,techno,industrial hardcore').
    """
    if not tag_list:
        return []
    if isinstance(tag_list, (list, tuple)):
        raw = list(tag_list)
    else:
        raw = [t.strip('"') for t in re.findall(r'"[^"]*"|[^\s]+', str(tag_list))]
    out: list[str] = []
    for chunk in raw:
        out.extend(part for part in str(chunk).split(",") if part.strip())
    return [t.strip().strip('"').strip() for t in out if t.strip().strip('"').strip()]


# Géneros que se pueden buscar dentro del TÍTULO sin arriesgar falsos
# positivos, porque como palabra son inequívocos. Quedan afuera a propósito
# los que son palabras comunes en nombres de tema ("acid" en "Acid Drop",
# "bass", "industrial", "rave", "techno"), que clasificarían mal.
_TITULO_SEGURO = (
    "schranz", "hardgroove", "hard groove", "frenchcore", "guaracha",
    "hardtechno", "hard techno", "uptempo", "rawstyle", "hardstyle",
    "industrial hardcore", "hardcore techno", "aleteo", "zapateo",
)


def _from_title(title: Optional[str]) -> Optional[tuple[str, int]]:
    """Busca un género inequívoco dentro del título, como palabra completa."""
    if not title:
        return None
    t = _norm(title)
    best: Optional[tuple[str, int]] = None
    for alias in _TITULO_SEGURO:
        if re.search(rf"(?<!\w){re.escape(_norm(alias))}(?!\w)", t):
            hit = SPECIFICITY.get(_norm(alias))
            if hit and (best is None or hit[1] > best[1]):
                best = hit
    return best


def resolve_genre(genre: Optional[str], tag_list=None, title: Optional[str] = None) -> Optional[str]:
    """
    Devuelve el subgénero más específico entre `genre` y `tag_list`, en su
    forma canónica ("Hard Techno", no "HARDTECHNO"/"hard techno"/"Hardtechno").

    Si ningún candidato está en el vocabulario, cae al `genre` original
    limpiado — mejor conservar lo que puso el uploader que perder el dato.
    Devuelve None si no hay ninguna información de género.
    """
    candidates: list[str] = []
    if genre and str(genre).strip():
        # "Industrial Techno/Bochka" y "Techno / Hard Techno": cada lado es
        # un candidato, así el conocido gana en vez de crear una carpeta
        # con barra (que además anidaría directorios).
        candidates.extend(p for p in re.split(r"[/|]", str(genre)) if p.strip())
    candidates.extend(split_tags(tag_list))

    best: Optional[tuple[str, int]] = None
    for cand in candidates:
        hit = SPECIFICITY.get(_norm(cand))
        if hit and (best is None or hit[1] > best[1]):
            best = hit

    if best:
        return best[0]

    # Nada en genre/tags: último recurso, el título ("... Schranz Edit").
    from_title = _from_title(title)
    if from_title:
        return from_title[0]

    # Sin coincidencias: conservar el género original, presentable, salvo
    # que sea una palabra que no describe un género.
    if genre and str(genre).strip():
        cleaned = re.sub(r"\s+", " ", str(genre).strip())
        if _norm(cleaned) in _NO_ES_GENERO or _parece_basura(cleaned):
            return None
        return cleaned.title() if cleaned.islower() or cleaned.isupper() else cleaned
    return None


def genre_folder(
    genre: Optional[str],
    tag_list=None,
    title: Optional[str] = None,
    fallback: str = "Sin género",
) -> str:
    """
    Nombre de carpeta para el subgénero resuelto, seguro para el sistema de
    archivos. `fallback` se usa cuando el track no tiene ninguna información.
    """
    resolved = resolve_genre(genre, tag_list, title) or fallback
    safe = re.sub(r'[\\/:*?"<>|]', "_", resolved).strip(". ")
    return safe or fallback
