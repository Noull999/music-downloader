#!/usr/bin/env python3
"""
Script de debug para ver exactamente qué devuelve SoundCloud.
Ejecuta: python debug_likes.py
"""
import requests
import json
from sync.soundcloud_api import SoundCloudAPIClient

oauth_token = input("OAuth Token: ").strip()
client_id = input("Client ID: ").strip()

print("\n[*] Creando cliente...")
client = SoundCloudAPIClient(oauth_token, client_id)

print("[*] Validando credenciales...")
user = client.validate_credentials()
print(f"[OK] Usuario: {user['username']}")
print(f"     Likes (según API): {user['likes_count']}\n")

endpoints = [
    "/me/likes/tracks",
    "/me/likes",
    f"/users/{user['id']}/likes",
    f"/users/{user['id']}/likes/tracks",
]

for endpoint in endpoints:
    print(f"\n[*] Probando: {endpoint}...")
    try:
        response = client.session.get(
            f"https://api-v2.soundcloud.com{endpoint}",
            params={
                "client_id": client_id,
                "limit": 20,
                "offset": 0,
            },
            timeout=10
        )
        print(f"    Status: {response.status_code}")

        if response.status_code == 200:
            data = response.json()
            collection = data.get("collection", [])
            print(f"    ✅ Items encontrados: {len(collection)}")

            if collection:
                print(f"    Primer item keys: {list(collection[0].keys())}")
        else:
            print(f"    ❌ Error {response.status_code}")
    except Exception as e:
        print(f"    Error: {e}")
