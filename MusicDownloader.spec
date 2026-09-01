# -*- mode: python ; coding: utf-8 -*-
#
# Empaqueta la interfaz pywebview (main_webview.py), que es la app actual.
# La GUI vieja de CustomTkinter (main.py) sigue en el repo y se puede correr
# con `python main.py`, pero ya no es la que se distribuye.
import os
from PyInstaller.utils.hooks import collect_all

# webview_app/ lleva view.html (la interfaz entera), así que es obligatorio.
datas = [
    ('webview_app', 'webview_app'),
    ('handlers', 'handlers'),
    ('gui', 'gui'),
    ('db', 'db'),
    ('quality', 'quality'),
    ('utils', 'utils'),
    ('sync', 'sync'),
    ('config', 'config'),
    ('notifications', 'notifications'),
    ('assets', 'assets'),
]
binaries = []
hiddenimports = [
    'webview', 'webview.platforms.winforms', 'webview.platforms.edgechromium',
    'clr_loader', 'pythonnet',
    'yt_dlp', 'mutagen', 'PIL', 'thefuzz', 'Levenshtein',
    'customtkinter',  # gui/ sigue importándose desde utils compartidos
]

# pywebview trae backends por plataforma y assets propios que no se detectan
# siguiendo imports.
for _pkg in ('webview', 'customtkinter', 'yt_dlp', 'win11toast', 'winrt'):
    try:
        _d, _b, _h = collect_all(_pkg)
        datas += _d
        binaries += _b
        hiddenimports += _h
    except Exception:
        # Paquete opcional ausente: la app degrada sola (p.ej. notificaciones)
        pass

# ffmpeg embebido (onefile): scripts/build.py lo descarga/copia a build/ffmpeg
# antes de invocar PyInstaller. Se extrae a sys._MEIPASS/ffmpeg/ en runtime.
_ffmpeg_bundle = os.path.join('build', 'ffmpeg', 'ffmpeg.exe')
if os.path.isfile(_ffmpeg_bundle):
    binaries.append((_ffmpeg_bundle, 'ffmpeg'))


a = Analysis(
    ['main_webview.py'],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='MusicDownloader',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='assets/icon.ico',
)
