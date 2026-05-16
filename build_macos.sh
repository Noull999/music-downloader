#!/bin/bash
# Build script para crear MusicDownloader.app (macOS)

echo "[BUILD] Limpiando builds anteriores..."
rm -rf build dist

echo "[BUILD] Compilando para macOS..."
pyinstaller \
  --name=MusicDownloader \
  --onefile \
  --windowed \
  --osx-bundle-identifier=com.musicdownloader.app \
  --add-data=config.json:. \
  --add-data=handlers:handlers \
  --add-data=gui:gui \
  --add-data=db:db \
  --add-data=quality:quality \
  --add-data=utils:utils \
  --hidden-import=customtkinter \
  --hidden-import=yt_dlp \
  --hidden-import=mutagen \
  --hidden-import=pydub \
  --hidden-import=PIL \
  --collect-all=customtkinter \
  --collect-all=yt_dlp \
  main.py

if [ -d "dist/MusicDownloader.app" ]; then
  SIZE=$(du -sh dist/MusicDownloader.app | cut -f1)
  echo "[SUCCESS] MusicDownloader.app creado ($SIZE)"
  exit 0
else
  echo "[ERROR] Build falló"
  exit 1
fi
