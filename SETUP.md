# Setup - Music Downloader

Guía de instalación para Music Downloader en diferentes sistemas operativos.

## 🚀 Instalación Rápida (Recomendado)

### Windows
```bash
install.bat
python main.py
```

### macOS / Linux
```bash
chmod +x install.sh
./install.sh
python3 main.py
```

---

## 📋 Requisitos Previos

### Todos los Sistemas
- **Python 3.9+** ([descargar](https://www.python.org/downloads/))
- **ffmpeg** (ver instrucciones por SO)
- **git** (para clonar el repo)

### Windows
1. Python 3.9+ (con "Add Python to PATH" activado)
2. ffmpeg (vía Chocolatey o manual)
3. Opcional: Git Bash o PowerShell 7+

### macOS
1. Python 3.9+ (via Homebrew o python.org)
2. Homebrew (`/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"`)
3. ffmpeg (`brew install ffmpeg`)

### Linux (Ubuntu/Debian)
1. Python 3.9+ (`sudo apt-get install python3`)
2. ffmpeg (`sudo apt-get install ffmpeg`)
3. pip (`sudo apt-get install python3-pip`)

---

## 📥 Instalación Paso a Paso

### 1. Clonar el Repositorio
```bash
git clone https://github.com/YourUsername/music-downloader.git
cd music-downloader
```

### 2. Verificar Python
```bash
# Windows
python --version

# macOS / Linux
python3 --version
```

Debe mostrar Python 3.9 o superior.

### 3. Instalar ffmpeg

#### Windows
**Opción A: Chocolatey (Recomendado)**
```bash
choco install ffmpeg
```

**Opción B: Manual**
1. Descarga desde https://ffmpeg.org/download.html
2. Extrae en `C:\ffmpeg`
3. Agrega `C:\ffmpeg\bin` al PATH:
   - Win+R → `sysdm.cpl`
   - Variables de entorno → PATH → Nuevo → `C:\ffmpeg\bin`

#### macOS
```bash
brew install ffmpeg
```

#### Linux (Ubuntu/Debian)
```bash
sudo apt-get update
sudo apt-get install ffmpeg
```

#### Verificar Instalación
```bash
ffmpeg -version
```

Debe mostrar la versión de ffmpeg.

### 4. Instalar Dependencias Python
```bash
# Windows
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt

# macOS / Linux
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 5. Ejecutar la Aplicación
```bash
# Windows (con venv activado)
python main.py

# macOS / Linux (con venv activado)
python3 main.py
```

---

## 🔧 Troubleshooting

### "ffmpeg not found"
**Problema:** La app no encuentra ffmpeg en PATH.

**Solución:**
1. Verifica que ffmpeg está instalado: `ffmpeg -version`
2. Si no funciona, instalalo de nuevo:
   - Windows: `choco install ffmpeg`
   - macOS: `brew install ffmpeg`
   - Linux: `sudo apt-get install ffmpeg`

### "Python not found" / "Command not recognized"
**Problema:** Python no está en PATH.

**Solución:**
1. Windows: Desinstala Python y reinstala con "Add Python to PATH"
2. macOS/Linux: Usa `python3` en lugar de `python`

### "ModuleNotFoundError"
**Problema:** Falta una dependencia Python.

**Solución:**
```bash
pip install -r requirements.txt
```

### ffmpeg detectado pero conversion no funciona
**Problema:** ffmpeg está instalado pero la app no lo encuentra.

**Solución:**
1. Verifica ubicación de ffmpeg:
   - Windows: Busca en `C:\ffmpeg\bin` o donde lo instalaste
   - macOS: `which ffmpeg`
   - Linux: `which ffmpeg`

2. Si está en ruta no estándar, agrega a PATH manualmente

### Puerto en uso (GUI no inicia)
**Problema:** "Address already in use"

**Solución:**
1. Cierra todas las instancias de la app
2. En Windows, mata el proceso:
   ```bash
   taskkill /IM python.exe /F
   ```

### Database locked
**Problema:** "database is locked"

**Solución:**
1. Cierra todas las instancias de la app
2. Elimina `~/.music_downloader/history.db`
3. Reinicia

---

## 📁 Estructura de Datos

```
~/.music_downloader/
├── history.db          # Base de datos de descargas
└── config.json*        # Configuración (si aplica)

~/Music/               # Ubicación predeterminada de descargas
└── [canciones descargadas]
```

*: La ubicación de config.json puede variar

---

## 🧪 Ejecutar Tests

```bash
# Instalar pytest (si no está)
pip install pytest

# Ejecutar todos los tests
pytest tests/ -v

# Ejecutar un test específico
pytest tests/test_ffmpeg_detection.py::TestFFmpegLocation -v
```

---

## 🌍 Desarrollo Multiplataforma

### Contribuir

**Antes de hacer un PR:**
1. Crea una rama: `git checkout -b feature/mi-feature`
2. Ejecuta tests: `pytest tests/`
3. Asegúrate que funciona en tu SO
4. Los CI/CD tests validarán en Windows, macOS y Linux

**Notas de Desarrollo:**
- Usa rutas relativas con `os.path.join()` o `pathlib.Path`
- Evita rutas hardcodeadas a `/Users/` o `C:\Users\`
- Prueba en múltiples SO si es posible

### Probando en Diferentes SO (Localmente)

**Si tienes acceso a múltiples máquinas:**
1. Clona el repo
2. Sigue SETUP.md para tu SO
3. Ejecuta `pytest tests/`
4. Reporta problemas en Issues

---

## 🚀 Próximos Pasos

1. **Primera Ejecución:**
   ```bash
   python main.py  # o python3 main.py
   ```

2. **Configurar Credenciales:**
   - Abre la app
   - Ve a Configuración
   - Agrega SoundCloud OAuth token y Client ID

3. **Primeros Descargas:**
   - Prueba con una canción individual
   - Verifica que se descargó correctamente
   - Prueba con una playlist

4. **Sincronización (Opcional):**
   - Configura sincronización de likes de SoundCloud
   - La app descargará automáticamente nuevos likes

---

## 📞 Soporte

Si encuentras problemas:

1. **Consulta Troubleshooting** arriba
2. **Verifica los tests:** `pytest tests/ -v`
3. **Lee los logs:** La app muestra detalles en consola
4. **Abre un Issue** en GitHub con:
   - Tu SO y versión
   - Versión de Python
   - Qué intentaste hacer
   - Mensaje de error completo

---

## 📝 Notas Importantes

- **Almacenamiento:** Los datos se guardan en `~/.music_downloader/` (independiente de SO)
- **Configuración:** Accesible desde la GUI
- **Bases de Datos:** SQLite3 (no requiere servidor externo)
- **Actualizaciones:** Ejecuta `git pull` para obtener cambios

---

**¡Disfruta descargando música! 🎵**
