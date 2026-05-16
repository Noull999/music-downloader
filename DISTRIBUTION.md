# Music Downloader - Guía de Distribución

## Build para Windows (.exe)

```bash
python build_windows.py
```

Genera: `dist/MusicDownloader.exe` (~150-200MB)

**Requisitos previos:**
- Python 3.9+
- pip (incluido con Python)

**Instalación de dependencias:**
```bash
pip install -r requirements.txt
pip install pyinstaller
```

---

## Build para macOS (.app)

```bash
chmod +x build_macos.sh
./build_macos.sh
```

Genera: `dist/MusicDownloader.app` (~150-200MB)

**Notas macOS:**
- Requiere ejecutarse en macOS para generar .app
- Puede necesitar notarización si se distribuye fuera de bundle

---

## Build para Linux (binary)

```bash
chmod +x build_linux.sh
./build_linux.sh
```

Genera: `dist/music-downloader` (~150-200MB binary)

**Notas Linux:**
- Sin interfaz gráfica nativa (Tkinter soportado)
- Requiere ffmpeg y yt-dlp instalados en el sistema

---

## Distribución Multi-plataforma

Para distribuir en una sola carpeta:

```bash
mkdir MusicDownloader-Release
cp dist/MusicDownloader.exe MusicDownloader-Release/  # Windows
cp -r dist/MusicDownloader.app MusicDownloader-Release/  # macOS
cp dist/music-downloader MusicDownloader-Release/  # Linux
```

---

## Tamaño de archivos esperados

- **Windows .exe**: ~150-200MB (one-file)
- **macOS .app**: ~150-200MB 
- **Linux binary**: ~150-200MB

> Los executables incluyen Python runtime + todas las dependencias

---

## Actualizaciones futuras

1. Modifica el código normalmente
2. Ejecuta el script de build correspondiente
3. Reemplaza el archivo distribuido

**Versionado:** 
- Renombra a `MusicDownloader-v1.0.exe`, `v1.1.exe`, etc.
- Permite que usuarios tengan múltiples versiones

---

## Nota: Dependencias del sistema

Los executables generados incluyen Python, pero requieren:

### Windows
- ✅ Nada adicional (todo incluido)

### macOS  
- ⚠️ Puede requerir Xcode Command Line Tools
- `xcode-select --install`

### Linux
- `ffmpeg`: `sudo apt install ffmpeg` (Debian/Ubuntu)
- `ffmpeg`: `brew install ffmpeg` (macOS via Homebrew)
