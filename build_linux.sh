#!/bin/bash
# Build script para crear binary para Linux

echo "[BUILD] Limpiando builds anteriores..."
rm -rf build dist

echo "[BUILD] Compilando para Linux..."
pyinstaller \
  --name=music-downloader \
  --onefile \
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

if [ -f "dist/music-downloader" ]; then
  SIZE=$(ls -lh dist/music-downloader | awk '{print $5}')
  echo "[SUCCESS] Binary creado: dist/music-downloader ($SIZE)"
  exit 0
else
  echo "[ERROR] Build falló"
  exit 1
fi
