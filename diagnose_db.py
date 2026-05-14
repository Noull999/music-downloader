#!/usr/bin/env python3
"""Script de diagnóstico para verificar la base de datos."""
import sqlite3
from pathlib import Path

DB_PATH = Path.home() / ".music_downloader" / "history.db"

if not DB_PATH.exists():
    print(f"❌ Base de datos NO encontrada: {DB_PATH}")
    exit(1)

print(f"[OK] Base de datos encontrada: {DB_PATH}")
print()

try:
    conn = sqlite3.connect(str(DB_PATH))
    cursor = conn.cursor()

    # Contar likes
    cursor.execute("SELECT COUNT(*) FROM soundcloud_likes")
    likes_count = cursor.fetchone()[0]
    print(f"[INFO] Total de likes en DB: {likes_count}")

    # Contar descargas
    cursor.execute("SELECT COUNT(*) FROM downloads")
    downloads_count = cursor.fetchone()[0]
    print(f"[INFO] Total de descargas registradas: {downloads_count}")

    # Mostrar los primeros likes si hay
    if likes_count > 0:
        print(f"\n[LIKES] Primeros 5 likes:")
        cursor.execute(
            "SELECT id, title, artist FROM soundcloud_likes LIMIT 5"
        )
        for row in cursor.fetchall():
            print(f"  - {row[1]} ({row[2]})")

        if likes_count > 5:
            print(f"  ... y {likes_count - 5} mas")
    else:
        print("\n[WARNING] No hay likes guardados en la base de datos!")
        print("    Intenta sincronizar primero desde la aplicacion.")

    conn.close()

except sqlite3.Error as e:
    print(f"❌ Error en base de datos: {e}")
    exit(1)
