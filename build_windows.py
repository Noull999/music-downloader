#!/usr/bin/env python3
"""
Build script para crear music_downloader.exe con PyInstaller
"""
import os
import shutil
import subprocess
import sys

def build_exe():
    """Genera executable para Windows"""

    # Limpiar builds anteriores
    for folder in ['build', 'dist']:
        if os.path.exists(folder):
            shutil.rmtree(folder)

    cmd = [
        'pyinstaller',
        '--name=MusicDownloader',
        '--onefile',
        '--windowed',
        '--icon=NONE',
        '--add-data=config.json:.',
        '--add-data=handlers:handlers',
        '--add-data=gui:gui',
        '--add-data=db:db',
        '--add-data=quality:quality',
        '--add-data=utils:utils',
        '--hidden-import=customtkinter',
        '--hidden-import=yt_dlp',
        '--hidden-import=mutagen',
        '--hidden-import=pydub',
        '--hidden-import=PIL',
        '--collect-all=customtkinter',
        '--collect-all=yt_dlp',
        'main.py'
    ]

    print("[BUILD] Compilando MusicDownloader.exe...")
    result = subprocess.run(cmd, capture_output=False)

    if result.returncode == 0:
        exe_path = os.path.join('dist', 'MusicDownloader.exe')
        if os.path.exists(exe_path):
            size_mb = os.path.getsize(exe_path) / (1024*1024)
            print(f"[SUCCESS] {exe_path} creado ({size_mb:.1f}MB)")
            return True

    print("[ERROR] Build falló")
    return False

if __name__ == '__main__':
    success = build_exe()
    sys.exit(0 if success else 1)
