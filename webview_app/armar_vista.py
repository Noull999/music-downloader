"""
Arma la interfaz como UN solo texto HTML, con las tipografias adentro.

Antes la ventana cargaba view.html desde un servidor local que levanta
pywebview (http://127.0.0.1:puerto). En un Mac de prueba el navegador tardo
35 s solo en conectarse a ese servidor y la ventana quedaba en negro mientras
tanto; esa conexion local es ademas lo que bloquean firewalls, antivirus,
proxies y la privacidad de red local de macOS. Pasandole la pagina entera a la
ventana no hace falta ningun servidor.
"""
import base64
import re
from pathlib import Path

ENLACE_FUENTES = '<link rel="stylesheet" href="fonts/fonts.css">'


def _css_con_fuentes_adentro(carpeta_fuentes: Path) -> str:
    css = (carpeta_fuentes / "fonts.css").read_text(encoding="utf-8")

    def a_data_uri(m):
        datos = (carpeta_fuentes / m.group(1)).read_bytes()
        return f"url(data:font/woff2;base64,{base64.b64encode(datos).decode('ascii')})"

    return re.sub(r"url\(([^)]+\.woff2)\)", a_data_uri, css)


def armar_html(ruta_vista: str) -> str:
    vista = Path(ruta_vista)
    html = vista.read_text(encoding="utf-8")
    if ENLACE_FUENTES not in html:
        raise ValueError("view.html ya no enlaza fonts/fonts.css: revisar armar_vista.py")
    estilo = "<style>\n" + _css_con_fuentes_adentro(vista.parent / "fonts") + "\n</style>"
    return html.replace(ENLACE_FUENTES, estilo, 1)
