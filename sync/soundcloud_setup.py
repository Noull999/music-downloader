"""
Ayudas para conectar SoundCloud sin tocar las herramientas de desarrollador.

- `detectar_client_id()`: el Client ID es publico (la propia web de SoundCloud
  lo lleva dentro de sus scripts), asi que se lee de ahi en vez de pedirselo
  a la persona.
- `token_de_cookies()`: el OAuth Token es la cookie `oauth_token` que
  SoundCloud deja al iniciar sesion; la persona inicia sesion en una ventana
  de la app y se lee de ahi (la app nunca ve la contrasena).
"""
import logging
import re
from typing import Iterable, Optional

import requests

logger = logging.getLogger(__name__)

_URL_PORTADA = "https://soundcloud.com/"
_UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                     "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"}
_RE_SCRIPT = re.compile(r'<script[^>]+src="(https://a-v2\.sndcdn\.com/assets/[^"]+\.js)"')
_RE_CLIENT_ID = re.compile(r'client_id\s*[:=]\s*"([A-Za-z0-9]{32})"')


def client_id_en_js(js: str) -> Optional[str]:
    """Busca `client_id:"..."` (32 caracteres alfanumericos) dentro de un script."""
    m = _RE_CLIENT_ID.search(js or "")
    return m.group(1) if m else None


def scripts_de_la_portada(html: str) -> list[str]:
    return _RE_SCRIPT.findall(html or "")


def detectar_client_id(sesion=None) -> Optional[str]:
    """
    Client ID vigente de la web de SoundCloud, o None si no se pudo leer.
    El que lleva el id suele estar en los ultimos scripts, asi que se
    recorren de atras hacia adelante.
    """
    s = sesion or requests.Session()
    try:
        html = s.get(_URL_PORTADA, headers=_UA, timeout=15).text
        for url in reversed(scripts_de_la_portada(html)):
            cid = client_id_en_js(s.get(url, headers=_UA, timeout=15).text)
            if cid:
                return cid
    except requests.RequestException as e:
        logger.warning("No se pudo leer el Client ID de SoundCloud: %s", e)
    return None


def token_de_cookies(cookies: Iterable) -> Optional[str]:
    """
    Arma el valor del header Authorization ("OAuth 2-...") a partir de las
    cookies de la ventana de login. Acepta objetos http.cookies.SimpleCookie
    (lo que devuelve pywebview) y diccionarios {name, value}.
    """
    for c in cookies or []:
        items = c.items() if hasattr(c, "items") else []
        for nombre, morsel in items:
            if nombre == "oauth_token":
                # Un Morsel es un dict con atributo .value; un dict comun trae "value".
                valor = getattr(morsel, "value", None)
                if valor is None and isinstance(morsel, dict):
                    valor = morsel.get("value")
                if valor is None:
                    valor = morsel
                valor = (valor or "").strip().strip('"')
                if valor:
                    return valor if valor.lower().startswith("oauth ") else f"OAuth {valor}"
        if isinstance(c, dict) and c.get("name") == "oauth_token" and c.get("value"):
            valor = str(c["value"]).strip().strip('"')
            return valor if valor.lower().startswith("oauth ") else f"OAuth {valor}"
    return None
