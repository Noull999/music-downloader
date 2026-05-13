"""
Presets de calidad de descarga.
Cada preset define el formato de yt-dlp y si se convierte (o no) el audio.
"""

QUALITY_PRESETS: dict[str, dict] = {
    "max_quality": {
        "label": "Maxima calidad disponible (recomendado)",
        "description": "Descarga en MP3 320kbps. Maxima calidad con compatibilidad garantizada.",
        "yt_format": "bestaudio/best",
        "sc_format": "bestaudio/best",
        "convert_to": "mp3",
        "bitrate": "320",
        "warning": None,
    },
    "mp3_320": {
        "label": "MP3 320kbps (maxima compatibilidad)",
        "description": "Convierte a MP3 320kbps. Compatible con todo reproductor.",
        "yt_format": "bestaudio/best",
        "sc_format": "bestaudio/best",
        "convert_to": "mp3",
        "bitrate": "320",
        "warning": None,
    },
    "mp3_256": {
        "label": "MP3 256kbps (balance calidad/tamano)",
        "description": "Buena calidad con archivos mas pequenos que 320kbps.",
        "yt_format": "bestaudio/best",
        "sc_format": "bestaudio/best",
        "convert_to": "mp3",
        "bitrate": "256",
        "warning": None,
    },
    "mp3_128": {
        "label": "MP3 128kbps (tamano minimo)",
        "description": "Calidad reducida. Util para podcasts o conexiones lentas.",
        "yt_format": "bestaudio/best",
        "sc_format": "bestaudio/best",
        "convert_to": "mp3",
        "bitrate": "128",
        "warning": None,
    },
    "flac": {
        "label": "FLAC sin perdida (solo si disponible)",
        "description": "Convierte a FLAC. NO mejora la calidad del audio original de YouTube/SoundCloud.",
        "yt_format": "bestaudio/best",
        "sc_format": "bestaudio/best",
        "convert_to": "flac",
        "bitrate": None,
        "warning": (
            "YouTube y SoundCloud no ofrecen audio sin perdida. "
            "El archivo FLAC tendra el mismo audio que el original "
            "pero en un contenedor mas grande. "
            "No hay mejora real de calidad."
        ),
    },
}

# Orden de presentacion en la GUI
PRESET_ORDER = ["max_quality", "mp3_320", "mp3_256", "mp3_128", "flac"]

# Preset por defecto
DEFAULT_PRESET = "mp3_320"


def get_preset(key: str) -> dict:
    """Retorna el preset por key, o el default si la key no existe."""
    return QUALITY_PRESETS.get(key, QUALITY_PRESETS[DEFAULT_PRESET])


def effective_extension(preset_key: str) -> str:
    """Retorna la extension del archivo final segun el preset."""
    preset = get_preset(preset_key)
    ext = preset.get("convert_to")
    if ext:
        return ext
    # max_quality: no conversion, el formato depende de la plataforma
    # Usamos mp3 como fallback para deteccion de duplicados
    return "mp3"
