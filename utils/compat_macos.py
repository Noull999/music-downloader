"""
Compatibilidad de pywebview con macOS anteriores a 11.3 (Catalina y antes).

pywebview 6 decide cada navegacion llamando a
`WKNavigationAction.shouldPerformDownload()`, que Apple agrego en macOS 11.3.
En Catalina esa llamada falla, el delegado se corta sin autorizar la carga y
la ventana queda en negro para siempre (visto en un MacBook Pro 2012 con
10.15.8: "Completion handler passed to ...decidePolicyForNavigationAction...
was not called").

Se le agrega a WKNavigationAction un `shouldPerformDownload` que responde
"no" (lo mismo que dice un macOS nuevo para cualquier navegacion normal), solo
si el sistema no lo trae.
"""
import logging
import sys

logger = logging.getLogger(__name__)


def aplicar() -> bool:
    """Devuelve True si hizo falta agregar el metodo."""
    if sys.platform != "darwin":
        return False
    try:
        import objc
        import WebKit
    except ImportError:
        return False
    if WebKit.WKNavigationAction.instancesRespondToSelector_(b"shouldPerformDownload"):
        return False

    class WKNavigationAction(objc.Category(WebKit.WKNavigationAction)):
        @objc.typedSelector(b"Z@:")
        def shouldPerformDownload(self):
            return False

    logger.info("Compatibilidad: agregado WKNavigationAction.shouldPerformDownload (macOS < 11.3)")
    return True
