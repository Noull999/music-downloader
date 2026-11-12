"""
Deja título y artista de forma que se puedan encontrar al buscar en Serato.

Serato busca en las etiquetas del archivo, no en su nombre. Medido sobre una
biblioteca real (1618 pistas): 27 sin título ni artista, 239 sin artista con el
título "Artista - Tema", varias con la codificación rota ("TiÃ«sto") y 52 con
letras que no salen del teclado ("KØZLØV", cirílicas que parecen latinas).

Nunca deja una etiqueta en blanco y guarda un respaldo de lo que había.
"""
import json
import logging
import re
import unicodedata
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

EXTENSIONES = {".mp3", ".wav", ".aiff", ".aif"}   # las que llevan ID3
CARPETA_RESPALDO = Path.home() / ".music_downloader"

# Un grupo entre corchetes/paréntesis que solo anuncia la descarga gratis.
_PROMO_GRUPO = re.compile(r"\s*[\[({][^\])}]*\bfree\s*(?:dl|download)\b[^\])}]*[\])}]", re.I)
_PROMO_SUELTO = re.compile(r"\s*[|*\-–:]*\s*\bfree\s*(?:dl|download)\b\s*[|*\-–:]*\s*", re.I)
_PREMIERE = re.compile(r"^\s*premiere\s*[:|\-–]\s*", re.I)

_TECLADO = set("áéíóúüñÁÉÍÓÚÜÑ¿¡")   # se escriben con un teclado en español
_SIN_DESCOMPOSICION = str.maketrans({
    "ø": "o", "Ø": "O", "æ": "ae", "Æ": "AE", "ß": "ss", "đ": "d", "Đ": "D",
    "ł": "l", "Ł": "L", "Λ": "A", "–": "-", "—": "-", "’": "'", "‘": "'", "“": '"', "”": '"',
})
# Cirílicas que se ven igual que una latina (nombres "decorados").
_CIRILICAS = str.maketrans("аеорсхіАЕОРСХІ", "aeopcxiAEOPCXI")


def _arreglar_codificacion(s: str) -> str:
    """'TiÃ«sto' -> 'Tiësto'. Solo si TODO el texto vuelve a ser UTF-8 válido."""
    for enc in ("cp1252", "latin-1"):
        try:
            return s.encode(enc).decode("utf-8")
        except UnicodeError:
            continue
    return s


def _tipeable(s: str) -> str:
    if re.search("[A-Za-z]", s):   # un título entero en ruso no se toca
        s = s.translate(_CIRILICAS)
    salida = []
    for ch in s.translate(_SIN_DESCOMPOSICION):
        if ord(ch) < 128 or ch in _TECLADO:
            salida.append(ch)
            continue
        base = "".join(c for c in unicodedata.normalize("NFKD", ch) if not unicodedata.combining(c))
        salida.append(base if base and all(ord(c) < 128 for c in base) else ch)
    return "".join(salida)


def limpiar(texto: str) -> str:
    """Texto de una etiqueta, encontrable escribiéndolo con el teclado."""
    original = (texto or "").strip()
    s = _tipeable(_arreglar_codificacion(original))
    s = _PREMIERE.sub("", _PROMO_SUELTO.sub(" ", _PROMO_GRUPO.sub("", s)))
    s = re.sub(r"\s{2,}", " ", s).strip(" -|")
    return s or original   # un tema que se llama "Free Download" queda como está


def propuesta(nombre_archivo: str, title: str, artist: str) -> tuple[str, str]:
    """(título, artista) corregidos. Lo vacío sale del nombre del archivo."""
    t, a = limpiar(title), limpiar(artist)
    if not t:
        t = limpiar(Path(nombre_archivo).stem)
    # Solo se separa si NO hay artista: con artista puesto, "Tema - Extended"
    # no se puede distinguir de "Artista - Tema".
    if not a and " - " in t:
        a, t = (x.strip() for x in t.split(" - ", 1))
    return t, a


def _leer(ruta):
    from mutagen import File as MFile
    audio = MFile(ruta)
    tags = audio.tags if audio is not None else None

    def texto(clave):
        frame = tags.get(clave) if tags else None
        return str(frame.text[0]).strip() if frame is not None and frame.text else ""

    return audio, texto("TIT2"), texto("TPE1")


def buscar_cambios(carpetas: list[str]) -> list[dict]:
    """[{ruta, antes: {title, artist}, despues: {title, artist}}] de lo que cambiaría."""
    from sync import match_utils
    cambios = []
    for ruta, _ in match_utils.index_audio_files(carpetas):
        if ruta.suffix.lower() not in EXTENSIONES:
            continue
        try:
            _, t, a = _leer(str(ruta))
        except Exception:
            logger.warning("No se pudieron leer las etiquetas de %s", ruta)
            continue
        nt, na = propuesta(ruta.name, t, a)
        if (nt, na) != (t, a):
            cambios.append({"ruta": str(ruta), "antes": {"title": t, "artist": a},
                            "despues": {"title": nt, "artist": na}})
    return cambios


def aplicar(cambios: list[dict]) -> dict:
    """Escribe los cambios. Antes guarda en un JSON lo que había."""
    from mutagen.id3 import TIT2, TPE1
    CARPETA_RESPALDO.mkdir(parents=True, exist_ok=True)
    respaldo = CARPETA_RESPALDO / f"etiquetas_antes_{datetime.now():%Y%m%d_%H%M%S}.json"
    respaldo.write_text(json.dumps(cambios, ensure_ascii=False, indent=1), encoding="utf-8")

    aplicados = errores = 0
    for c in cambios:
        try:
            audio, _, _ = _leer(c["ruta"])
            if audio.tags is None:
                audio.add_tags()
            for clave, frame in (("title", TIT2), ("artist", TPE1)):
                valor = c["despues"][clave]
                if valor and valor != c["antes"][clave]:
                    audio.tags.setall(frame.__name__, [frame(encoding=3, text=[valor])])
            audio.save(v2_version=3)   # v2.3: ver quality/post_processor.py
            # Releer: hay WAV con bloques 'id3' duplicados donde guardar "funciona"
            # pero no escribe nada.
            _, t, a = _leer(c["ruta"])
            if (t, a) != (c["despues"]["title"], c["despues"]["artist"]):
                raise OSError("las etiquetas no quedaron escritas")
            aplicados += 1
        except Exception:
            logger.exception("No se pudieron escribir las etiquetas de %s", c["ruta"])
            errores += 1
    return {"aplicados": aplicados, "errores": errores, "respaldo": str(respaldo)}
