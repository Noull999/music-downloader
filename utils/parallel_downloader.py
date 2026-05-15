"""
ParallelImageDownloader: Descarga imagen en paralelo mientras se descarga audio.
Evita bloquear descarga si imagen es lenta, con timeout.
"""
import threading
import logging
from typing import Optional, Callable
import requests

logger = logging.getLogger(__name__)


class ParallelImageDownloader:
    """Descarga imagen en thread aparte sin bloquear descarga principal."""

    def __init__(self, timeout: float = 5.0, max_retries: int = 2):
        self.timeout = timeout
        self.max_retries = max_retries
        self._image_data: Optional[bytes] = None
        self._error: Optional[str] = None
        self._lock = threading.Lock()
        self._thread: Optional[threading.Thread] = None

    def download_async(self, url: str, on_complete: Optional[Callable[[bytes], None]] = None) -> None:
        """
        Inicia descarga de imagen en thread aparte.

        Args:
            url: URL de imagen
            on_complete: Callback opcional cuando se descarga (imagen_bytes)
        """
        if not url:
            logger.debug("No URL de imagen, omitiendo descarga")
            return

        self._thread = threading.Thread(
            target=self._download_worker,
            args=(url, on_complete),
            daemon=True
        )
        self._thread.start()
        logger.debug(f"📥 Descarga de imagen iniciada en paralelo: {url[:50]}...")

    def _download_worker(self, url: str, callback: Optional[Callable] = None) -> None:
        """Worker que descarga la imagen (corre en thread aparte)."""
        try:
            image_bytes = self._fetch_with_retries(url)
            if image_bytes:
                with self._lock:
                    self._image_data = image_bytes
                logger.debug(f"✓ Imagen descargada en paralelo: {len(image_bytes)//1024}KB")
                if callback:
                    callback(image_bytes)
            else:
                with self._lock:
                    self._error = "Imagen vacía"
        except Exception as e:
            logger.warning(f"⚠️  Error descargando imagen en paralelo: {e}")
            with self._lock:
                self._error = str(e)

    def _fetch_with_retries(self, url: str) -> Optional[bytes]:
        """Descarga con reintentos y timeout."""
        for attempt in range(self.max_retries):
            try:
                response = requests.get(
                    url,
                    timeout=self.timeout,
                    headers={
                        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
                    }
                )
                response.raise_for_status()
                return response.content
            except requests.Timeout:
                logger.debug(f"Timeout descargando imagen (intento {attempt+1}/{self.max_retries})")
            except requests.RequestException as e:
                logger.debug(f"Error request imagen (intento {attempt+1}/{self.max_retries}): {e}")

        return None

    def get_image(self, wait_ms: int = 5000) -> Optional[bytes]:
        """
        Obtiene imagen si está disponible.

        Args:
            wait_ms: Milisegundos máximo a esperar (default 5s)

        Returns:
            Bytes de imagen o None si no disponible/timeout
        """
        if self._thread:
            self._thread.join(timeout=wait_ms / 1000.0)

        with self._lock:
            return self._image_data

    def get_error(self) -> Optional[str]:
        """Obtiene mensaje de error si falló descarga."""
        with self._lock:
            return self._error

    def is_done(self) -> bool:
        """Verifica si descarga está completa."""
        if self._thread:
            return not self._thread.is_alive()
        return True


class OptimizedDownloadOptions:
    """Factory para opciones optimizadas de yt-dlp por plataforma."""

    @staticmethod
    def get_youtube_opts(output_path: str, quality_preset: dict) -> dict:
        """Opciones optimizadas para YouTube."""
        return {
            # Formato: mejor audio disponible
            "format": "bestaudio/best",
            # Output
            "outtmpl": output_path + ".%(ext)s",
            # Velocidad
            "socket_timeout": 30,
            "retries": 3,
            "fragment_retries": 3,
            "skip_unavailable_fragments": True,
            # Performance
            "quiet": False,
            "no_warnings": True,
            "prefer_ffmpeg": True,
            # Anti-bloqueo
            "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        }

    @staticmethod
    def get_soundcloud_opts(output_path: str, quality_preset: dict, oauth_token: str = "") -> dict:
        """Opciones optimizadas para SoundCloud."""
        opts = {
            # Formato
            "format": quality_preset.get("sc_format", "bestaudio/best"),
            "outtmpl": output_path + ".%(ext)s",
            # Velocidad
            "socket_timeout": 30,
            "retries": 3,
            "fragment_retries": 3,
            "skip_unavailable_fragments": True,
            # Performance
            "quiet": False,
            "no_warnings": True,
            "prefer_ffmpeg": True,
            # NO descargar thumbnail aquí (lo hacemos en paralelo)
            "writethumbnail": False,
            "writesubtitles": False,
            # SoundCloud específico
            "geo_bypass": True,
        }

        # Agregar token si disponible
        if oauth_token:
            opts["extractor_args"] = {
                "soundcloud": {"oauth_token": [oauth_token]}
            }

        return opts

    @staticmethod
    def get_postprocessors(quality_preset: dict) -> list[dict]:
        """Postprocessadores optimizados."""
        postprocessors = []
        convert_to = quality_preset.get("convert_to")

        if convert_to:
            # Conversión de audio
            postprocessors.append({
                "key": "FFmpegExtractAudio",
                "preferredcodec": convert_to,
                "preferredquality": quality_preset.get("bitrate", "0"),
            })

            # Metadata básica vía ffmpeg (rápido)
            # Nota: No usamos EmbedThumbnail aquí porque:
            # 1. Ya descargamos imagen en paralelo
            # 2. yt-dlp EmbedThumbnail deja archivos .jpg sueltos si falla
            # 3. Mutagen (en PostProcessor) es más confiable
            postprocessors.append({
                "key": "FFmpegMetadata",
                "add_metadata": True
            })

        return postprocessors
