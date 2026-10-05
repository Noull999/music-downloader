# -*- mode: python ; coding: utf-8 -*-
#
# Empaqueta la interfaz pywebview (main_webview.py), que es la app actual.
import os
import sys
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
    ('analysis', 'analysis'),
    ('config', 'config'),
    ('notifications', 'notifications'),
    ('assets', 'assets'),
]
binaries = []
hiddenimports = [
    'webview',
    'yt_dlp', 'mutagen', 'PIL', 'thefuzz', 'Levenshtein',
    'librosa',  # análisis de BPM/tonalidad (analysis/audio_analysis.py)
]

IS_WIN = sys.platform == 'win32'
IS_MAC = sys.platform == 'darwin'
if IS_WIN:
    hiddenimports += ['webview.platforms.winforms', 'webview.platforms.edgechromium',
                      'clr_loader', 'pythonnet']
if IS_MAC:
    hiddenimports += ['webview.platforms.cocoa']
_EXE_EXT = '.exe' if IS_WIN else ''

# fpcalc (Chromaprint) para huella de audio: scripts/build.py lo descarga a
# build/fpcalc/ antes de invocar PyInstaller. Se empaqueta como carpeta
# 'fpcalc/' junto al resto (no como binary suelto) para que
# analysis/fingerprint.py lo encuentre en sys._MEIPASS/fpcalc/fpcalc.exe.
_fpcalc_bundle = os.path.join('build', 'fpcalc', 'fpcalc' + _EXE_EXT)
if os.path.isfile(_fpcalc_bundle):
    datas.append((_fpcalc_bundle, 'fpcalc'))

# pywebview trae backends por plataforma y assets propios que no se detectan
# siguiendo imports.
_paquetes = ['webview', 'yt_dlp']
if IS_WIN:
    _paquetes += ['win11toast', 'winrt']
for _pkg in _paquetes:
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
_ffmpeg_bundle = os.path.join('build', 'ffmpeg', 'ffmpeg' + _EXE_EXT)
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

if IS_MAC:
    # macOS: .app (onedir). Un onefile dentro de un .app se re-extrae en cada
    # arranque y Gatekeeper lo trata peor.
    exe = EXE(
        pyz,
        a.scripts,
        [],
        exclude_binaries=True,
        name='MusicDownloader',
        debug=False,
        strip=False,
        upx=False,
        console=False,
        argv_emulation=False,
        target_arch=None,
        codesign_identity=None,
        entitlements_file=None,
    )
    coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name='MusicDownloader')
    app = BUNDLE(
        coll,
        name='MusicDownloader.app',
        icon='assets/icon.png',
        bundle_identifier='com.musicdownloader.app',
        info_plist={
            'CFBundleDisplayName': 'Music Downloader',
            'NSHighResolutionCapable': True,
        },
    )
else:
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
