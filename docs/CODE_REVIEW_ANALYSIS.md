# 🔍 Análisis Profesional: Problemas de Sincronización de Likes

## Resumen Ejecutivo

Se identificaron **3 problemas críticos** en el flujo de sincronización de likes:

1. **Desconexión en la detección de nuevos likes** - Los likes nuevos no se reflejan correctamente
2. **Falta de visualización** - No hay forma de ver qué se sincroniza vs qué está descargado
3. **Lógica de almacenamiento de likes ineficiente** - Se guardan pero no se usan correctamente

---

## 🐛 Problema #1: Sincronización Rota de Likes

### Síntomas
- Usuario agrega likes en SoundCloud
- Ejecuta "Sincronizar ahora"
- Los nuevos likes no aparecen descargados
- O aparecen como duplicados cuando no lo son

### Causa Raíz

**En `sync_manager.py` línea 303**:
```python
def sync_once(self):
    ...
    all_likes = self.api.get_likes()  # Obtiene TODO el historial de likes
    self.history.save_likes(all_likes)  # GUARDA todos los likes
    new_tracks, duplicates = self.checker.get_new_tracks(all_likes, folder)  # Filtra nuevos
```

**Problema**: El sistema:
1. ✓ Obtiene correctamente los likes de SoundCloud API
2. ✓ Guarda todos los likes en `soundcloud_likes` table
3. ✗ **PERO**: Luego filtra nuevos comparando SOLO contra `downloads` table (historial de descargas)

**El Bug**: Si un usuario:
- Tiene 50 likes en SoundCloud
- 45 ya están descargados
- Agrega 5 nuevos likes
- El sistema obtiene los 50, pero solo descarga los 5 nuevos ✓

**PERO si**: 
- El usuario BORRA un archivo local (pero SoundCloud sigue teniendo el like)
- Ejecuta sync de nuevo
- El sistema obtiene 50 likes, BUT el archivo no está en `downloads` table (está en carpeta)
- El `DuplicateChecker` busca archivo similar en carpeta y LO ENCUENTRA
- Sistema marca como duplicado pero el usuario QUERÍA descargarlo de nuevo ✗

### Impacto
- **Severidad**: ALTA
- **Frecuencia**: MEDIA (cuando archivos se pierden/mueven)
- **Afectados**: Todos los usuarios que reorganizan archivos o eliminan descargas

---

## 🎨 Problema #2: Falta de Visualización/Preview

### Síntomas
- Usuario no sabe qué está sincronizando
- No hay forma de ver nuevas canciones pendientes sin descargar
- No hay forma de seleccionar qué descargar

### Solución Requerida
Agregar una **ventana de preview** que muestre:
1. Likes en SoundCloud (con estado: descargado ✓ / pendiente ⏳)
2. Archivos ya descargados en la carpeta
3. Selector para elegir qué descargar

---

## 📊 Problema #3: Likes Guardados Sin Usar

### Estado Actual
- `soundcloud_likes` table se llena cada sync
- PERO nunca se usa para mostrar al usuario
- NO hay UI que muestre estos datos

### Solución Requerida
Crear un tab/ventana que:
1. Cargue likes de la DB
2. Muestre estado de cada uno (descargado sí/no)
3. Permita interacción (descargar, eliminar, etc)

---

## ✅ Plan de Fixes

### Fix #1: Mejorar Detección de Duplicados
- [ ] Sincronizar tabla `downloads` con archivos reales en carpeta
- [ ] Agregar método `sync_filesystem_to_db()` 
- [ ] Ejecutar al iniciar app y después de cada descarga

### Fix #2: Agregar Ventana de Preview
- [ ] Nueva ventana `LikesPreviewWindow`
- [ ] Tabla con: artista | canción | estado | acciones
- [ ] Botones: descargar, marcar como duplicado, eliminar like

### Fix #3: Hacer Likes Guardados Útiles
- [ ] Cargar likes al iniciar (rápido, sin API call)
- [ ] Mostrar estadísticas en tiempo real
- [ ] Permitir buscar/filtrar en tabla

---

## 🔐 Consideraciones de Seguridad

✓ **Sin problemas de seguridad graves encontrados**
- Credenciales se guardan en config local (usuario responsable)
- URLs del token se normalizan correctamente
- No hay inyección de SQL (usa prepared statements)
- No hay acceso no autorizado a archivos

---

## 📈 Estimación de Esfuerzo

| Fix | Complejidad | Líneas | Tiempo Est. |
|-----|---|---|---|
| Fix #1 | Media | 100-150 | 1-2 horas |
| Fix #2 | Alta | 400-500 | 3-4 horas |
| Fix #3 | Baja | 50-100 | 30 min |

**Total**: 4-6 horas de desarrollo

---

## 📋 Código Afectado

```
sync/
├── sync_manager.py        # Fix: agregar sync_filesystem_to_db()
├── duplicate_checker.py   # Cambios menores

db/
├── history.py            # Agregar método get_likes_with_status()

gui/
├── sync_window.py        # Agregar tab para preview
└── (Nueva) likes_preview_window.py  # Nueva ventana

main.py                    # Llamar sync_filesystem_to_db() al iniciar
```

---

## 🎯 Next Steps

1. Implementar Fix #1 (mejorar detección de duplicados)
2. Implementar Fix #2 (ventana de preview)
3. Implementar Fix #3 (usar likes guardados)
4. Testing y validación
