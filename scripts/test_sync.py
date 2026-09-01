#!/usr/bin/env python3
"""
Test basico del modulo de sync.
Valida:
1. validate_credentials() con token real
2. get_likes() retorna datos
3. duplicate_checker con nombres normalizados
4. history.py guarda/recupera datos
"""
import logging
import sys
from pathlib import Path

# Setup logging
logging.basicConfig(
    level=logging.DEBUG,
    format="%(levelname)-8s | %(name)s | %(message)s"
)
logger = logging.getLogger(__name__)

# Asegurar que podemos importar modules del proyecto
sys.path.insert(0, str(Path(__file__).parent))

from sync.soundcloud_api import SoundCloudAPIClient
from sync.duplicate_checker import DuplicateChecker
from sync import match_utils
from db.history import DownloadHistory


def test_credentials():
    """Test 1: Validar credenciales."""
    print("\n" + "="*60)
    print("TEST 1: Validar credenciales de SoundCloud")
    print("="*60)

    oauth_token = input("\nPega tu OAuth token (ej: 'OAuth 2-XXXXX-...'): ").strip()
    client_id = input("Pega tu Client ID (ej: 'XXXXXXXX'): ").strip()

    if not oauth_token or not client_id:
        print("[X] Credenciales invalidas")
        return None

    try:
        client = SoundCloudAPIClient(oauth_token, client_id)
        user_info = client.validate_credentials()
        print(f"\n[OK] Credenciales validas!")
        print(f"   Usuario: {user_info['username']}")
        print(f"   Nombre: {user_info['full_name']}")
        print(f"   Likes: {user_info['likes_count']}")
        return client
    except ValueError as e:
        print(f"\n[X] Error de token: {e}")
        return None
    except Exception as e:
        print(f"\n[X] Error de conexion: {e}")
        return None


def test_get_likes(client):
    """Test 2: Obtener likes."""
    print("\n" + "="*60)
    print("TEST 2: Obtener likes (primeros 5)")
    print("="*60)

    try:
        likes = client.get_recent_likes(count=5)
        print(f"\n[OK] Obtenidos {len(likes)} likes:")
        for i, track in enumerate(likes, 1):
            print(f"   {i}. {track.artist} - {track.title}")
            print(f"      ID: {track.id} | URL: {track.url}")
            print(f"      Duracion: {track.duration_ms}ms | Genero: {track.genre}")
        return likes
    except Exception as e:
        print(f"\n[X] Error obteniendo likes: {e}")
        return []


def test_duplicate_checker(likes):
    """Test 3: Duplicate checker."""
    print("\n" + "="*60)
    print("TEST 3: Duplicate Checker (busqueda fuzzy)")
    print("="*60)

    history = DownloadHistory()
    checker = DuplicateChecker(history)

    # Test casos especiales
    test_cases = [
        ("Cafe - La Noche", "cafe la noche"),      # Tildes
        ("Nino - Juegame todo", "nino juegame todos"),  # Acentos
        ("THE WEEKEND - BLINDING LIGHTS", "the weekend blinding lights"),  # Mayusculas
    ]

    print("\nPruebas de normalizacion:")
    for original, normalized in test_cases:
        norm = match_utils.clean_for_match(original)
        print(f"   {original}")
        print(f"   -> {norm}")
        assert norm == normalized, f"Normalizacion incorrecta!"
        print("   [OK]")

    # Test con un archivo simulado en /tmp
    import tempfile
    import os

    with tempfile.TemporaryDirectory() as tmpdir:
        # Crear archivos simulados
        test_files = [
            "BadBunny_Titi_Me_Pregunto.mp3",
            "bad_bunny-titi_me_pregunto.mp3",
            "Bad Bunny - Titi Me Pregunto.mp3",
        ]

        for filename in test_files:
            Path(tmpdir, filename).touch()

        print(f"\n[OK] Creados {len(test_files)} archivos de prueba")

        # Probar busqueda fuzzy
        print("\nPruebas de busqueda fuzzy:")
        test_queries = [
            ("Titi Me Pregunto", "Bad Bunny", True),   # Debe encontrar
            ("TITI ME PREGUNTO", "bad bunny", True),   # Mayusculas
            ("Xxxx", "Yyyy", False),                   # No debe encontrar
        ]

        for title, artist, should_find in test_queries:
            similar = checker._find_similar_file(title, artist, tmpdir)
            found = similar is not None
            status = "[OK]" if found == should_find else "[X]"
            print(f"   {status} {artist} - {title}")
            if found:
                print(f"       Encontrado: {similar}")


def test_history():
    """Test 4: Database history."""
    print("\n" + "="*60)
    print("TEST 4: Database History")
    print("="*60)

    history = DownloadHistory()

    # Simular descargas
    test_downloads = [
        ("https://soundcloud.com/artist1/track1", "Track 1", "Artist 1", "/path/file1.mp3"),
        ("https://soundcloud.com/artist2/track2", "Track 2", "Artist 2", "/path/file2.mp3"),
        ("https://soundcloud.com/artist3/track3", "Track 3", "Artist 3", "/path/file3.mp3"),
    ]

    print("\nRegistrando descargas simuladas:")
    for url, title, artist, file_path in test_downloads:
        history.mark_downloaded(url, title, artist, file_path)
        print(f"   [OK] {artist} - {title}")

    # Verificar que estan en la DB
    print("\nVerificando descargas en historial:")
    for url, title, artist, _ in test_downloads:
        is_dup = history.is_downloaded(url)
        status = "[OK]" if is_dup else "[X]"
        print(f"   {status} {url}")

    # Stats
    stats = history.get_stats()
    print(f"\nEstadisticas:")
    print(f"   Total tracks: {stats['total_tracks']}")
    print(f"   Total artistas: {stats['total_artists']}")

    # Log sync
    history.log_sync(new=2, skipped=1, errors=0)
    last_sync = history.get_last_sync()
    if last_sync:
        print(f"\nUltima sincronizacion:")
        print(f"   Nuevas: {last_sync['new_tracks']}")
        print(f"   Omitidas: {last_sync['skipped']}")
        print(f"   Errores: {last_sync['errors']}")

    history.close()


def main():
    print("\n" + "#"*60)
    print("#  TEST DE MODULO SYNC - Music Downloader")
    print("#"*60)

    # Test 1: Credenciales
    client = test_credentials()
    if not client:
        print("\n[X] No se pueden continuar sin credenciales validas")
        return

    # Test 2: Obtener likes
    likes = test_get_likes(client)
    if not likes:
        print("\n[!] No se obtuvieron likes (puede ser que tengas pocos en tu cuenta)")

    # Test 3: Duplicate checker
    test_duplicate_checker(likes)

    # Test 4: Database
    test_history()

    print("\n" + "#"*60)
    print("#  [OK] TODOS LOS TESTS COMPLETADOS")
    print("#"*60 + "\n")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n[X] Cancelado por el usuario")
    except Exception as e:
        print(f"\n[X] Error no esperado: {e}")
        import traceback
        traceback.print_exc()
