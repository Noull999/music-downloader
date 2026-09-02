"""
Detección de BPM y tonalidad musical, con notación Camelot para mezcla
armónica.

Los parámetros no son los que vienen por defecto en librosa: se eligieron
midiendo contra archivos de la biblioteca real que ya traían BPM en sus
tags (ver docstrings de cada función). Cambiarlos sin volver a medir
degrada la precisión de forma silenciosa.
"""
import logging
import os
import warnings
from typing import Optional

logger = logging.getLogger(__name__)

# Rango de BPM al que se pliega el resultado. La detección de tempo tiene
# ambigüedad de octava (un track de 174 puede reportarse como 87 o 348);
# 85-175 cubre prácticamente toda la música de baile (house ~125,
# techno ~145-160, DnB ~174, guaracha ~128) sin partir géneros al medio.
BPM_MIN = 85
BPM_MAX = 175

# Semilla del beat tracker. Con el valor por defecto de librosa (120) los
# resultados eran erráticos en material de techno/DnB; con 145 dieron
# 8 de 10 casi exactos contra los BPM ya tagueados de la biblioteca.
BPM_START_PRIOR = 145

# Por debajo de esta correlación, la tonalidad detectada no es confiable y
# se descarta en vez de escribir un valor probablemente incorrecto. Medido
# analizando cada track por mitades: las que discrepaban entre mitad A y
# mitad B puntuaban 0.31-0.39, las coincidentes 0.47-0.78.
KEY_MIN_CONFIDENCE = 0.45

_NOTES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]

# Perfiles Krumhansl-Schmuckler: peso esperado de cada grado de la escala
# en música tonal. Se correlacionan contra el cromagrama del track.
_MAJOR_PROFILE = [6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88]
_MINOR_PROFILE = [6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17]

# Rueda Camelot: (nota, es_menor) -> código. Las claves adyacentes en la
# rueda (mismo número ±1, o cambiar A/B) son las compatibles para mezclar.
_CAMELOT = {
    ("B", True): "1A", ("F#", True): "2A", ("C#", True): "3A", ("G#", True): "4A",
    ("D#", True): "5A", ("A#", True): "6A", ("F", True): "7A", ("C", True): "8A",
    ("G", True): "9A", ("D", True): "10A", ("A", True): "11A", ("E", True): "12A",
    ("D", False): "1B", ("A", False): "2B", ("E", False): "3B", ("B", False): "4B",
    ("F#", False): "5B", ("C#", False): "6B", ("G#", False): "7B", ("D#", False): "8B",
    ("A#", False): "9B", ("F", False): "10B", ("C", False): "11B", ("G", False): "12B",
}


class AnalysisResult:
    """Resultado del análisis. `key`/`camelot` pueden ser None si no hubo confianza."""

    __slots__ = ("bpm", "key", "camelot", "key_confidence")

    def __init__(self, bpm: Optional[float], key: Optional[str],
                 camelot: Optional[str], key_confidence: float):
        self.bpm = bpm
        self.key = key
        self.camelot = camelot
        self.key_confidence = key_confidence

    def __repr__(self):
        return (f"<AnalysisResult bpm={self.bpm} key={self.key} "
                f"camelot={self.camelot} conf={self.key_confidence:.2f}>")


def _fold_bpm(bpm: float) -> float:
    """Lleva el BPM al rango típico duplicando o dividiendo (ambigüedad de octava)."""
    if bpm <= 0:
        return bpm
    # Los límites evitan un loop infinito con valores absurdos.
    for _ in range(8):
        if bpm < BPM_MIN:
            bpm *= 2
        elif bpm > BPM_MAX:
            bpm /= 2
        else:
            break
    return bpm


def to_camelot(key: str) -> Optional[str]:
    """Convierte una tonalidad tipo 'Gm' o 'D#' a su código Camelot."""
    if not key:
        return None
    is_minor = key.endswith("m")
    note = key[:-1] if is_minor else key
    return _CAMELOT.get((note, is_minor))


