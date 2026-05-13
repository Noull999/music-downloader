# Módulo de Sincronización de Likes de SoundCloud

## Descripción

El módulo `sync/` automatiza la descarga de tus likes de SoundCloud:

1. **Lee tus likes** vía API interna de SoundCloud (sin Playwright/Selenium)
2. **Detecta duplicados** inteligentemente (fuzzy matching de nombres + historial)
3. **Descarga solo lo nuevo** usando el handler existente de SoundCloud
4. **Auto-sync en background** cada N minutos sin bloquear la GUI
5. **Notificaciones del sistema** cuando termina

## Estructura

```
sync/
├── soundcloud_api.py      # Cliente API interna de SoundCloud
├── duplicate_checker.py   # Detección inteligente de duplicados
├── sync_manager.py        # Orquestador principal
└── scheduler.py           # Auto-sync en background

db/
└── history.py            # SQLite historial de descargas

notifications/
└── notifier.py           # Notificaciones del sistema
```

## Paso 1: Obtener Credenciales

Necesitás extraer dos valores de tu navegador:

### 1. OAuth Token

```
1. Abre https://soundcloud.com en Chrome/Firefox
2. Inicia sesión
3. Presiona F12 (DevTools)
4. Ve a Network
5. Escribe "api-v2" en el filtro
6. Recarga la página (F5)
7. Haz click en cualquier request (ej: me/likes/tracks)
8. En "Request Headers" busca "Authorization"
9. Copia el valor: "OAuth 2-XXXXX-XXXXX-XXXXXXXXXX"
```

### 2. Client ID

```
1. Mismo lugar, Network, cualquier request a api-v2
2. Mira la URL del request
3. Busca "client_id=XXXXXXXX"
4. Copia solo la parte alfanumérica
```

⚠️ **NO compartas estos valores.** Son como contraseñas.

## Paso 2: Test Básico

Ejecuta el script de test para validar credenciales:

```bash
python test_sync.py
```

Te pedirá:
- OAuth Token
- Client ID

Luego verificará:
1. ✓ Token válido
2. ✓ Obtiene tus likes reales
3. ✓ Fuzzy matcher funciona con tildes
4. ✓ Database SQLite funciona

## Paso 3: Uso en Código

### Opción A: Sincronización manual (una vez)

```python
from sync.sync_manager import SyncManager
from handlers.soundcloud_handler import SoundCloudHandler
from pathlib import Path

oauth_token = "OAuth 2-XXXXX-..."
client_id = "XXXXXXXX"
download_folder = str(Path.home() / "Música" / "SoundCloud")

downloader = SoundCloudHandler()
manager = SyncManager(oauth_token, client_id, download_folder, downloader)

# Sincronizar
def on_progress(pct, msg):
    print(f"[{pct}%] {msg}")

results = manager.sync_once(progress_callback=on_progress)
print(f"✓ {results['new']} descargadas")
print(f"✓ {results['skipped']} omitidas")
print(f"⚠️ {results['errors']} errores")
```

### Opción B: Auto-sync en background

```python
from sync.sync_manager import SyncManager
from sync.scheduler import AutoSyncScheduler

manager = SyncManager(oauth_token, client_id, download_folder, downloader)
scheduler = AutoSyncScheduler(manager, interval_minutes=30)

# Callbacks para actualizar GUI
def on_sync_start():
    print("🔄 Sincronización iniciada...")

def on_sync_complete(results):
    print(f"✓ Completado: +{results['new']} | -{results['skipped']}")

scheduler.on_sync_start = on_sync_start
scheduler.on_sync_complete = on_sync_complete

# Iniciar
scheduler.start()

# ... la app sigue funcionando ...

# Detener
scheduler.stop()
```

### Opción C: Validar credenciales

```python
from sync.sync_manager import SyncManager

manager = SyncManager(oauth_token, client_id, download_folder, downloader)

try:
    manager.validate_credentials()
    print("✓ Token válido")
except ValueError as e:
    print(f"❌ Token inválido: {e}")
```

## API Reference

### `SoundCloudAPIClient`

```python
from sync.soundcloud_api import SoundCloudAPIClient

client = SoundCloudAPIClient(oauth_token, client_id)

# Validar token
user_info = client.validate_credentials()
# → {"id": 123, "username": "tu_user", "likes_count": 45, ...}

# Obtener todos los likes (paginado automáticamente)
all_likes = client.get_likes()
# → [SoundCloudTrack(...), SoundCloudTrack(...), ...]

# Obtener solo los últimos N likes (más rápido)
recent = client.get_recent_likes(count=10)
```

### `DuplicateChecker`

```python
from sync.duplicate_checker import DuplicateChecker
from db.history import DownloadHistory

history = DownloadHistory()
checker = DuplicateChecker(history)

# Verificar si es duplicado
is_dup, reason = checker.is_duplicate(
    track_url="https://soundcloud.com/artist/track",
    track_title="Track Title",
    artist="Artist Name",
    folder="/path/to/downloads"
)

# Filtrar lista
new_tracks, duplicates = checker.get_new_tracks(all_likes, "/path/downloads")
# → (new_tracks: list, duplicates: list[(track, reason)])
```

