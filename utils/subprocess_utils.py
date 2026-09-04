"""
Flags para lanzar subprocesos sin ventana visible en Windows.

Sin esto, cada llamada a subprocess.run/Popen desde un .exe empaquetado sin
consola (console=False) hace que Windows le abra una ventana de cmd propia
a CADA proceso hijo (fpcalc, ffmpeg...), porque el proceso hijo no hereda
"ausencia de consola" del padre, la crea la suya. Con una sincronización
bajando varias canciones —cada una dispara fpcalc para el chequeo de
duplicados y ffmpeg para el post-proceso— eso se traduce en una ventana
negra apareciendo y desapareciendo varias veces por segundo, que además
le roba el foco al teclado.
"""
import subprocess
import sys

NO_WINDOW: int = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
