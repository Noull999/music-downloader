"""
Validacion y parsing de URLs para YouTube y SoundCloud.
"""
import re
from urllib.parse import urlparse

from url_detector import supported_domains

# Regex amplio para extraer URLs de un bloque de texto
_URL_RE = re.compile(r"https?://[^\s\"'<>]+")


def validate_url(url: str) -> bool:
    """Retorna True si la URL pertenece a una plataforma soportada."""
    url = url.strip()
    if not url:
        return False
    try:
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https"):
            return False
        host = parsed.netloc.lower().replace("www.", "")
        return any(host == d or host.endswith("." + d) for d in supported_domains())
    except Exception:
        return False


def parse_urls_from_text(text: str) -> list[str]:
    """
    Extrae URLs validas de un bloque de texto multilínea.
    Acepta una URL por linea o embebidas en texto.
    Deduplica manteniendo el orden.
    """
    seen: set[str] = set()
    result: list[str] = []

    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        # Intentar la linea entera primero
        if validate_url(line):
            clean = line.rstrip("/")
            if clean not in seen:
                seen.add(clean)
                result.append(clean)
            continue
        # Extraer URLs embebidas en texto
        for match in _URL_RE.finditer(line):
            candidate = match.group(0).rstrip("/.,;)")
            if validate_url(candidate) and candidate not in seen:
                seen.add(candidate)
                result.append(candidate)

    return result
