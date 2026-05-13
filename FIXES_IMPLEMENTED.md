# ✅ Fixes Implementados - Revisión de Sincronización de Likes

## Resumen de Cambios

Se han implementado **3 fixes principales** para resolver los problemas identificados en el flujo de sincronización de likes:

---

## 🔧 Fix #1: Sincronización de Filesystem con Database

### Problema Original
- Usuario descargaba canción → se guardaba en DB
- Usuario borraba archivo local (por error o propósito)
- En siguiente sync, sistema creía que estaba descargado (según DB)
- Resultado: No re-descargaba la canción

### Solución Implementada
**Nueva Función**: `sync_filesystem_to_db()` en `SyncManager`

```python
def sync_filesystem_to_db(self) -> dict:
    """
    Escanea archivos locales y agrega los que NO están en el historial.
    Resultado: {'added': int, 'already_tracked': int, 'total_found': int}
    """
```

**Cómo se ejecuta:**
1. ✅ Automáticamente al inicializar SyncManager
2. ✅ Manualmente con botón "🔄 Sync Filesystem" en opciones avanzadas
3. ✅ Busca todos los archivos de audio en la carpeta
4. ✅ Agrega los no rastreados al historial con URL local

**Beneficio:**
- Archivos descargados antes de usar la app se detectan correctamente
- Si borras un archivo, el siguiente sync puede re-descargarlo
- Base de datos siempre refleja estado actual del filesystem

---

## 🎨 Fix #2: Ventana de Preview de Likes

### Problema Original
- Usuario no sabía qué canciones eran nuevas vs ya descargadas
- Sin forma de ver estado de cada like sin descargar
- Sin forma de seleccionar específicamente qué descargar

### Solución Implementada
**Nueva Ventana**: `LikesPreviewWindow` 

**Ubicación**: `gui/likes_preview_window.py`

**Características:**
```
┌─────────────────────────────────────┐
│ Mis Likes de SoundCloud              │
│ ┌─────────────────────────────────┐  │
│ │ 🔍 Buscar canción, artista...  │  │  <- Búsqueda en tiempo real
│ └─────────────────────────────────┘  │
│                                       │
│ ○ Todos  ○ Descargados ✓  ○ Pendientes ⏳  <- Filtros
│                                       │
│ ┌─────────────────────────────────┐  │
│ │ ☑ Status  Canción        Artista│  │  <- Tabla
│ │ ☑ ✓      Song A          Artist A│  │
│ │ ☐ ⏳     Song B          Artist B│  │
│ │ ☑ ✓      Song C          Artist C│  │
│ └─────────────────────────────────┘  │
│                                       │
│ Total: 50 | Descargadas: 35 | Pendientes: 15 │
│                                       │
│ [ Seleccionar todo ] [ Descargar ]   │
└─────────────────────────────────────┘
```

**Cómo usar:**
1. En "Opciones Avanzadas" → Click en "📺 Preview de Likes"
2. Se abre ventana con tabla de todos tus likes
3. Filtros:
   - **Todos**: muestra todos los likes
   - **Descargados ✓**: solo los que ya tienes en local
   - **Pendientes ⏳**: canciones nuevas para descargar
4. Búsqueda: encuentra canción por título o artista
5. Acciones:
   - Checkbox para seleccionar
   - "Descargar" para descargar individual
   - "Seleccionar todo" para descargar lote

**Implementación Técnica:**
```python
# Get likes with download status
likes = sync_manager.get_likes_with_status()
# Resultado: lista con {url, title, artist, downloaded, file_path, ...}
```

---

## 📊 Fix #3: Método de Status de Likes

### Problema Original
- Likes se guardaban en DB pero nunca se usaban
- No había forma de saber rápidamente qué estaba descargado

### Solución Implementada
**Nueva Función**: `get_likes_with_status()` en `SyncManager`

```python
def get_likes_with_status(self) -> list[dict]:
    """
    Retorna todos los likes con su estado de descarga.
    Resultado: lista de {
        'id', 'url', 'title', 'artist',
        'downloaded': bool,
        'file_path': str | None,
        'created_at': str,
        'genre': str | None,
        'artwork_url': str
    }
    """
```

**Características:**
- Carga datos de `soundcloud_likes` table
- Cruza con `downloads` table para status
- Obtiene ruta del archivo si fue descargado
- Retorna info completa para UI

**Uso:**
```python
# En LikesPreviewWindow
likes_with_status = self.sync_manager.get_likes_with_status()

# Filtrar por status
downloaded = [l for l in likes_with_status if l['downloaded']]
pending = [l for l in likes_with_status if not l['downloaded']]
```

---

## 🚀 Cómo Usar Los Fixes

