#!/usr/bin/env python3
"""
Test interactivo para el modulo sync.
Ejecuta con: python test_sync_interactive.py
"""
import logging
import sys
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)-8s | %(message)s"
)
logger = logging.getLogger(__name__)

sys.path.insert(0, str(Path(__file__).parent))

from sync.soundcloud_api import SoundCloudAPIClient
from sync.duplicate_checker import DuplicateChecker
from sync import match_utils
from db.history import DownloadHistory


def main():
    print("\n" + "#"*70)
    print("#  TEST INTERACTIVO - Modulo SYNC de SoundCloud")
    print("#"*70 + "\n")

    # PASO 1: Pedir credenciales
    print("PASO 1: Extraer y validar credenciales")
    print("-" * 70)
    print("\nNecesitas extraer dos valores de tu navegador:")
    print("  1. OAuth Token: F12 -> Network -> Filtro 'api-v2' -> ")
    print("     Un request -> Headers -> Authorization: 'OAuth 2-XXXXX...'")
    print("  2. Client ID: En la URL del mismo request 'client_id=XXXXXXXX'\n")

    oauth_token = input("Pega tu OAuth token: ").strip()
    client_id = input("Pega tu Client ID: ").strip()

    if not oauth_token or not client_id:
        print("[X] Credenciales vacias, abortando.")
        return

    print("\n[*] Validando credenciales...")
    try:
        client = SoundCloudAPIClient(oauth_token, client_id)
        user_info = client.validate_credentials()
        print(f"[OK] Token valido!")
        print(f"     Usuario: {user_info['username']}")
        print(f"     Nombre: {user_info['full_name']}")
        print(f"     Followers: {user_info['followers_count']}")
        print(f"     Likes: {user_info['likes_count']}")
    except ValueError as e:
        print(f"[X] Token invalido: {e}")
        return
    except Exception as e:
        print(f"[X] Error de conexion: {e}")
        return

    # PASO 2: Obtener likes
    print("\n" + "-"*70)
    print("PASO 2: Obtener tus likes de SoundCloud")
    print("-" * 70)

    count = input("\nCuantos likes queres obtener? (default 5): ").strip()
    count = int(count) if count.isdigit() else 5

    print(f"\n[*] Obteniendo {count} likes...")
    try:
        likes = client.get_recent_likes(count=count)
        print(f"[OK] Obtenidos {len(likes)} likes:\n")

        for i, track in enumerate(likes, 1):
            print(f"{i}. {track.artist} - {track.title}")
            print(f"   URL: {track.url}")
            print(f"   Duracion: {track.duration_ms}ms")
            print(f"   Genero: {track.genre}")
            print()
    except Exception as e:
        print(f"[X] Error obteniendo likes: {e}")
        return

    # PASO 3: Duplicate checker
    print("-"*70)
    print("PASO 3: Probar Duplicate Checker (fuzzy matching)")
    print("-" * 70)

    history = DownloadHistory()
    checker = DuplicateChecker(history)

    print("\n[*] Probando normalizacion de texto:")
    test_cases = [
        "Cafe - La Noche",
        "THE WEEKEND - BLINDING LIGHTS",
        "Nino de Rivera - Todo Bien",
    ]

    for text in test_cases:
        normalized = match_utils.clean_for_match(text)
        print(f"  '{text}'")
        print(f"  -> '{normalized}'")

    # PASO 4: Database
    print("\n" + "-"*70)
    print("PASO 4: Probar Database SQLite")
    print("-" * 70)

    print("\n[*] Registrando tus likes en la DB...")
    for i, track in enumerate(likes[:3], 1):  # Registrar los primeros 3
        history.mark_downloaded(
            url=track.url,
            title=track.title,
            artist=track.artist,
            file_path=f"/local/path/{i}.mp3",
            platform="soundcloud"
        )
        print(f"  [{i}] {track.artist} - {track.title}")

    print("\n[*] Verificando que estan en la DB...")
    for i, track in enumerate(likes[:3], 1):
        is_dup = history.is_downloaded(track.url)
        status = "[OK]" if is_dup else "[X]"
        print(f"  {status} {track.url}")

    print("\n[*] Estadisticas:")
    stats = history.get_stats()
    print(f"  Total tracks en historial: {stats['total_tracks']}")
    print(f"  Total artistas: {stats['total_artists']}")

    print("\n[*] Registrando un evento de sync...")
    history.log_sync(new=3, skipped=2, errors=0)

    last_sync = history.get_last_sync()
    if last_sync:
        print(f"  Ultima sync:")
        print(f"    - Nuevas: {last_sync['new_tracks']}")
        print(f"    - Omitidas: {last_sync['skipped']}")
        print(f"    - Errores: {last_sync['errors']}")
        print(f"    - Timestamp: {last_sync['synced_at']}")

    history.close()

    # FINAL
    print("\n" + "#"*70)
    print("#  [OK] TODOS LOS TESTS PASARON!")
    print("#"*70)
    print("\nProximo paso: Integrar en GUI (sync_window.py)")
    print()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n[X] Cancelado por el usuario")
    except Exception as e:
        print(f"\n[X] Error: {e}")
        import traceback
        traceback.print_exc()
