"""
Normalización y comparación difusa de títulos de canciones.

Módulo compartido entre el detector de duplicados (sync/duplicate_checker.py)
y la reconciliación de biblioteca (webview_app/api.py), que antes tenían dos
implementaciones distintas y daban resultados distintos para el mismo par
de canciones.

El problema que resuelve, específico de SoundCloud:

1. El campo "artista" de un like es el UPLOADER (sello o canal, p.ej.
   "GEWOONRAVES", "art.1.43"), no el artista real, que vive dentro del
   título. Los archivos en disco están nombrados "ArtistaReal - Título",
   así que comparar "uploader + título" contra el nombre de archivo mete
   ruido en cada comparación. Por eso se compara también contra el título
   solo.

2. El ruido de promo y versionado ("[FREE DL]", "(Original Mix)", "MASTER",
   "v3.2") aparece en ambos lados e infla la similitud entre canciones sin
   relación. Quitarlo sube el score de las coincidencias reales y baja el
   de las falsas: "No Good" vs "Raise The Roof" cae de 81 a 78, mientras
   que "D|K|OXY - Rage Machine (FREE DL)" vs "DKOXY - Rage Machine.wav"
   sube de 84 a más de 90.
"""
import logging
import re
import unicodedata
from pathlib import Path
from typing import Iterable, Optional

from thefuzz import fuzz

logger = logging.getLogger(__name__)

AUDIO_EXTENSIONS = {".mp3", ".m4a", ".flac", ".wav", ".ogg", ".opus", ".aac",
                    ".aiff", ".aif"}


def es_basura_del_sistema(path: Path) -> bool:
    """
    Archivos que NO son música aunque tengan extensión de audio.

    macOS deja un "._NombreCancion.mp3" (AppleDouble, unos pocos KB con
    metadatos) junto a cada archivo al copiar a un disco no-Mac, más los
    .DS_Store de Finder. Como copian la extensión, se indexaban como
    canciones reales: en una biblioteca de prueba había 613 de estos
    falsos sobre 2036 archivos, y ensuciaban tanto la detección de
    duplicados como el conteo y las huellas de audio.
    """
    name = path.name
    return name.startswith("._") or name == ".DS_Store"

# Umbral por defecto para considerar dos títulos la misma canción.
# Elegido midiendo contra una biblioteca real de 1904 archivos y 392 likes:
# en >=80 no aparecieron falsos positivos; entre 72 y 79 sí (p.ej. "Barbie
# Girl" coincidiendo con "Girl In Red"). Aplica a cadenas YA limpiadas por
# clean_for_match(), así que no es comparable con umbrales de otras épocas.
MATCH_THRESHOLD = 80

# Cadenas más cortas que esto no aportan señal suficiente para comparar.
MIN_MATCH_LEN = 4

_NOISE = re.compile(
    r"\b(free\s*(dl|download)|full\s*length|out\s*now|premiere|preview|"
    r"extended(\s*(mix|version))?|original\s*mix|radio\s*edit|"
    r"master(ed|ing)?|mstr|final|v\d+(\.\d+)?|hq|clip|temporary)\b",
    re.I,
)
_BRACKETS = re.compile(r"[\[\(\{][^\]\)\}]*[\]\)\}]")


def clean_for_match(text: str) -> str:
    """
    Normaliza un título para comparación difusa: quita bloques entre
    corchetes/paréntesis, ruido de promo/versionado, tildes y signos, y
    colapsa espacios.
    """
    if not text:
        return ""
    t = _BRACKETS.sub(" ", text)
    t = _NOISE.sub(" ", t)
    t = unicodedata.normalize("NFD", t)
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    t = re.sub(r"[^\w\s]", " ", t.lower())
    return " ".join(t.split())


def _usable(candidates: Iterable[str]) -> set[str]:
    return {c for c in candidates if len(c) >= MIN_MATCH_LEN}


# Palabras que van entre parentesis pero no son el nombre de quien hizo la
# version: sin esto "(Free Download)" se tomaria por un remixer.
_NO_ES_REMIXER = frozenset({
    "remix", "edit", "bootleg", "free", "download", "dl", "extended", "original", "mix", "hard",
    "techno", "schranz", "rework", "flip", "vip", "version", "remaster", "remastered", "master",
    "mastered", "premiere", "out", "now", "feat", "the", "and", "dub", "radio", "club",
    "hardtechno", "hardstyle", "hardcore", "tek", "mashup", "rave", "kick", "new", "intro",
    "temporary", "limited", "time", "only", "full", "track", "official", "video", "audio",
    "preview", "clip", "promo", "exclusive", "soundcloud", "bandcamp", "buy", "link", "bio",
})


def _solo_alfanumerico(texto: str) -> str:
    t = unicodedata.normalize("NFD", texto or "")
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    return re.sub(r"[^a-z0-9 ]+", " ", t.lower())


