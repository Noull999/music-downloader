#!/usr/bin/env python
import sqlite3
from pathlib import Path

db_path = Path.home() / '.music_downloader' / 'history.db'
print(f'Database: {db_path}')
print(f'Exists: {db_path.exists()}\n')

conn = sqlite3.connect(db_path)
cursor = conn.cursor()

# Count total
cursor.execute('SELECT COUNT(*) FROM downloads')
total = cursor.fetchone()[0]
print(f'Total downloads: {total}')

# Count SoundCloud
cursor.execute('SELECT COUNT(*) FROM downloads WHERE platform = "soundcloud"')
sc_count = cursor.fetchone()[0]
print(f'SoundCloud likes: {sc_count}')

# Show last 10
print('\nLast 10 imported likes:')
cursor.execute('''
SELECT title, artist, url, download_date
FROM downloads
WHERE platform = "soundcloud"
ORDER BY download_date DESC
LIMIT 10
''')

for i, (title, artist, url, date) in enumerate(cursor.fetchall(), 1):
    print(f'{i}. {artist} - {title}')
    print(f'   URL: {url[:60]}...')
    print(f'   Date: {date}\n')

conn.close()
