"""
Script para reconstruir historial basado en archivos existentes en una carpeta.
Uso: python rebuild_history.py [ruta_a_carpeta_musica]
     Si no se proporciona ruta, usa ~/Music por defecto.

Escribe en la tabla "sync_downloads" (la misma que usa db/history.py /
SyncManager para el flujo de Sincronizar). No toca la tabla "downloads"
de db/history_manager.py, que es la que usa el flujo principal de
"pegar link" — ambas viven en el mismo .db pero en tablas separadas
a propósito, para no pisarse los esquemas entre sí.
"""
import sqlite3
import os
import sys
from pathlib import Path
from datetime import datetime

# Configurar encoding para Windows
if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# Usar argumento de línea de comandos o ~/Music por defecto
MUSIC_FOLDER = sys.argv[1] if len(sys.argv) > 1 else os.path.expanduser("~/Music")
DB_PATH = Path.home() / ".music_downloader" / "history.db"

def rebuild_history():
    """Reconstruye el historial escaneando la carpeta de música."""
    if not os.path.exists(MUSIC_FOLDER):
        print(f"❌ Carpeta no encontrada: {MUSIC_FOLDER}")
        return

    # Crear DB si no existe
    DB_PATH.parent.mkdir(exist_ok=True, parents=True)
    conn = sqlite3.connect(str(DB_PATH))
    cursor = conn.cursor()

    # Crear tabla si no existe
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS sync_downloads (
            url         TEXT PRIMARY KEY,
            title       TEXT NOT NULL,
            artist      TEXT,
            file_path   TEXT,
            platform    TEXT DEFAULT 'soundcloud',
            downloaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()

    # Escanear archivos
    audio_extensions = ('.mp3', '.m4a', '.flac', '.ogg', '.wav')
    files_found = 0
    files_added = 0

    for root, dirs, files in os.walk(MUSIC_FOLDER):
        for filename in files:
            if filename.lower().endswith(audio_extensions):
                file_path = os.path.join(root, filename)
                files_found += 1

                # Extraer artist - title del nombre del archivo
                name_without_ext = os.path.splitext(filename)[0]

                if " - " in name_without_ext:
                    parts = name_without_ext.split(" - ", 1)
                    artist = parts[0].strip()
                    title = parts[1].strip()
                else:
                    artist = "Unknown"
                    title = name_without_ext.strip()

                # Crear URL fake (necesaria como primary key)
                fake_url = f"file://{file_path}"

                try:
                    cursor.execute("""
                        INSERT OR IGNORE INTO sync_downloads
                        (url, title, artist, file_path, platform, downloaded_at)
                        VALUES (?, ?, ?, ?, 'soundcloud', ?)
                    """, (fake_url, title, artist, file_path, datetime.now().isoformat()))
                    files_added += 1
                    print(f"[OK] {artist} - {title}")
                except sqlite3.Error as e:
                    print(f"[ERROR] Error insertando {filename}: {e}")

    conn.commit()
    conn.close()

    print(f"\n[SUCCESS] Historial reconstruido:")
    print(f"   Archivos encontrados: {files_found}")
    print(f"   Archivos agregados al historial: {files_added}")
    print(f"   Base de datos: {DB_PATH}")

if __name__ == "__main__":
    rebuild_history()
