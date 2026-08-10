"""
Normalización de géneros musicales.

El "género" que traen las plataformas es texto libre del uploader, así que
la misma cosa aparece escrita de mil formas ("Hard Techno", "hardtechno",
"HARD TECHNO"...). Este módulo colapsa esas variantes a un nombre canónico
único, usable como nombre de subcarpeta y como tag de género del archivo.
"""
import os
import re

# Alias → nombre canónico. La clave es la forma "colapsada": minúsculas y
# sin espacios/guiones/símbolos (ver _collapse). Agregar aliases acá cuando
# aparezcan grafías nuevas.
_CANONICAL: dict[str, str] = {
    # Techno y familia
    "techno": "Techno",
    "hardtechno": "Hard Techno",
    "harttechno": "Hard Techno",
    "schranz": "Schranz",
    "acidtechno": "Acid Techno",
    "industrialtechno": "Industrial Techno",
    "melodictechno": "Melodic Techno",
    "peaktimetechno": "Peak Time Techno",
    "hypnotictechno": "Hypnotic Techno",
    "darktechno": "Dark Techno",
    "minimaltechno": "Minimal Techno",
    "detroittechno": "Detroit Techno",
    # Hardcore / hard dance
    "hardcore": "Hardcore",
    "uptempo": "Uptempo",
    "uptempohardcore": "Uptempo",
    "frenchcore": "Frenchcore",
    "hardstyle": "Hardstyle",
    "rawstyle": "Rawstyle",
    "gabber": "Gabber",
    # DnB
    "drumbass": "Drum & Bass",
    "drumandbass": "Drum & Bass",
    "drumnbass": "Drum & Bass",
    "dnb": "Drum & Bass",
    "neurofunk": "Neurofunk",
    "jungle": "Jungle",
    # House y familia
    "house": "House",
    "techhouse": "Tech House",
    "deephouse": "Deep House",
    "progressivehouse": "Progressive House",
    "bassline": "Bassline",
    "bass": "Bass",
    "basshouse": "Bass House",
    # Otros electrónicos
    "electronic": "Electronic",
    "electronica": "Electronic",
    "danceedm": "Dance & EDM",
    "edm": "Dance & EDM",
    "dance": "Dance & EDM",
    "trance": "Trance",
    "psytrance": "Psytrance",
    "dubstep": "Dubstep",
    "riddim": "Dubstep",
    "trap": "Trap",
    "phonk": "Phonk",
    "ambient": "Ambient",
    "downtempo": "Downtempo",
    "breakbeat": "Breakbeat",
    "breaks": "Breakbeat",
    "garage": "UK Garage",
    "ukgarage": "UK Garage",
    "eurodance": "Eurodance",
    "hardgroove": "Hardgroove",
    "guaracha": "Guaracha",
    "aleteo": "Guaracha",
    "zapateo": "Guaracha",
    "groovetechno": "Groove Techno",
}

# Nombre de carpeta para lo que no se pudo clasificar en ningún género —
# se reutiliza como "cajón" en vez de crear una carpeta nueva.
UNCLASSIFIED_FOLDER = "musik"


def _collapse(raw: str) -> str:
    """Colapsa un género a su clave de comparación: minúsculas, solo letras/números."""
    return re.sub(r"[^a-z0-9]+", "", raw.lower())


# SoundCloud tag_list: space-separated, multi-word tags wrapped in quotes.
# Ej: '"hard techno" schranz rave "under ground"' -> ['hard techno', 'schranz', ...]
_TAG_RE = re.compile(r'"([^"]+)"|(\S+)')


def parse_tag_list(tag_list: str | None) -> list[str]:
    """Parsea el tag_list crudo de SoundCloud a una lista de tags."""
    if not tag_list:
        return []
    tags = []
    for quoted, bare in _TAG_RE.findall(tag_list):
        tag = (quoted or bare).strip()
        if tag:
            tags.append(tag)
    return tags


def resolve_genre(genre: str | None, tags: list[str] | None = None) -> str:
    """
    Elige el mejor género disponible entre el campo `genre` (texto libre del
    uploader, poco confiable) y una lista de `tags` (más granular, pero
    ruidosa: puede traer cualquier cosa, no solo géneros).

    Prioridad:
      1. Un tag que matchee un subgénero CONOCIDO (nuestro mapa canónico) —
         es más específico que el género genérico ("Techno") y confiable
         porque lo reconocemos explícitamente, no es ruido al azar.
      2. El campo `genre`, normalizado.
      3. El primer tag, como último recurso (puede no ser un género real).
      4. "" si no hay nada.
    """
    for tag in (tags or []):
        key = _collapse(tag)
        if key in _CANONICAL:
            return _CANONICAL[key]

    if genre:
        return normalize_genre(genre)

    if tags:
        return normalize_genre(tags[0])

    return ""


def normalize_genre(raw: str | None) -> str:
    """
    Devuelve el nombre canónico del género, o "" si viene vacío.

    "hard techno" / "HardTechno" / "HARD-TECHNO" → "Hard Techno"
    Géneros desconocidos se devuelven limpios en Title Case, así carpetas y
    tags quedan consistentes aunque no estén en el mapa.
    """
    if not raw:
        return ""
    cleaned = " ".join(raw.split()).strip()
    if not cleaned:
        return ""

    key = _collapse(cleaned)
    if not key:
        return ""
    if key in _CANONICAL:
        return _CANONICAL[key]

    # Desconocido: Title Case conservando separadores razonables
    return cleaned.title()


def is_recognized_genre(genre: str | None) -> bool:
    """
    True si `genre` corresponde a un género real que reconocemos (nuestro
    mapa canónico), no texto libre sin sentido que puso el uploader (ej.
    el nombre de su sello o su propio usuario en el campo "género").

    Se usa para decidir si vale la pena crear una carpeta nueva con ese
    nombre, o si es más seguro mandarlo al cajón de sin-clasificar.
    """
    if not genre:
        return False
    return _collapse(genre) in _CANONICAL


def find_existing_genre_folder(dest_folder: str, genre: str) -> str | None:
    """
    Busca una subcarpeta de `dest_folder` que ya represente `genre`, sin
    importar mayúsculas/minúsculas, y devuelve su nombre EXACTO tal cual
    está en disco.

    Sin esto, si el usuario ya tiene una carpeta "PSYTRANCE" armada a mano
    y el normalizador produce "Psytrance", la app crearía una carpeta
    duplicada al lado en vez de usar la que ya existe.
    """
    if not genre or not os.path.isdir(dest_folder):
        return None
    target = _collapse(genre)
    try:
        for entry in os.listdir(dest_folder):
            if os.path.isdir(os.path.join(dest_folder, entry)) and _collapse(entry) == target:
                return entry
    except OSError:
        pass
    return None
