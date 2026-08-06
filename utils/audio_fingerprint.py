"""
Fingerprinting acústico (Chromaprint/AcoustID) para detectar duplicados
REALES de audio, sin depender del nombre de archivo.

Nota de diseño: esto NO puede reemplazar el chequeo de duplicados de
`sync/duplicate_checker.py` en el punto en que hoy se ejecuta, porque ese
chequeo corre ANTES de descargar (solo hay URL/título disponibles, no
audio). El fingerprinting solo tiene sentido una vez el archivo ya existe
en disco. Por eso se expone como una utilidad de escaneo de biblioteca
(ver `sync/audio_duplicate_scanner.py`), no como parte del filtro
pre-descarga.

Requiere:
  - paquete Python `pyacoustid` (pip install pyacoustid)
  - binario `fpcalc` (Chromaprint) accesible en PATH
Si cualquiera de los dos falta, todas las funciones degradan a None/False
sin lanzar — mismo patrón defensivo que el resto del proyecto con ffmpeg
y mutagen.
"""
import logging
import shutil
from typing import Optional

logger = logging.getLogger(__name__)


def is_available() -> bool:
    """
    True si pyacoustid + los bindings de chromaprint + el binario fpcalc
    están disponibles. Se necesitan los tres: fpcalc genera el fingerprint,
    los bindings de chromaprint (paquete `chromaprint`) lo decodifican para
    poder comparar dos fingerprints entre sí.
    """
    try:
        import acoustid
    except ImportError:
        return False
    if not getattr(acoustid, "have_chromaprint", False):
        return False
    return shutil.which("fpcalc") is not None


def fingerprint_file(file_path: str, max_length: int = 120) -> Optional[tuple]:
    """
    Calcula el fingerprint acústico de un archivo: (duration, fingerprint).
    Retorna None si no se puede (dependencia faltante, archivo inválido, etc).
    El resultado se pasa tal cual a `similarity()`.

    Args:
        file_path: ruta al archivo de audio
        max_length: segundos máximos a analizar (fpcalc por defecto usa 120)
    """
    try:
        import acoustid
    except ImportError:
        logger.debug("pyacoustid no instalado; fingerprinting no disponible.")
        return None

    try:
        return acoustid.fingerprint_file(file_path, maxlength=max_length)
    except Exception as exc:
        logger.debug("No se pudo generar fingerprint de %s: %s", file_path, exc)
        return None


def similarity(fp1: tuple, fp2: tuple) -> float:
    """
    Compara dos fingerprints (tal como los devuelve `fingerprint_file`) y
    retorna similitud 0-100. Usa `acoustid.compare_fingerprints`, la propia
    implementación de pyacoustid (decodificación Chromaprint + comparación
    por desplazamiento/Hamming), en vez de reinventar el algoritmo.
    """
    try:
        import acoustid
    except ImportError:
        return 0.0

    try:
        return acoustid.compare_fingerprints(fp1, fp2) * 100.0
    except Exception as exc:
        logger.debug("Error comparando fingerprints: %s", exc)
        return 0.0
