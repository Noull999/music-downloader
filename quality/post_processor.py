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
from typing import Optional

from handlers.base_handler import ffmpeg_location

logger = logging.getLogger(__name__)


def _ffmpeg_exe() -> str:
    loc = ffmpeg_location()
    return os.path.join(loc, "ffmpeg.exe") if loc else "ffmpeg"


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
        if (self.embed_metadata or self.embed_artwork) and ext == ".mp3":
            self._embed_tags(input_file, metadata, thumbnail_url if self.embed_artwork else "")

        return input_file

    # ------------------------------------------------------------------ #
    # Filtros ffmpeg                                                       #
    # ------------------------------------------------------------------ #

    def _apply_ffmpeg_filters(self, input_file: str) -> str:
        ffmpeg = _ffmpeg_exe()
        if not os.path.isfile(ffmpeg) and not shutil.which(ffmpeg):
            logger.warning("ffmpeg no encontrado; se omite post-procesado de audio.")
            return input_file

        filters: list[str] = []

        if self.normalize_volume:
            # EBU R128 — estandar profesional de normalizacion de loudness
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
            )
            if result.returncode == 0 and os.path.exists(temp_file):
                os.replace(temp_file, input_file)
                logger.info("Filtros ffmpeg aplicados: %s", filter_chain)
            else:
                logger.warning(
                    "ffmpeg retorno %d: %s",
                    result.returncode,
                    result.stderr.decode(errors="replace")[:300],
                )
                if os.path.exists(temp_file):
                    os.remove(temp_file)
        except (subprocess.TimeoutExpired, FileNotFoundError, OSError) as exc:
            logger.warning("Error aplicando filtros ffmpeg: %s", exc)
            if os.path.exists(temp_file):
                os.remove(temp_file)

        return input_file

    # ------------------------------------------------------------------ #
    # Embebido de tags con mutagen                                         #
    # ------------------------------------------------------------------ #

    def _embed_tags(self, file_path: str, metadata: dict, thumbnail_url: str) -> None:
        try:
            from mutagen.id3 import ID3, APIC, TIT2, TPE1, TALB, TDRC, error as ID3Error
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
                if metadata.get("title"):
                    audio.tags.add(TIT2(encoding=3, text=metadata["title"]))
                if metadata.get("artist"):
                    audio.tags.add(TPE1(encoding=3, text=metadata["artist"]))
                if metadata.get("album"):
                    audio.tags.add(TALB(encoding=3, text=metadata["album"]))
                if metadata.get("year"):
                    audio.tags.add(TDRC(encoding=3, text=metadata["year"]))

            if self.embed_artwork and thumbnail_url:
                img_data = self._fetch_image(thumbnail_url)
                if img_data:
                    audio.tags.add(
                        APIC(
                            encoding=3,
                            mime="image/jpeg",
                            type=3,   # Cover (front)
                            desc="Cover",
                            data=img_data,
                        )
                    )

            audio.save()
        except Exception as exc:
            logger.warning("Error embebiendo tags en %s: %s", file_path, exc)

    def _fetch_image(self, url: str) -> Optional[bytes]:
        try:
            import requests
            resp = requests.get(url, timeout=10)
            resp.raise_for_status()
            return resp.content
        except Exception as exc:
            logger.warning("No se pudo descargar thumbnail para tags: %s", exc)
            return None