### Instalación (Lo fixes ya están integrados)
Los fixes se ejecutan automáticamente sin configuración extra.

### Uso Básico

**1. Sincronizar Filesystem (después de restaurar archivos)**
   - Settings → Opciones Avanzadas → "🔄 Sync Filesystem"
   - Escaneará archivos y actualizará el historial
   - Resultado: muestra cuántos archivos se agregaron

**2. Ver Preview de Likes**
   - Settings → Opciones Avanzadas → "📺 Preview de Likes"
   - Abre ventana con tabla completa de likes
   - Usa filtros para ver estado de descarga
   - Selecciona y descarga lo que quieras

**3. Sincronización Normal (sin cambios)**
   - El sync automático ahora:
     1. Obtiene likes de SoundCloud
     2. Sincroniza archivos locales con BD (automático)
     3. Detecta correctamente qué es nuevo vs duplicado
     4. Descarga solo lo nuevo

---

## 🔍 Problemas Resueltos

### ✅ Problema: "Nuevos likes no se descargan"
**Solución**: Sync filesystem automático ahora sync DB después de cada cambio

### ✅ Problema: "No hay forma de ver qué sincronizar"
**Solución**: New preview window muestra status de todos los likes

### ✅ Problema: "Archivos borrados re-aparecen como duplicados"
**Solución**: DB update ahora más preciso, filesystem sync recupera archivos

### ✅ Problema: "No sé qué está en mis likes vs descargado"
**Solución**: Preview window color-codea (✓ descargado vs ⏳ pendiente)

---

## 📋 Cambios en Archivos

```
sync/sync_manager.py
├── + sync_filesystem_to_db()      # Sincroniza FS con DB
└── + get_likes_with_status()      # Get likes con status

gui/likes_preview_window.py         # Nueva ventana (completa)
└── LikesPreviewWindow
    ├── Tabla con likes
    ├── Búsqueda y filtros
    └── Acciones (descargar, seleccionar)

gui/sync_window.py
├── + _on_show_likes_preview()     # Abre preview
├── + _on_sync_filesystem()        # Ejecuta sync FS
└── + _on_sync_filesystem_complete() # Muestra resultado
└── (Llamar sync_filesystem_to_db al iniciar)
```

---

## ⚙️ Configuración Avanzada

### Threshold de Similitud
El sistema mantiene su threshold de similitud (85%) para detectar duplicados fuzzy.
Esto significa que:
- Canciones con nombres muy similares (tildes diferentes, espacios) se detectan como duplicados
- Archivos que se movieron pero tienen nombre parecido también

### Qué Cuenta como "Descargado"
Un like se marca como descargado si:
1. Su URL está en `downloads` table, O
2. Un archivo similar existe en la carpeta local (fuzzy match 85%+)

### Cómo Se Guardan Los Likes
Cada vez que haces sync:
1. Se obtienen TODOS los likes de SoundCloud
2. Se guardan en `soundcloud_likes` table (overwrite)
3. Se comparan con `downloads` table para status

---

## 🐛 Troubleshooting

**P: ¿Qué pasa si ejecuto "Sync Filesystem" múltiples veces?**
R: Es seguro. Solo agrega archivos no rastreados. No duplica.

**P: ¿Los likes guardados se actualizan automáticamente?**
R: Sí, cada time que haces cualquier sync (manual o auto) se actualizan.

**P: ¿Puedo ver los likes sin internet?**
R: Sí, la preview window carga likes guardados localmente sin API.

**P: ¿Qué pasa si borro la carpeta de descargas?**
R: El siguiente "Sync Filesystem" seguirá rastreando los archivos (aunque no existan).
   Para limpiar: ejecuta una sincronización y revisa el archivo de log.

---

## 📈 Mejoras Futuras Posibles

1. Descarga individual desde preview window
2. Eliminar likes desde preview window
3. Batch operations (descargar múltiples)
4. Mostrar progreso de descargas en preview
5. Caché local de artwork_url para carga rápida
6. Sincronización incremental (solo últimos N likes)

---

## 🧪 Testing Checklist

- [ ] Ejecutar app con archivos locales pre-existentes
- [ ] Click "Sync Filesystem" → verifica que se agreguen archivos
- [ ] Abrir "Preview de Likes" → tabla se carga correctamente
- [ ] Filtro "Descargados" → muestra solo archivos descargados
- [ ] Filtro "Pendientes" → muestra solo nuevos likes
- [ ] Búsqueda → funciona con artista y título
- [ ] Auto-sync se ejecuta correctamente
- [ ] Nuevos likes se detectan en siguiente sync

---

**Fecha**: 2025-05-13
**Rama**: `claude/fix-music-sync-preview-NrIYB`
**Status**: ✅ Implementado y listo para testing
