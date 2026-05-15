#!/usr/bin/env python3
"""
Test para verificar que el endpoint actualizado funciona.
Usa la clase SoundCloudAPIClient ya corregida.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from sync.soundcloud_api import SoundCloudAPIClient

print("\n" + "="*60)
print("TEST - Endpoint actualizado de likes")
print("="*60 + "\n")

oauth_token = input("OAuth Token: ").strip()
client_id = input("Client ID: ").strip()

print("\n[*] Validando credenciales...")
client = SoundCloudAPIClient(oauth_token, client_id)

try:
    user = client.validate_credentials()
    print(f"[OK] Usuario: {user['username']}")
    print(f"     ID: {user['id']}")
    print(f"     Likes (según /me): {user['likes_count']}\n")
except Exception as e:
    print(f"[X] Error: {e}")
    sys.exit(1)

print("[*] Obteniendo últimos 10 likes...")
try:
    likes = client.get_recent_likes(count=10)
    print(f"[OK] Obtenidos {len(likes)} likes:\n")

    for i, track in enumerate(likes, 1):
        print(f"{i}. {track.artist} - {track.title}")
        print(f"   URL: {track.url}")
        print(f"   ID: {track.id}")

    if len(likes) > 0:
        print("\n✅ FUNCIONA - El endpoint actualizado obtiene likes!")
    else:
        print("\n⚠️  No hay likes (pero no hay error)")

except Exception as e:
    print(f"[X] Error: {e}")
    import traceback
    traceback.print_exc()
