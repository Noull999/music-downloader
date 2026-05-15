"""
Script para debuggear qué devuelve la API de SoundCloud.
"""
import sys
import io
import os
import json

if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

from sync.soundcloud_api import SoundCloudAPIClient
from db.history import DownloadHistory

# Lee credenciales desde el archivo de config (relativo al directorio del script)
config_file = os.path.join(os.path.dirname(__file__), "config.json")

try:
    import json
    with open(config_file) as f:
        config = json.load(f)

    oauth_token = config.get("soundcloud", {}).get("oauth_token", "").strip()
    client_id = config.get("soundcloud", {}).get("client_id", "").strip()

    if not oauth_token or not client_id:
        print("❌ Token OAuth o Client ID vacíos en config.json")
        sys.exit(1)

    print(f"✓ Credenciales leídas")
    print(f"  Token: {oauth_token[:30]}...")
    print(f"  Client ID: {client_id}")

    # Conectar a la API
    api = SoundCloudAPIClient(oauth_token, client_id)

    # Validar credenciales
    user_info = api.validate_credentials()
    print(f"\n✓ Usuario validado: {user_info['username']}")
    print(f"  Total de likes: {user_info['likes_count']}")

    # Obtener últimos 10 likes
    print(f"\n📥 Obteniendo últimos 10 likes...")
    recent = api.get_recent_likes(count=10)

    print(f"\n✓ Obtenidos {len(recent)} likes:\n")
    for i, track in enumerate(recent, 1):
        print(f"{i}. {track.artist} - {track.title}")
        print(f"   URL: {track.url}")
        print(f"   Fecha: {track.created_at}")
        print()

    # Buscar las canciones específicas
    print("\n🔍 Buscando 'woop' y 'moupe'...")
    found_woop = any('woop' in t.title.lower() for t in recent)
    found_moupe = any('moupe' in t.title.lower() for t in recent)

    print(f"  ¿Encontró 'woop'? {'✓ SÍ' if found_woop else '✗ NO'}")
    print(f"  ¿Encontró 'moupe'? {'✓ SÍ' if found_moupe else '✗ NO'}")

    if not found_woop or not found_moupe:
        print("\n⚠️  Las canciones nuevas NO están en los últimos 10 de la API")
        print("   Posible causa: SoundCloud todavía no las ha indexado")
        print("   Solución: Espera 5-10 minutos y vuelve a intentar")

except FileNotFoundError:
    print(f"❌ Archivo no encontrado: {config_file}")
    print("   Asegúrate de haber configurado las credenciales en Configuración")
    sys.exit(1)
except Exception as e:
    print(f"❌ Error: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
