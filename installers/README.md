# 🎵 Music Downloader - Instaladores

Scripts de instalación automática para cada sistema operativo.

## Windows

### Opción 1: Instalador automático (Recomendado)
```bash
install-windows.bat
```

Simplemente **haz doble click** en el archivo `install-windows.bat` y todo se instalará automáticamente.

### Opción 2: Manual
```bash
python -m pip install --upgrade pip
pip install -r ../requirements.txt
python ../main.py
```

**Requisitos previos:**
- Python 3.8+ (descarga desde https://www.python.org)
- FFmpeg (https://ffmpeg.org/download.html)

---

## macOS

### Opción 1: Instalador automático (Recomendado)
```bash
chmod +x install-macos.sh
./install-macos.sh
```

### Opción 2: Manual
```bash
brew install ffmpeg python3
pip3 install -r ../requirements.txt
python3 ../main.py
```

**Requisitos:**
- Homebrew (descarga desde https://brew.sh)

---

## Linux

### Opción 1: Instalador automático (Recomendado)
```bash
chmod +x install-linux.sh
./install-linux.sh
```

Soporta automáticamente:
- Ubuntu / Debian (apt)
- Fedora / CentOS / RHEL (dnf)
- Arch / Manjaro (pacman)
- openSUSE (zypper)

### Opción 2: Manual
```bash
# Ubuntu/Debian
sudo apt install python3 python3-pip ffmpeg

# Fedora/RHEL
sudo dnf install python3 python3-pip ffmpeg

# Arch
sudo pacman -S python python-pip ffmpeg

pip3 install -r ../requirements.txt
python3 ../main.py
```

---

## Después de Instalar

Para iniciar la aplicación:

```bash
python main.py      # Windows
python3 main.py     # macOS / Linux
```

---

## Solución de Problemas

### "Python not found"
- **Windows:** Asegúrate de marcar "Add Python to PATH" en el instalador
- **macOS/Linux:** Instala Python con: `brew install python3` o `apt install python3`

### "FFmpeg not found"
- Los scripts lo instalan automáticamente
- Si aún falla, instálalo manualmente desde https://ffmpeg.org

### "Permission denied" (macOS/Linux)
```bash
chmod +x install-macos.sh
chmod +x install-linux.sh
```

---

**¡Listo! Disfruta descargando tu música! 🎶**
