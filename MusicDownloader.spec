# -*- mode: python ; coding: utf-8 -*-
import os
from PyInstaller.utils.hooks import collect_all

datas = [('config.json', '.'), ('handlers', 'handlers'), ('gui', 'gui'), ('db', 'db'), ('quality', 'quality'), ('utils', 'utils'), ('assets', 'assets')]
binaries = []
hiddenimports = ['customtkinter', 'yt_dlp', 'mutagen', 'pydub', 'PIL']
tmp_ret = collect_all('customtkinter')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
tmp_ret = collect_all('yt_dlp')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
tmp_ret = collect_all('win11toast')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
tmp_ret = collect_all('winrt')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]

# ffmpeg embebido (onefile): scripts/build.py lo descarga/copia a build/ffmpeg
# antes de invocar PyInstaller. Se extrae a sys._MEIPASS/ffmpeg/ en runtime.
_ffmpeg_bundle = os.path.join('build', 'ffmpeg', 'ffmpeg.exe')
if os.path.isfile(_ffmpeg_bundle):
    binaries.append((_ffmpeg_bundle, 'ffmpeg'))


a = Analysis(
    ['main.py'],
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
