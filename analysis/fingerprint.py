"""
Huella de audio (Chromaprint) para detectar duplicados por sonido, no por
nombre de archivo. Complementa sync/match_utils.py: ese matching de texto
falla cuando el mismo tema tiene un nombre de archivo muy distinto al
título de SoundCloud (o, al revés, dos remixes/edits distintos comparten
casi el mismo nombre). Acá se compara el audio real.

Validado contra la biblioteca real del usuario (2026-09-02):
  - Mismo tema con offset/recorte inducido: 0.96-0.99 de similitud.
  - 14 pares de temas con títulos MUY parecidos entre sí (remixes/edits
    distintos del mismo tema base, hasta 97% de similitud de texto):
    todos dieron por debajo de 0.71 de similitud de audio.
Por eso MATCH_THRESHOLD=0.85: deja margen de sobra a ambos lados.
"""
import json
import logging
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Iterable, Optional

logger = logging.getLogger(__name__)

MATCH_THRESHOLD = 0.85
PREVIEW_SECONDS = 30
FP_LENGTH = 60

CACHE_PATH = Path.home() / ".music_downloader" / "fingerprint_index.json"

AUDIO_EXTENSIONS = {".mp3", ".m4a", ".flac", ".wav", ".ogg", ".opus", ".aac"}


def _fpcalc_path() -> str:
    """Ubica fpcalc.exe: empaquetado junto al .exe, en dev bajo build/, o en PATH."""
    candidates = []
    if getattr(sys, "frozen", False):
        candidates.append(Path(sys._MEIPASS) / "fpcalc" / "fpcalc.exe")
    else:
        base = Path(__file__).resolve().parents[1]
        candidates.append(base / "build" / "fpcalc" / "fpcalc.exe")
    for c in candidates:
        if c.exists():
            return str(c)
    found = shutil.which("fpcalc")
    if found:
        return found
    raise FileNotFoundError(
        "No se encontró fpcalc (Chromaprint). Corré scripts/build.py o "
        "instalá chromaprint y agregalo al PATH."
    )


def fingerprint_file(path: str, length: int = FP_LENGTH) -> Optional[list[int]]:
    try:
        fpcalc = _fpcalc_path()
    except FileNotFoundError as e:
        logger.warning(str(e))
        return None
    try:
        out = subprocess.run(
            [fpcalc, "-raw", "-length", str(length), path],
            capture_output=True, text=True, timeout=60,
        )
    except Exception as e:
        logger.warning("fpcalc falló en %s: %s", path, e)
        return None
    for line in out.stdout.splitlines():
        if line.startswith("FINGERPRINT="):
            try:
                return [int(x) for x in line[len("FINGERPRINT="):].split(",")]
            except ValueError:
                return None
    return None


def _hamming(a: int, b: int) -> int:
    return bin(a ^ b).count("1")


def similarity_aligned(fp1: list[int], fp2: list[int], max_shift: int = 40) -> float:
    """
    Similitud [0,1] tolerante a desfase (p.ej. un preview que arranca en
    otro punto del tema que el archivo local). Solapa fp1/fp2 probando
    corrimientos de hasta max_shift posiciones y se queda con el mejor.
    """
    best = 0.0
    n1, n2 = len(fp1), len(fp2)
    for shift in range(-max_shift, max_shift + 1):
        total = 0
        matches = 0.0
        for i in range(max(0, -shift), min(n1, n2 - shift)):
            j = i + shift
            total += 1
            matches += 1 - (_hamming(fp1[i], fp2[j]) / 32.0)
        if total > 10:
            sim = matches / total
            if sim > best:
                best = sim
    return best


class LibraryFingerprintIndex:
    """
    Huellas de todos los archivos de la biblioteca, cacheadas en disco por
    (mtime, tamaño) para no volver a analizar miles de archivos en cada
    sync (la primera vez tarda minutos; después, solo lo nuevo/cambiado).
    """

    def __init__(self, cache_path: Path = CACHE_PATH):
        self.cache_path = cache_path
        self._entries: dict[str, dict] = {}

    def _load_cache(self) -> dict:
        if self.cache_path.exists():
            try:
                return json.loads(self.cache_path.read_text(encoding="utf-8"))
            except Exception:
                logger.warning("Cache de huellas corrupta, se reconstruye")
        return {}

    def _save_cache(self) -> None:
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            self.cache_path.write_text(json.dumps(self._entries), encoding="utf-8")
        except Exception as e:
            logger.warning("No se pudo guardar cache de huellas: %s", e)

    def build(self, folders: Iterable[str]) -> None:
        cache = self._load_cache()
        files = []
        for folder in folders:
            root = Path(folder)
            if not root.is_dir():
                continue
            files.extend(p for p in root.rglob("*") if p.suffix.lower() in AUDIO_EXTENSIONS and p.is_file())

        new_entries = {}
        computed = 0
        for p in files:
            key = str(p)
            try:
                stat = p.stat()
            except OSError:
                continue
            cached = cache.get(key)
            if cached and cached.get("mtime") == stat.st_mtime and cached.get("size") == stat.st_size:
                new_entries[key] = cached
                continue
            fp = fingerprint_file(key)
            computed += 1
            if fp:
                new_entries[key] = {"mtime": stat.st_mtime, "size": stat.st_size, "fp": fp}

        self._entries = new_entries
        self._save_cache()
        logger.info(
            "Índice de huellas: %d archivos (%d recalculados)",
            len(new_entries), computed,
        )

    def find_best_match(self, fp: list[int]) -> Optional[tuple[str, float]]:
        best_path, best_score = None, 0.0
        for path, entry in self._entries.items():
            score = similarity_aligned(fp, entry["fp"])
            if score > best_score:
                best_score = score
                best_path = path
        if best_path and best_score >= MATCH_THRESHOLD:
            return best_path, best_score
        return None

    def __len__(self) -> int:
        return len(self._entries)


def download_preview(
    url: str,
    dest_path_no_ext: str,
    oauth_token: str = "",
    duration: int = PREVIEW_SECONDS,
) -> Optional[str]:
    """
    Baja solo los primeros `duration` segundos, sin convertir, para poder
    sacarle la huella sin descargar el tema completo.
    """
    import yt_dlp

    from handlers.base_handler import ffmpeg_location

    ydl_opts: dict = {
        "format": "bestaudio/best",
        "outtmpl": dest_path_no_ext + ".%(ext)s",
        "quiet": True,
        "no_warnings": True,
        "download_ranges": yt_dlp.utils.download_range_func(None, [(0, duration)]),
        "force_keyframes_at_cuts": True,
        "retries": 1,
        "fragment_retries": 1,
    }
    if loc := ffmpeg_location():
        ydl_opts["ffmpeg_location"] = loc
    if oauth_token:
        ydl_opts["extractor_args"] = {"soundcloud": {"oauth_token": [oauth_token]}}

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
    except Exception as e:
        logger.debug("No se pudo bajar preview de %s: %s", url, e)
        return None

    parent = Path(dest_path_no_ext).parent
    name = Path(dest_path_no_ext).name
    for candidate in parent.glob(name + ".*"):
        return str(candidate)
    return None
