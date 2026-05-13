# PyInstaller spec para generar SoundCloudDownloader.exe portable
# Uso: pyinstaller build.spec

import sys
from pathlib import Path

block_cipher = None

a = Analysis(
    ["main.py"],
    pathex=[str(Path(__file__).parent)],
    binaries=[],
    datas=[
        (
            str(Path(sys.prefix) / "Lib" / "site-packages" / "customtkinter"),
            "customtkinter",
        ),
    ],
    hiddenimports=[
        "customtkinter",
        "PIL", "PIL.Image", "PIL.ImageTk",
        "mutagen", "mutagen.id3", "mutagen.mp3",
        "yt_dlp",
        "requests",
        "handlers.soundcloud_handler",
        "handlers.youtube_handler",
    ],
    hookspath=[],
    runtime_hooks=[],
    excludes=[],
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="MusicDownloader",
    debug=False,
    strip=False,
    upx=True,
    console=False,      # sin ventana de consola
    icon=None,          # reemplazar con "icon.ico" si tenés uno
)