def analyze_file(path: str) -> Optional[AnalysisResult]:
    """
    Analiza un archivo de audio y devuelve BPM, tonalidad y Camelot.

    Devuelve None si el archivo no se puede leer o si librosa no está
    instalado (es una dependencia opcional: la app funciona sin analizar).

    Tarda ~2 segundos por track en un equipo de escritorio, más una
    compilación inicial de numba (~60-80s) la primera vez en cada proceso.
    """
    try:
        import numpy as np
        import librosa
    except ImportError:
        logger.warning(
            "librosa no está instalado; se omite el análisis de BPM/tonalidad. "
            "Instalalo con: pip install librosa"
        )
        return None

    if not os.path.isfile(path):
        logger.warning("No existe el archivo a analizar: %s", path)
        return None

    try:
        with warnings.catch_warnings():
            # librosa avisa sobre formatos que delega a audioread; es ruido.
            warnings.simplefilter("ignore")
            # 22050 Hz mono alcanza para tempo y croma, y es varias veces
            # más rápido que cargar a full calidad.
            y, sr = librosa.load(path, sr=22050, mono=True)

            if y.size == 0:
                logger.warning("Audio vacío: %s", path)
                return None

            tempo, _ = librosa.beat.beat_track(y=y, sr=sr, start_bpm=BPM_START_PRIOR)
            bpm = _fold_bpm(float(np.atleast_1d(tempo)[0]))

            chroma = librosa.feature.chroma_cqt(y=y, sr=sr)
            profile = chroma.mean(axis=1)

            best_corr, best_note, best_minor = -2.0, None, False
            major = np.array(_MAJOR_PROFILE)
            minor = np.array(_MINOR_PROFILE)
            for i in range(12):
                rotated = np.roll(profile, -i)
                for is_minor, reference in ((False, major), (True, minor)):
                    corr = float(np.corrcoef(rotated, reference)[0, 1])
                    if corr > best_corr:
                        best_corr, best_note, best_minor = corr, _NOTES[i], is_minor

        if best_note is None or best_corr < KEY_MIN_CONFIDENCE:
            # BPM sí, tonalidad no: preferimos un tag vacío a uno equivocado,
            # porque una tonalidad mal escrita arruina la mezcla armónica.
            return AnalysisResult(round(bpm, 1), None, None, max(best_corr, 0.0))

        key = f"{best_note}{'m' if best_minor else ''}"
        return AnalysisResult(round(bpm, 1), key, to_camelot(key), best_corr)

    except Exception:
        logger.exception("Error analizando %s", path)
        return None


def write_tags(path: str, result: AnalysisResult, key_format: str = "camelot") -> bool:
    """
    Escribe BPM y tonalidad en los tags del archivo.

    key_format:
        "camelot"  -> escribe el código Camelot (9A, 5B...) en el campo de
                      tonalidad. Es lo que esperan la mayoría de los DJs
                      para mezcla armónica.
        "musical"  -> escribe la notación tradicional (Gm, D#...).

    Serato, Rekordbox y Traktor leen BPM del frame TBPM y tonalidad de TKEY.
    """
    if result is None:
        return False

    try:
        from mutagen import File as MutagenFile
        from mutagen.id3 import ID3, TBPM, TKEY, ID3NoHeaderError
    except ImportError:
        logger.warning("mutagen no disponible; no se escriben tags de análisis")
        return False

    key_value = None
    if result.key:
        key_value = result.camelot if key_format == "camelot" else result.key
        if key_value is None:  # sin mapeo Camelot, cae a la notación musical
            key_value = result.key

    try:
        ext = os.path.splitext(path)[1].lower()
        if ext in (".mp3", ".wav", ".aiff", ".aif"):
            # Estos formatos usan ID3; en WAV/AIFF va dentro de un chunk.
            try:
                tags = ID3(path)
            except ID3NoHeaderError:
                tags = ID3()
            if result.bpm:
                tags.add(TBPM(encoding=3, text=str(int(round(result.bpm)))))
            if key_value:
                tags.add(TKEY(encoding=3, text=key_value))
            tags.save(path)
        else:
            # FLAC/OGG/M4A: campos Vorbis/MP4 vía la interfaz genérica.
            audio = MutagenFile(path)
            if audio is None:
                logger.warning("Formato no soportado para tags: %s", path)
                return False
            if audio.tags is None:
                audio.add_tags()
            if result.bpm:
                audio["bpm"] = str(int(round(result.bpm)))
            if key_value:
                audio["key"] = key_value
            audio.save()

        logger.info(
            "✓ Analizado: %s BPM%s | %s",
            int(round(result.bpm)) if result.bpm else "?",
            f" · {key_value}" if key_value else " · tonalidad no confiable",
            os.path.basename(path),
        )
        return True

    except Exception:
        logger.exception("Error escribiendo tags de análisis en %s", path)
        return False


def analyze_and_tag(path: str, key_format: str = "camelot") -> Optional[AnalysisResult]:
    """Analiza y escribe los tags en un solo paso. Devuelve el resultado o None."""
    result = analyze_file(path)
    if result is None:
        return None
    write_tags(path, result, key_format=key_format)
    return result