### `DownloadHistory`

```python
from db.history import DownloadHistory

history = DownloadHistory()

# Verificar si se descargó
if history.is_downloaded("https://soundcloud.com/.../track"):
    print("Ya descargada")

# Registrar descarga
history.mark_downloaded(
    url="https://soundcloud.com/.../track",
    title="Track Title",
    artist="Artist",
    file_path="/local/path/file.mp3",
    platform="soundcloud"
)

# Obtener stats
stats = history.get_stats()
# → {"total_tracks": 312, "total_artists": 89, "by_platform": {"soundcloud": 200, ...}}

# Últimas sync
last = history.get_last_sync()
# → {"synced_at": "2025-05-13 10:30:00", "new_tracks": 3, "skipped": 47, "errors": 0}

# Log una sincronización
history.log_sync(new=3, skipped=47, errors=0)
```

### `SyncManager`

```python
from sync.sync_manager import SyncManager

manager = SyncManager(oauth_token, client_id, download_folder, downloader)

# Validar credenciales
manager.validate_credentials()  # Lanza ValueError si token inválido

# Sincronizar completa
results = manager.sync_once(progress_callback=lambda pct, msg: print(f"{pct}% {msg}"))
# → {
#     'new': 3,              # Descargadas
#     'skipped': 47,         # Duplicados
#     'errors': 0,           # Errores
#     'tracks': [...],       # Lista de SoundCloudTrack descargadas
#     'duplicates': [...]    # Lista de (track, reason) omitidas
# }

# Sincronización rápida (últimos N likes)
results = manager.sync_recent(count=10)

# Detener sync en curso
manager.stop()

# Verificar si está sincronizando
if manager.is_syncing():
    print("Sincronización en curso...")

# Obtener stats
stats = manager.get_history_stats()
last_sync = manager.get_last_sync_info()
```

### `AutoSyncScheduler`

```python
from sync.scheduler import AutoSyncScheduler

scheduler = AutoSyncScheduler(manager, interval_minutes=30)

# Callbacks
scheduler.on_sync_start = lambda: print("Iniciando...")
scheduler.on_sync_complete = lambda results: print(f"+{results['new']}")

# Iniciar background
scheduler.start()

# Cambiar intervalo (sin reiniciar)
scheduler.set_interval(60)  # Ahora cada 60 minutos

# Detener
scheduler.stop()

# Estado
if scheduler.is_running:
    print("Scheduler activo")
```

### `Notifier`

```python
from notifications.notifier import Notifier

# Notificación genérica
Notifier.notify(
    title="Título",
    message="Mensaje",
    timeout=5  # segundos
)

# Notificación de sincronización
Notifier.notify_sync_complete(
    new=3,
    skipped=47,
    errors=0
)

# Notificación de like nuevo
Notifier.notify_new_like_detected(
    title="Track Title",
    artist="Artist"
)

# Notificación de error
Notifier.notify_error(
    error_title="Token inválido",
    error_msg="Renueva desde DevTools (F12)"
)
```

## Integración en GUI (Próximo Paso)

Cuando esté listo, crearemos `gui/sync_window.py` que incluya:

```
┌─ Sincronizar Mis Likes ─────────┐
│ Token OAuth: [***...] [Verificar]│
│ Client ID:   [***...] [Copiar]   │
│ Carpeta:     [/path] [Cambiar]   │
│                                   │
│ ☑ Auto-sync cada 30 minutos       │
│ Estado: 🟢 Activo                 │
│                                   │
│ ▓▓▓▓▓▓░░ 60% Descargando...       │
│                                   │
│ [ ▶ Sincronizar ahora ] [ ⏹ ]     │
│ [ Últimos 10 ]          [ Todos ] │
└─────────────────────────────────┘
```

## Troubleshooting

### "Token inválido o expirado"

→ Extrae uno nuevo desde soundcloud.com (F12 → Network)

### "No se encuentran likes"

→ Verifica que tienes likes en tu cuenta: https://soundcloud.com/you/likes

### "Error de conexión"

→ Verifica tu internet y que SoundCloud no esté bloqueado

### "¿Por qué demora tanto?"

→ La API de SoundCloud pone delays entre requests para no saturarse
  → Con 500+ likes puede tomar 5-10 minutos

## Notas Técnicas

- **Sin Playwright/Selenium**: Solo requests HTTP, mucho más rápido y confiable
- **Thread-safe**: Puede correr en background sin bloquear GUI
- **Fuzzy matching**: Tolera tildes, mayúsculas, espacios (ej: "Café la noche" ≈ "cafe la noche")
- **Rate limiting**: Maneja automáticamente si SoundCloud limita requests (429)
- **Historial persistente**: Usa SQLite, sobrevive reinicios de la app
- **Modular**: Cada componente es independiente y testeable

## Ejemplo Completo

Ver `test_sync.py` para un ejemplo de uso de todos los componentes.
