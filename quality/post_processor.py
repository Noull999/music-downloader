"""
Post-procesado de audio con ffmpeg y mutagen.
Se aplica DESPUES de que el handler descargo y convirtio el archivo.
Operaciones: normalizacion de volumen, eliminacion de silencios, re-embebido de tags,
letras sincronizadas y organizacion opcional con beets.
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

# Codec de salida por extension. Antes se forzaba libmp3lame+320k para TODO,
# lo que rompía silenciosamente el preset FLAC (reencodeaba a mp3 con
# extensión .flac -> archivo corrupto/ilegible como FLAC real).
_FFMPEG_CODEC_ARGS: dict[str, list[str]] = {
    ".mp3": ["-c:a", "libmp3lame", "-b:a", "320k"],
    ".flac": ["-c:a", "flac"],
}

# Extensiones para las que sabemos embeber tags (mutagen)
_TAGGABLE_EXTENSIONS = {".mp3", ".flac"}


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
        self.embed_lyrics: bool = options.get("embed_lyrics", False)
        self.embed_genre: bool = options.get("embed_genre", True)
        self.organize_with_beets: bool = options.get("organize_with_beets", False)

    def process(
        self,
        input_file: str,
        metadata: dict,
        thumbnail_url: str = "",
    ) -> str:
        """
        Aplica todos los post-procesos configurados al archivo.
        Retorna la ruta del archivo procesado (puede ser el mismo, o la nueva
        ruta si beets lo reorganizo).
        """
        if not os.path.exists(input_file):
            logger.warning("Post-process: archivo no encontrado %s", input_file)
            return input_file

        ext = os.path.splitext(input_file)[1].lower()

        # Normalizacion y/o eliminacion de silencios via ffmpeg
        if (self.normalize_volume or self.remove_silence) and ext in _FFMPEG_CODEC_ARGS:
            input_file = self._apply_ffmpeg_filters(input_file, ext)

        # Re-embebido de metadatos, carátula y letras (mp3 y flac con mutagen)
        if (self.embed_metadata or self.embed_artwork or self.embed_lyrics or self.embed_genre) and ext in _TAGGABLE_EXTENSIONS:
            self._embed_tags(
                input_file, metadata,
                thumbnail_url if self.embed_artwork else "",
                ext,
            )

        # Organizacion de biblioteca con beets (opcional, requiere `beet` en PATH)
        if self.organize_with_beets:
            input_file = self._organize_with_beets(input_file)

        return input_file

    # ------------------------------------------------------------------ #
    # Filtros ffmpeg                                                       #
    # ------------------------------------------------------------------ #

    def _apply_ffmpeg_filters(self, input_file: str, ext: str) -> str:
        """Aplica filtros ffmpeg (normalización, eliminación de silencios).

        `ext` determina el codec de re-encode: antes esto se forzaba siempre
        a libmp3lame+320k, lo que corrompía archivos FLAC (quedaban como
        mp3 renombrado a .flac). Ahora se preserva el codec del preset.
        """
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

        codec_args = _FFMPEG_CODEC_ARGS.get(ext, _FFMPEG_CODEC_ARGS[".mp3"])
        filter_chain = ",".join(filters)
        temp_file = input_file + f".pp_temp{ext}"

        cmd = [
            ffmpeg, "-i", input_file,
            "-af", filter_chain,
            *codec_args,
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

    def _embed_tags(self, file_path: str, metadata: dict, thumbnail_url: str, ext: str) -> None:
        """Despacha el embebido de tags segun el formato del archivo."""
        lyrics = self._fetch_lyrics(metadata) if self.embed_lyrics else None

        if ext == ".mp3":
            self._embed_tags_mp3(file_path, metadata, thumbnail_url, lyrics)
        elif ext == ".flac":
            self._embed_tags_flac(file_path, metadata, thumbnail_url, lyrics)
        else:
            logger.debug("Formato %s sin soporte de tags, se omite.", ext)

    def _embed_tags_mp3(self, file_path: str, metadata: dict, thumbnail_url: str, lyrics: Optional[str]) -> None:
        try:
            from mutagen.id3 import ID3, APIC, TIT2, TPE1, TALB, TDRC, TCON, USLT, error as ID3Error
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

            if self.embed_genre and metadata.get("genre"):
                try:
                    audio.tags.add(TCON(encoding=3, text=metadata["genre"]))
                except Exception as genre_exc:
                    logger.warning("Error embebiendo género: %s", genre_exc)

            if self.embed_artwork and thumbnail_url:
                try:
                    img_data = self._fetch_image_cached(thumbnail_url)
                    if img_data and len(img_data) > 0:
                        audio.tags.add(
                            APIC(
                                encoding=3,
                                mime="image/jpeg",
                                type=3,   # Cover (front)
                                desc="Cover",
                                data=img_data,
                            )
                        )
                except Exception as art_exc:
                    logger.warning("Error embebiendo carátula: %s", art_exc)

            if lyrics:
                try:
                    audio.tags.add(USLT(encoding=3, lang="eng", desc="", text=lyrics))
                except Exception as lyr_exc:
                    logger.warning("Error embebiendo letras: %s", lyr_exc)

            audio.save()
        except Exception as exc:
            logger.warning("Error guardando tags en %s: %s", file_path, exc)

    def _embed_tags_flac(self, file_path: str, metadata: dict, thumbnail_url: str, lyrics: Optional[str]) -> None:
        """Embebe tags en FLAC via Vorbis comments + Picture block.

        Antes el preset FLAC no recibía NINGUN tag/caratula: el bloque de
        embebido superior estaba condicionado a `ext == ".mp3"`, así que
        cualquier descarga en FLAC quedaba silenciosamente sin metadatos.
        """
        try:
            from mutagen.flac import FLAC, Picture
        except ImportError:
            logger.warning("mutagen no disponible; no se puede embeber tags en FLAC.")
            return

        try:
            audio = FLAC(file_path)

            if self.embed_metadata:
                try:
                    if metadata.get("title"):
                        audio["title"] = metadata["title"]
                    if metadata.get("artist"):
                        audio["artist"] = metadata["artist"]
                    if metadata.get("album"):
                        audio["album"] = metadata["album"]
                    if metadata.get("year"):
                        audio["date"] = str(metadata["year"])
                except Exception as meta_exc:
                    logger.warning("Error embebiendo metadatos FLAC: %s", meta_exc)

            if self.embed_genre and metadata.get("genre"):
                try:
                    audio["genre"] = metadata["genre"]
                except Exception as genre_exc:
                    logger.warning("Error embebiendo género FLAC: %s", genre_exc)

            if self.embed_artwork and thumbnail_url:
                try:
                    img_data = self._fetch_image_cached(thumbnail_url)
                    if img_data and len(img_data) > 0:
                        pic = Picture()
                        pic.data = img_data
                        pic.type = 3  # Cover (front)
                        pic.mime = "image/jpeg"
                        audio.clear_pictures()
                        audio.add_picture(pic)
                except Exception as art_exc:
                    logger.warning("Error embebiendo carátula FLAC: %s", art_exc)

            if lyrics:
                try:
                    audio["lyrics"] = lyrics
                except Exception as lyr_exc:
                    logger.warning("Error embebiendo letras FLAC: %s", lyr_exc)

            audio.save()
        except Exception as exc:
            logger.warning("Error guardando tags FLAC en %s: %s", file_path, exc)

    # ------------------------------------------------------------------ #
    # Letras sincronizadas (syncedlyrics)                                  #
    # ------------------------------------------------------------------ #

    def _fetch_lyrics(self, metadata: dict) -> Optional[str]:
        """
        Busca letras (preferentemente sincronizadas LRC) via syncedlyrics.
        Retorna None si la librería no está instalada o no hay resultados
        — nunca lanza, para no romper el resto del post-procesado.
        """
        title = metadata.get("title", "")
        artist = metadata.get("artist", "")
        if not title:
            return None

        try:
            import syncedlyrics
        except ImportError:
            logger.debug("syncedlyrics no instalado; se omite embebido de letras.")
            return None

        query = f"{artist} {title}".strip()
        try:
            lrc = syncedlyrics.search(query)
            if lrc:
                logger.debug("✓ Letras encontradas para: %s", query)
            return lrc or None
        except Exception as exc:
            logger.warning("Error buscando letras para '%s': %s", query, exc)
            return None

    # ------------------------------------------------------------------ #
    # Organizacion de biblioteca con beets (opcional)                      #
    # ------------------------------------------------------------------ #

    def _organize_with_beets(self, file_path: str) -> str:
        """
        Importa el archivo a la biblioteca de beets (`beet import`), que
        renombra/mueve el archivo segun su config de beets y le agrega
        metadatos de MusicBrainz. Requiere el CLI `beet` en PATH y que el
        usuario ya tenga beets configurado (~/.config/beets/config.yaml).

        Best-effort: si beets no está instalado o falla, se deja el archivo
        tal cual (donde lo dejó el resto del pipeline) y solo se loguea.
        """
        beet_exe = shutil.which("beet")
        if not beet_exe:
            logger.debug("beets no está instalado (comando 'beet' no encontrado); se omite.")
            return file_path

        try:
            result = subprocess.run(
                [beet_exe, "import", "-q", "--singletons", file_path],
                capture_output=True,
                timeout=60,
                text=True,
            )
            if result.returncode != 0:
                logger.warning(
                    "beets import falló (código %s): %s",
                    result.returncode, result.stderr[:300],
                )
                return file_path

            logger.info("✓ Archivo importado a la biblioteca de beets: %s", file_path)
            # beets mueve el archivo segun su propio esquema de paths;
            # no conocemos la ruta final sin parsear su config, así que
            # devolvemos la ruta original como referencia informativa.
            return file_path
        except subprocess.TimeoutExpired:
            logger.warning("beets import timeout (>60s) en: %s", file_path)
            return file_path
        except Exception as exc:
            logger.warning("Error ejecutando beets import: %s", exc)
            return file_path

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
