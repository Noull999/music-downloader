"""
Post-procesado de audio con ffmpeg y mutagen.
Se aplica DESPUES de que el handler descargo y convirtio el archivo.
Operaciones: normalizacion de volumen, eliminacion de silencios, re-embebido de tags.
"""
import io
import logging
import os
import subprocess
import shutil
import sys
from typing import Optional

from utils.exceptions import DependencyNotFoundError, DownloadError
from utils.dependencies import FFmpegValidator

logger = logging.getLogger(__name__)

# Cache de ruta a ffmpeg validada
_FFMPEG_CACHE: Optional[str] = None


def get_ffmpeg_exe() -> str:
    """Obtiene ruta validada de ffmpeg. Lanza si no existe."""
    global _FFMPEG_CACHE
    if _FFMPEG_CACHE is None:
        _FFMPEG_CACHE = FFmpegValidator.find_ffmpeg_executable()
    return _FFMPEG_CACHE


class PostProcessor:
    """
    Aplica operaciones de post-procesado a un archivo de audio ya descargado.
    Todas las operaciones son opcionales y se configuran via `options`.
    """

    def __init__(self, options: dict):
        self.normalize_volume: bool = options.get("normalize_volume", False)
        self.remove_silence: bool = options.get("remove_silence", False)
        self.embed_artwork: bool = options.get("embed_artwork", True)
        self.embed_metadata: bool = options.get("embed_metadata", True)
        self.embed_genre: bool = options.get("embed_genre", False)
        self.analyze_audio: bool = options.get("analyze_audio", False)
        self.key_format: str = options.get("key_format", "camelot")

    def process(
        self,
        input_file: str,
        metadata: dict,
        thumbnail_url: str = "",
    ) -> str:
        """
        Aplica todos los post-procesos configurados al archivo.
        Retorna la ruta del archivo procesado (puede ser el mismo).
        """
        if not os.path.exists(input_file):
            logger.warning("Post-process: archivo no encontrado %s", input_file)
            return input_file

        ext = os.path.splitext(input_file)[1].lower()

        # Normalizacion y/o eliminacion de silencios via ffmpeg
        if (self.normalize_volume or self.remove_silence) and ext == ".mp3":
            input_file = self._apply_ffmpeg_filters(input_file)

        # Re-embebido de metadatos y carátula (solo MP3 con mutagen)
        if (self.embed_metadata or self.embed_artwork or self.embed_genre) and ext == ".mp3":
            self._embed_tags(input_file, metadata, thumbnail_url if self.embed_artwork else "")

        # BPM + tonalidad (Camelot). Es la operación más lenta (~2s/track,
        # más ~60-80s de compilación de numba la primera vez en el proceso),
        # así que va al final y nunca interrumpe la descarga si falla:
        # librosa es una dependencia opcional (ver analysis/audio_analysis.py).
        if self.analyze_audio:
            self._analyze_audio(input_file)

        return input_file

    def _analyze_audio(self, input_file: str) -> None:
        try:
            from analysis import audio_analysis
            audio_analysis.analyze_and_tag(input_file, key_format=self.key_format)
        except Exception:
            logger.exception("Error analizando BPM/tonalidad de %s (no crítico)", input_file)

    # ------------------------------------------------------------------ #
    # Filtros ffmpeg                                                       #
    # ------------------------------------------------------------------ #

    def _apply_ffmpeg_filters(self, input_file: str) -> str:
        """Aplica filtros ffmpeg (normalización, eliminación de silencios)."""
        try:
            ffmpeg = get_ffmpeg_exe()
        except DependencyNotFoundError as e:
            logger.warning(f"FFmpeg no disponible, omitiendo post-procesado: {e}")
            return input_file

        filters: list[str] = []

        if self.normalize_volume:
            # EBU R128 — estándar profesional de normalización de loudness
            filters.append("loudnorm=I=-14:LRA=11:TP=-1")

        if self.remove_silence:
            filters.append("silenceremove=start_periods=1:start_silence=0.5:start_threshold=-50dB")
            filters.append("silenceremove=stop_periods=1:stop_silence=0.5:stop_threshold=-50dB")

        if not filters:
            return input_file

        filter_chain = ",".join(filters)
        temp_file = input_file + ".pp_temp.mp3"

        cmd = [
            ffmpeg, "-i", input_file,
            "-af", filter_chain,
            "-c:a", "libmp3lame", "-b:a", "320k",
            "-y", temp_file,
        ]

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                timeout=120,
                text=False,
            )

            if result.returncode == 0 and os.path.exists(temp_file):
                os.replace(temp_file, input_file)
                logger.info(f"✓ Filtros ffmpeg aplicados: {filter_chain}")
                return input_file

            # FFmpeg falló — log claro
            stderr_msg = result.stderr.decode(errors="replace")[:300]
            raise DownloadError(
                f"FFmpeg falló (código {result.returncode}): {stderr_msg}"
            )

        except subprocess.TimeoutExpired:
            logger.error(f"FFmpeg timeout (>120s) en: {input_file}")
            if os.path.exists(temp_file):
                os.remove(temp_file)
            raise DownloadError("Post-procesado timeout")

        except FileNotFoundError:
            logger.error("FFmpeg ejecutable no encontrado")
            if os.path.exists(temp_file):
                os.remove(temp_file)
            raise DependencyNotFoundError("FFmpeg no está accesible")

        except DownloadError:
            if os.path.exists(temp_file):
                os.remove(temp_file)
            raise

        except Exception as e:
            logger.error(f"Error inesperado en post-procesado: {e}")
            if os.path.exists(temp_file):
                os.remove(temp_file)
            raise DownloadError(f"Post-procesado falló: {e}")

    # ------------------------------------------------------------------ #
    # Embebido de tags con mutagen                                         #
    # ------------------------------------------------------------------ #

    def _embed_tags(self, file_path: str, metadata: dict, thumbnail_url: str) -> None:
        try:
            from mutagen.id3 import ID3, APIC, TIT2, TPE1, TALB, TCON, TDRC, error as ID3Error
            from mutagen.mp3 import MP3
        except ImportError:
            logger.warning("mutagen no disponible; no se puede embeber tags manualmente.")
            return

        try:
            audio = MP3(file_path, ID3=ID3)
            try:
                audio.add_tags()
            except ID3Error:
                pass  # ya tiene tags

            if self.embed_metadata:
                try:
                    if metadata.get("title"):
                        audio.tags.add(TIT2(encoding=3, text=metadata["title"]))
                    if metadata.get("artist"):
                        audio.tags.add(TPE1(encoding=3, text=metadata["artist"]))
                    if metadata.get("album"):
                        audio.tags.add(TALB(encoding=3, text=metadata["album"]))
                    if metadata.get("year"):
                        audio.tags.add(TDRC(encoding=3, text=metadata["year"]))
                except Exception as meta_exc:
                    logger.warning("Error embebiendo metadatos: %s", meta_exc)

            if self.embed_genre:
                try:
                    genero = metadata.get("genre")
                    if genero:
                        audio.tags.add(TCON(encoding=3, text=genero))
                    else:
                        # No hay género válido. yt-dlp ya escribió el suyo
                        # durante la descarga y para YouTube eso es la
                        # CATEGORÍA del video ("Music", "Entertainment"),
                        # que no dice nada del estilo: si es de esas, se
                        # borra en vez de dejarla.
                        from sync import genre_utils
                        actual = audio.tags.get("TCON")
                        if actual and not genre_utils.resolve_genre(str(actual)):
                            audio.tags.delall("TCON")
                except Exception as meta_exc:
                    logger.warning("Error embebiendo metadatos: %s", meta_exc)

            if self.embed_artwork and thumbnail_url:
                try:
                    grande = self.upgrade_artwork_url(thumbnail_url)
                    img_data = self._fetch_image_cached(grande)
                    if not img_data and grande != thumbnail_url:
                        # El tamaño grande no siempre existe; mejor la
                        # miniatura que quedarse sin carátula.
                        img_data = self._fetch_image_cached(thumbnail_url)
                    if img_data and len(img_data) > 0:
                        img_data, mime = self.normalizar_imagen(img_data)
                        audio.tags.add(
                            APIC(
                                encoding=3,
                                mime=mime,
                                type=3,   # Cover (front)
                                desc="Cover",
                                data=img_data,
                            )
                        )
                except Exception as art_exc:
                    logger.warning("Error embebiendo carátula: %s", art_exc)

            audio.save()
        except Exception as exc:
            logger.warning("Error guardando tags en %s: %s", file_path, exc)

    @staticmethod
    def upgrade_artwork_url(url: str) -> str:
        """
        SoundCloud llama "large" a una miniatura de 100x100, que incrustada
        se ve borrosa en Serato y en cualquier reproductor. La variante
        t500x500 (500x500, ~57 KB) es el punto justo: nítida sin inflar
        cada mp3 como haría "original" (3999x3999, ~1.9 MB).
        """
        if not url:
            return url
        for otro in ("-large.", "-t300x300.", "-small.", "-badge.", "-tiny.",
                     "-original."):
            if otro in url:
                # "original" también se cambia, pero por lo contrario: son
                # 3000x3000 y ~900 KB metidos en cada mp3.
                return url.replace(otro, "-t500x500.")
        return url

    @staticmethod
    def normalizar_imagen(data: bytes, lado_max: int = 600) -> tuple[bytes, str]:
        """
        Deja la imagen lista para incrustar: JPEG y de tamaño razonable.

        YouTube devuelve las miniaturas en WebP, que Serato y varios
        reproductores no muestran como carátula; y algunas fuentes dan
        imágenes de 3000x3000 que inflan cada archivo casi 1 MB. Si algo
        falla se devuelve el original tal cual: mejor una carátula
        imperfecta que ninguna.
        """
        try:
            from PIL import Image
        except ImportError:
            return data, PostProcessor._mime_de(data)
        try:
            im = Image.open(io.BytesIO(data))
            formato = (im.format or "").upper()
            grande = max(im.size) > lado_max
            if formato in ("JPEG", "PNG") and not grande:
                return data, PostProcessor._mime_de(data)
            if grande:
                im.thumbnail((lado_max, lado_max), Image.LANCZOS)
            buf = io.BytesIO()
            im.convert("RGB").save(buf, "JPEG", quality=88, optimize=True)
            return buf.getvalue(), "image/jpeg"
        except Exception as exc:
            logger.debug("No se pudo normalizar la carátula (%s); se usa tal cual", exc)
            return data, PostProcessor._mime_de(data)

    @staticmethod
    def _mime_de(data: bytes) -> str:
        """
        Tipo real según los primeros bytes. Antes se declaraba siempre
        image/jpeg, incluso para URLs .png: un reproductor estricto no
        muestra una carátula cuyo mime no coincide con el contenido.
        """
        if data[:8] == b"\x89PNG\r\n\x1a\n":
            return "image/png"
        return "image/jpeg"

    def _fetch_image_cached(self, url: str, timeout: float = 5.0) -> Optional[bytes]:
        """Obtiene imagen con caché automático (evita re-descargar)."""
        try:
            from utils.image_cache import ImageCacheManager

            # Intentar obtener del caché
            cache = ImageCacheManager()
            img_data = cache.get(url)
            if img_data:
                logger.debug(f"✓ Imagen obtenida del caché: {len(img_data)//1024}KB")
                return img_data

            # No está en caché, descargar
            logger.debug(f"📥 Descargando imagen (no en caché)...")
            img_data = self._fetch_image(url, timeout)
            if img_data:
                cache.set(url, img_data, mime_type="image/jpeg", ttl_days=30)
            return img_data

        except ImportError:
            logger.debug("ImageCacheManager no disponible, descargando sin caché")
            return self._fetch_image(url, timeout)
        except Exception as exc:
            logger.warning(f"Error en caché de imágenes: {exc}")
            return self._fetch_image(url, timeout)

    def _fetch_image(self, url: str, timeout: float = 5.0) -> Optional[bytes]:
        """Descarga imagen usando sesión global con pooling."""
        try:
            from utils.http_session import get_session
            session = get_session()
            resp = session.get(url, timeout=timeout)
            resp.raise_for_status()
            return resp.content
        except Exception as exc:
            logger.warning(f"No se pudo descargar thumbnail para tags: {exc}")
            return None