def tokens_de_remixer(titulo: str) -> frozenset:
    """
    Nombres propios dentro de los PARENTESIS de un titulo: quien hizo la
    version ("(SX2 Remix)" -> {"sx2"}).

    clean_for_match borra todo lo que va entre parentesis, y ahi esta justo el
    remixer: "Faithless - Insomnia (SX2 Remix)" e "Insomnia - Faithless
    (Restricted & NIK)" quedaban IDENTICOS y la sync daba el segundo por el
    primero. No se miran los corchetes: ahi van sellos y codigos ([FREE DL],
    [TFT046]), no remixers.
    """
    toks: set[str] = set()
    for grupo in re.findall(r"\(([^)]*)\)", titulo or ""):
        toks |= {w for w in _solo_alfanumerico(grupo).split()
                 if len(w) >= 3 and w not in _NO_ES_REMIXER and not w.isdigit()}
    return frozenset(toks)


def respeta_remixer(titulo: str, stem: str) -> bool:
    """False si el titulo nombra un remixer que el archivo no menciona: otra version."""
    toks = tokens_de_remixer(titulo)
    if not toks:
        return True
    nombre = _solo_alfanumerico(stem)
    return all(t in nombre for t in toks)


# Un remix o edit que comparte la voz con el original suena igual en los primeros
# 30 s, asi que la huella lo da por duplicado; pero casi nunca dura lo mismo.
TOLERANCIA_DURACION_S = 15


def duracion_compatible(ruta, duracion_s, tolerancia: float = TOLERANCIA_DURACION_S) -> bool:
    """True si el archivo dura lo que se espera (o si no se puede saber)."""
    if not duracion_s:
        return True
    try:
        from mutagen import File as MFile
        archivo = MFile(str(ruta))
        real = float(archivo.info.length)
    except Exception:
        return True
    return abs(real - duracion_s) <= tolerancia


def like_candidates(artist: str, title: str) -> set[str]:
    """
    Variantes de un track de SoundCloud con las que vale la pena comparar:
    "artista + título" y el título solo (ver punto 1 del docstring del módulo).
    """
    return _usable({clean_for_match(f"{artist or ''} {title or ''}"), clean_for_match(title or "")})


def file_candidates(stem: str) -> set[str]:
    """Variantes de un archivo local (por ahora, su nombre sin extensión)."""
    return _usable({clean_for_match(stem)})


def best_score(candidates_a: Iterable[str], candidates_b: Iterable[str]) -> int:
    """Mejor similitud (0-100) entre dos conjuntos de variantes."""
    best = 0
    for a in candidates_a:
        for b in candidates_b:
            score = max(fuzz.token_sort_ratio(a, b), fuzz.ratio(a, b))
            if score > best:
                best = score
    return best


def index_audio_files(folders: Iterable[str]) -> list[tuple[Path, set[str]]]:
    """
    Indexa recursivamente los archivos de audio de una o más carpetas,
    precalculando sus variantes normalizadas.

    Se construye UNA vez y se reutiliza para todas las comparaciones: antes
    se re-recorría el disco entero por cada canción a verificar.

    Carpetas anidadas o repetidas se indexan una sola vez.
    """
    index: list[tuple[Path, set[str]]] = []
    seen: set[str] = set()
    for folder in folders:
        if not folder:
            continue
        root = Path(folder)
        if not root.is_dir():
            logger.debug("Carpeta inexistente al indexar, se omite: %s", folder)
            continue
        try:
            for path in root.rglob("*"):
                if es_basura_del_sistema(path):
                    continue
                if not path.is_file() or path.suffix.lower() not in AUDIO_EXTENSIONS:
                    continue
                key = str(path).lower()
                if key in seen:
                    continue
                seen.add(key)
                cands = file_candidates(path.stem)
                if cands:
                    index.append((path, cands))
        except (OSError, PermissionError) as exc:
            logger.warning("Error indexando %s: %s", folder, exc)
    return index


def find_best_match(
    candidates: Iterable[str],
    index: list[tuple[Path, set[str]]],
    threshold: int = MATCH_THRESHOLD,
    titulo: Optional[str] = None,
) -> tuple[Optional[Path], int]:
    """
    Busca en el índice el archivo MÁS parecido (no el primero que supere el
    umbral). Devuelve (ruta, score) o (None, mejor_score) si nada llega al
    umbral.

    Si se pasa `titulo`, se descartan los archivos cuyo nombre no menciona al
    remixer que ese titulo nombra entre parentesis (ver tokens_de_remixer).
    """
    candidates = list(candidates)
    if not candidates:
        return None, 0
    best_path, best = None, 0
    for path, file_cands in index:
        if titulo and not respeta_remixer(titulo, path.stem):
            continue
        score = best_score(candidates, file_cands)
        if score > best:
            best, best_path = score, path
    if best_path is not None and best >= threshold:
        return best_path, best
    return None, best
