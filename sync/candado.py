"""
Candado para que nunca corran dos sincronizaciones a la vez.

La sincronizacion automatica (tarea programada / launchd) es otro proceso
distinto de la app abierta: si alguien pulsaba "Sincronizar" justo cuando
corria la automatica, las dos bajaban los mismos temas y una le borraba el
archivo temporal a la otra (visto en un Mac: "No such file or directory").

Se usa el bloqueo de archivos del sistema operativo, que se libera solo si el
proceso termina o se cae: no quedan candados "pegados".
"""
import logging
import os
import sys
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

RUTA_POR_DEFECTO = Path.home() / ".music_downloader" / "sync.lock"


class CandadoDeSync:
    def __init__(self, ruta: Optional[Path] = None):
        self.ruta = Path(ruta or RUTA_POR_DEFECTO)
        self._archivo = None

    def tomar(self) -> bool:
        """True si se obtuvo; False si otra sincronizacion lo tiene."""
        if self._archivo is not None:
            return True
        self.ruta.parent.mkdir(parents=True, exist_ok=True)
        archivo = open(self.ruta, "a+")
        try:
            if sys.platform == "win32":
                import msvcrt
                archivo.seek(0)
                msvcrt.locking(archivo.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(archivo.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            archivo.close()
            return False
        self._archivo = archivo
        try:
            archivo.seek(0)
            archivo.truncate()
            archivo.write(str(os.getpid()))
            archivo.flush()
        except OSError:
            pass
        return True

    def soltar(self) -> None:
        archivo, self._archivo = self._archivo, None
        if archivo is None:
            return
        try:
            if sys.platform == "win32":
                import msvcrt
                archivo.seek(0)
                msvcrt.locking(archivo.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(archivo.fileno(), fcntl.LOCK_UN)
        except OSError:
            pass
        finally:
            archivo.close()
