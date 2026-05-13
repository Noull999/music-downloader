# 🎵 Music Downloader

Una aplicación de escritorio para descargar música de **SoundCloud y YouTube** con sincronización automática, detección de duplicados y conversión de formatos.

![Python](https://img.shields.io/badge/Python-3.9%2B-blue)
![License](https://img.shields.io/badge/License-MIT-green)

## ✨ Características

- **SoundCloud API Integration**
  - Descarga automática de tus likes de SoundCloud
  - Sincronización automática periódica
  - Detección inteligente de nuevas canciones

- **Sincronización Inteligente**
  - Detección fuzzy de duplicados (85% similitud)
  - Historial de descargas en SQLite
  - Evita descargas duplicadas

- **Descargas Multi-formato**
  - MP3 (128kbps, 256kbps, 320kbps)
  - FLAC (sin pérdida, si disponible)
  - Soporte para YouTube y SoundCloud

- **Post-procesamiento**
  - Incrustación de metadatos (título, artista, album)
  - Incrustación de portadas de álbum
  - Normalización de volumen
  - Detección y eliminación de silencios

- **Interfaz Gráfica**
  - GUI moderna con CustomTkinter
  - Progreso en tiempo real
  - Pausa/reanudación de descargas
  - Descarga multi-threaded (3 workers)

## 📋 Requisitos

- Python 3.9+
- FFmpeg (para post-procesamiento)
- yt-dlp
- customtkinter
- requests

## 🚀 Instalación

1. Clona el repositorio:
```bash
git clone https://github.com/Noull999/music-downloader.git
cd music-downloader
```

2. Instala las dependencias:
```bash
pip install -r requirements.txt
```

3. (Opcional) Obtén FFmpeg:
   - Windows: `choco install ffmpeg` o descarga desde https://ffmpeg.org/download.html
   - macOS: `brew install ffmpeg`
   - Linux: `sudo apt install ffmpeg`

## ⚙️ Configuración SoundCloud

Para usar la sincronización automática necesitas tu **OAuth Token** y **Client ID**:

1. Abre soundcloud.com en tu navegador
2. Abre DevTools (F12 → Network)
3. Busca cualquier request a `api-v2.soundcloud.com`
4. En el header `Authorization` copia el valor (formato: `OAuth 2-XXXXX...`)
5. En los query params busca `client_id=XXXXX` y cópialo

Ingresa estos valores en la app en la sección "Credenciales".

## 🎯 Uso

### Iniciar la aplicación:
```bash
python main.py
```

### Funciones principales:

1. **Descarga Manual**
   - Ingresa URL de SoundCloud o YouTube
   - Selecciona calidad y destino
   - Haz clic en "Descargar"

2. **Sincronización Automática**
   - Configura credenciales de SoundCloud
   - Activa auto-sync en Configuración
   - La app sincronizará tus likes periódicamente

3. **Revisar Últimas 10**
   - Verifica tus 10 likes más recientes sin descargar
   - Detecta duplicados automáticamente

4. **Sincronizar desde Índice**
   - Descarga a partir de un índice específico
   - Útil para recuperación parcial

## 📁 Estructura del Proyecto

```
music_downloader/
├── gui/                    # Interfaz gráfica
│   ├── main_window.py     # Ventana principal
│   ├── sync_window.py     # Panel de sincronización
│   ├── settings.py        # Configuración
│   └── track_list.py      # Lista de canciones
├── handlers/              # Descargadores
│   ├── base_handler.py    # Clase base
│   ├── soundcloud_handler.py
│   └── youtube_handler.py
├── sync/                  # Sincronización
│   ├── soundcloud_api.py  # Cliente API de SoundCloud
│   ├── sync_manager.py    # Orquestador de sync
│   └── duplicate_checker.py # Detección de duplicados
├── db/                    # Base de datos
│   └── history.py         # Historial de descargas
├── quality/               # Post-procesamiento
│   ├── presets.py         # Presets de calidad
│   └── post_processor.py  # FFmpeg processing
└── main.py               # Entry point
```

## 🔧 Configuración Avanzada

### Patrón de nombre de archivo:
En Configuración puedes usar:
- `{artist} - {title}` (default)
- `{title}` (solo título)
- Personalizado con {artist}, {title}, {album}

### Presets de calidad:
- **MP3 320kbps** (máxima compatibilidad)
- **MP3 256kbps** (balance calidad/tamaño)
- **MP3 128kbps** (tamaño mínimo)
- **FLAC** (sin pérdida)

### Post-procesamiento:
- Normalización de volumen
- Detección de silencios al inicio/final
- Incrustación de metadatos
- Incrustación de portadas

## 🐛 Troubleshooting

### "File not found after download"
- Verifica que FFmpeg esté instalado: `ffmpeg -version`
- Intenta con un preset diferente (ej: MP3 320kbps)

### "Invalid OAuth token"
- Regenera el token en soundcloud.com (F12 → Network)
- Asegúrate de copiar el valor completo con "OAuth 2-"

### "No new tracks found" en sync
- Los likes pueden tardar 5-10 minutos en indexarse en la API de SoundCloud
- Intenta nuevamente después de esperar

## 📊 Base de datos

El historial se guarda en:
```
~/.music_downloader/history.db
```

Contiene:
- URL de canciones descargadas
- Título, artista, album
- Ruta del archivo
- Plataforma (SoundCloud/YouTube)
- Fecha de descarga

## 📝 Logs

Los logs se guardan en:
```
music_downloader.log
```

Nivel de logging: INFO (cambiar en main.py si es necesario)

## 🤝 Contribuciones

Las contribuciones son bienvenidas. Por favor:
1. Fork el repo
2. Crea una rama para tu feature (`git checkout -b feature/AmazingFeature`)
3. Commit tus cambios (`git commit -m 'Add some AmazingFeature'`)
4. Push a la rama (`git push origin feature/AmazingFeature`)
5. Abre un Pull Request

## ⚠️ Disclaimer

Esta herramienta es solo para uso personal. Respeta los términos de servicio de SoundCloud y YouTube. El autor no es responsable de mal uso.

## 📄 License

Este proyecto está bajo la licencia MIT. Ver archivo [LICENSE](LICENSE) para más detalles.

## 👨‍💻 Autor

**José Esteban Asencio**
- GitHub: [@Noull999](https://github.com/Noull999)
- Email: joseestebanasencio@gmail.com

---

⭐ Si te fue útil, considera darle una estrella al proyecto!
