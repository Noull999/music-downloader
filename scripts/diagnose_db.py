#!/usr/bin/env python3
"""
Script de diagnóstico para verificar la base de datos.

El .db tiene DOS tablas de descargas independientes, a propósito:
- "downloads"       -> db/history_manager.py (flujo principal, pegar link)
- "sync_downloads"  -> db/history.py (flujo de Sincronizar / likes de SoundCloud)
Se reportan por separado para no confundirlas.
"""
import sqlite3
from pathlib import Path

DB_PATH = Path.home() / ".music_downloader" / "history.db"

if not DB_PATH.exists():
    print(f"❌ Base de datos NO encontrada: {DB_PATH}")
    exit(1)

print(f"[OK] Base de datos encontrada: {DB_PATH}")
print()


def count_table(cursor, table_name: str) -> int | None:
    """Retorna COUNT(*) de la tabla, o None si no existe todavía."""
    try:
        cursor.execute(f"SELECT COUNT(*) FROM {table_name}")
        return cursor.fetchone()[0]
    except sqlite3.OperationalError:
        return None


try:
    conn = sqlite3.connect(str(DB_PATH))
    cursor = conn.cursor()

    # Contar likes
    likes_count = count_table(cursor, "soundcloud_likes") or 0
    print(f"[INFO] Total de likes en DB: {likes_count}")

    # Contar descargas (flujo principal, "pegar link")
    downloads_count = count_table(cursor, "downloads")
    if downloads_count is None:
        print("[INFO] Tabla 'downloads' (flujo principal) aún no existe")
    else:
        print(f"[INFO] Total de descargas registradas (flujo principal): {downloads_count}")

    # Contar descargas (flujo de Sincronizar)
    sync_downloads_count = count_table(cursor, "sync_downloads")
    if sync_downloads_count is None:
        print("[INFO] Tabla 'sync_downloads' (flujo de Sincronizar) aún no existe")
    else:
        print(f"[INFO] Total de descargas registradas (flujo de Sincronizar): {sync_downloads_count}")

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
