#!/usr/bin/env python3
"""
Lista todos los archivos de audio en tu carpeta de descargas.
Ayuda a verificar que la carpeta es la correcta y ve cuántos archivos hay realmente.
"""
import sys
from pathlib import Path

download_folder = input("Ruta de tu carpeta de descargas: ").strip()

if not Path(download_folder).exists():
    print(f"❌ Carpeta no existe: {download_folder}")
    sys.exit(1)

audio_extensions = {'.mp3', '.m4a', '.flac', '.wav', '.ogg', '.opus', '.aac'}
audio_files = []

print(f"\n[*] Buscando archivos de audio en: {download_folder}\n")

for file_path in Path(download_folder).rglob('*'):
    if file_path.is_file() and file_path.suffix.lower() in audio_extensions:
        audio_files.append(file_path)

print(f"✅ Encontrados {len(audio_files)} archivos de audio:\n")

for i, file_path in enumerate(sorted(audio_files), 1):
    print(f"{i:3d}. {file_path.name}")
    if i % 20 == 0:
        print()

print(f"\n📊 TOTAL: {len(audio_files)} archivos")
print(f"\nEsperabas {210} archivos. Si hay menos, verifica que estés")
print(f"apuntando a la carpeta correcta donde SoundCloud guardó tus canciones.")
