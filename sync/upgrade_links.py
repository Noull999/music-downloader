"""
Detecta qué likes ya descargados tienen, según SoundCloud, un lugar mejor
de donde conseguirlos: el gate de descarga gratis que puso el artista
(Hypeddit, Bandcamp, fanlink...) a cambio de un follow/like/repost.

No hace falta rastrear la descripción del track: SoundCloud trae un campo
dedicado para esto, `purchase_url`, presente en ~65% de una biblioteca
real medida (270 de 412 likes). Se usa tal cual, sin intentar completar el
gate por la app — eso es una decisión del usuario, no algo para
automatizar (ver el hilo de la sesión: el gate es lo que el artista pide a
cambio, saltarlo o fingir el follow/like no es aceptable).
"""
import re
from urllib.parse import urlparse

# Dominios reconocidos, con una etiqueta legible. No es necesario un
# manejo especial por servicio: solo mostrarle al usuario adónde va.
_ETIQUETAS = {
    "hypeddit.com": "Hypeddit",
    "toneden.io": "ToneDen",
    "click.dj": "Click.dj",
    "droploud.com": "Droploud",
    "fanlink.tv": "Fanlink",
    "hyperfollow.com": "HyperFollow",
    "songwhip.com": "Songwhip",
    "push.fm": "Push.fm",
    "linktr.ee": "Linktree",
    "bandcamp.com": "Bandcamp",
    "dropbox.com": "Dropbox",
    "drive.google.com": "Google Drive",
    "mediafire.com": "MediaFire",
    "wetransfer.com": "WeTransfer",
}


def _dominio_base(host: str) -> str:
    """'schranzformatorakaobi.bandcamp.com' -> 'bandcamp.com'."""
    partes = host.split(".")
    return ".".join(partes[-2:]) if len(partes) >= 2 else host


def clasificar(purchase_url: str) -> tuple[str, str]:
    """
    Returns: (dominio_base, etiqueta_legible). Etiqueta es el dominio tal
    cual si no está en la lista reconocida.
    """
    try:
        host = urlparse(purchase_url).netloc.lower()
    except ValueError:
        return "", purchase_url
    base = _dominio_base(host)
    return base, _ETIQUETAS.get(base, base or purchase_url)


def es_gate_de_descarga(purchase_url: str) -> bool:
    """
    True si el link parece un gate de descarga gratis y no, por ejemplo,
    un link de compra en Beatport/iTunes (que no tiene sentido "mejorar":
    ahí se paga, no hay nada que la app pueda ofrecerte gratis).
    """
    base, _ = clasificar(purchase_url)
    # clasificar() ya reduce a los últimos dos segmentos del dominio
    # ("open.spotify.com" -> "spotify.com"), así que la lista de exclusión
    # tiene que estar en esa misma forma o nunca matchea.
    no_son_gates = {"beatport.com", "apple.com", "spotify.com",
                    "traxsource.com", "junodownload.com"}
    return bool(base) and base not in no_son_gates


def candidatos_de_mejor_calidad(likes: list[dict], descargados: dict[str, dict]) -> list[dict]:
    """
    De los likes ya descargados, cuáles tienen un gate disponible que
    probablemente dé mejor calidad que lo que ya se tiene.

    Se excluyen los que el artista dejó descargar nativo en SoundCloud
    (`downloadable`): ahí yt-dlp ya se llevó el archivo original, no el
    stream, y no hay nada que un gate externo mejore.

    Args:
        likes: filas de soundcloud_likes (con purchase_url/downloadable)
        descargados: url -> {"local_path": ...} de lo que ya está en disco

    Returns: [{title, artist, url, purchase_url, servicio, local_path}, ...]
    """
    out = []
    for like in likes:
        url = like.get("url", "")
        descarga = descargados.get(url)
        if not descarga:
            continue  # todavía no se bajó; no hay "mejor calidad" que ofrecer aún
        if like.get("downloadable"):
            continue  # ya se bajó el original nativo
        purchase_url = (like.get("purchase_url") or "").strip()
        if not purchase_url or not es_gate_de_descarga(purchase_url):
            continue
        _, etiqueta = clasificar(purchase_url)
        out.append({
            "title": like.get("title", ""),
            "artist": like.get("artist", ""),
            "url": url,
            "purchase_url": purchase_url,
            "servicio": etiqueta,
            "local_path": descarga.get("local_path", ""),
        })
    return out
