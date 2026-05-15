#!/usr/bin/env python3
"""
Debug script to verify which files are detected as duplicates.
Shows exactly which tracks match which files in your download folder.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from sync.soundcloud_api import SoundCloudAPIClient
from sync.duplicate_checker import DuplicateChecker
from db.history import DownloadHistory

oauth_token = input("OAuth Token: ").strip()
client_id = input("Client ID: ").strip()
download_folder = input("Download folder path: ").strip()

print("\n[*] Inicializando...")
client = SoundCloudAPIClient(oauth_token, client_id)
history = DownloadHistory()
checker = DuplicateChecker(history)

print("[*] Validando credenciales...")
try:
    user = client.validate_credentials()
    print(f"[OK] Usuario: {user['username']}")
except Exception as e:
    print(f"[X] Error: {e}")
    sys.exit(1)

print(f"[*] Obteniendo likes...")
try:
    all_likes = client.get_likes()
    print(f"[OK] Obtenidos {len(all_likes)} likes\n")
except Exception as e:
    print(f"[X] Error: {e}")
    sys.exit(1)

print(f"[*] Analizando duplicados en: {download_folder}\n")
print("="*80)

new_tracks, duplicates = checker.get_new_tracks(all_likes, download_folder)

print(f"\n📊 RESUMEN:")
print(f"  Total likes: {len(all_likes)}")
print(f"  Duplicados encontrados: {len(duplicates)}")
print(f"  Nuevos para descargar: {len(new_tracks)}")

if duplicates:
    print(f"\n📋 DUPLICADOS DETECTADOS:")
    print("-" * 80)

    for i, (track, reason) in enumerate(duplicates, 1):
        print(f"\n{i}. {track.artist} - {track.title}")
        print(f"   Razón: {reason}")
        print(f"   URL: {track.url}")

print("\n" + "="*80)
print(f"\n✅ Verifica que estos {len(duplicates)} archivos existen en tu carpeta")
print("Si ves archivos que NO existen, aumenta el threshold de similitud en duplicate_checker.py")
