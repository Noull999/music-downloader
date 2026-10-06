"""
Motor JavaScript para YouTube.

YouTube entrega los links de audio "cifrados" junto con un JavaScript que los
descifra; yt-dlp necesita un motor externo que lo ejecute (sin el, la
extraccion esta obsoleta y pueden faltar formatos). Se ofrecen todos los que
haya y yt-dlp elige el mejor disponible (deno > node > quickjs):

- deno / node: si la persona ya los tiene instalados (node >= 22).
- quickjs: un motor chico (~2 MB) que va dentro del ejecutable, para que
  funcione en cualquier PC o Mac sin instalar nada.
"""
import sys
from pathlib import Path


def _quickjs_incluido():
    nombre = "qjs.exe" if sys.platform == "win32" else "qjs"
    if getattr(sys, "frozen", False):
        candidato = Path(getattr(sys, "_MEIPASS", "")) / "quickjs" / nombre
    else:
        candidato = Path(__file__).resolve().parents[1] / "build" / "quickjs" / nombre
    return str(candidato) if candidato.is_file() else None


def runtimes() -> dict:
    """Valor para la opcion `js_runtimes` de yt-dlp."""
    rts = {"deno": {}, "node": {}}
    qjs = _quickjs_incluido()
    rts["quickjs"] = {"path": qjs} if qjs else {}
    return rts


def aplicar(opts: dict) -> dict:
    """Agrega los motores a unas opciones de yt-dlp (sin pisar si ya vienen)."""
    opts.setdefault("js_runtimes", runtimes())
    return opts
