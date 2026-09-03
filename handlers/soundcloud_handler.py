"""
Handler para SoundCloud — tracks individuales, sets y perfiles de usuario.
"""
import glob as _glob
import logging
import os
from typing import Callable, Optional
from urllib.parse import urlparse

import yt_dlp

from handlers.base_handler import BaseHandler, TrackMetadata, ffmpeg_location

logger = logging.getLogger(__name__)

_PLATFORM = "SoundCloud"


class SoundCloudHandler(BaseHandler):

    def can_handle(self, url: str) -> bool:
        try:
            host = urlparse(url.strip()).netloc.lower().replace("www.", "")
            return host == "soundcloud.com"
        except Exception:
            return False

    # ------------------------------------------------------------------ #
    # Metadatos                                                            #
    # ------------------------------------------------------------------ #

    def get_metadata(self, url: str) -> list[TrackMetadata]:
        ydl_opts = {
            "quiet": True,
            "no_warnings": True,
            "extract_flat": "in_playlist",
            "skip_download": True,
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            try:
                info = ydl.extract_info(url, download=False)
            except yt_dlp.utils.DownloadError as exc:
                raise RuntimeError(_clean(str(exc))) from exc

        if not info:
            raise RuntimeError("No se pudo obtener información de la URL.")

        if info.get("_type") in ("playlist", "multi_video"):
            tracks = []
            for entry in (info.get("entries") or []):
                if entry:
                    tracks.append(self._parse(entry, url))
            return tracks

        # Single track — re-fetch with full info para detectar calidad
        full = self._full_info(url)
        return [self._parse(full or info, url)]

    def _full_info(self, url: str) -> dict | None:
        opts = {"quiet": True, "no_warnings": True, "skip_download": True}
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                return ydl.extract_info(url, download=False)
        except Exception:
            return None

    def _parse(self, info: dict, base_url: str = "") -> TrackMetadata:
        title = info.get("title") or "Desconocido"
        artist = (
            info.get("uploader")
            or info.get("artist")
            or info.get("creator")
            or "Desconocido"
        )
        duration = int(info.get("duration") or 0)
        thumbnail = info.get("thumbnail") or ""
        album = info.get("album") or ""
        year = str(info.get("release_year") or "")
        url = info.get("webpage_url") or info.get("url") or base_url
        track_id = str(info.get("id") or url)

        formats = info.get("formats") or []
        quality = self._best_audio_quality(formats) or "128kbps Mp3"
        available = self._all_audio_qualities(formats) or ["128kbps Mp3"]

        return TrackMetadata(
            url=url,
            title=title,
            artist=artist,
            duration=duration,
            thumbnail_url=thumbnail,
            album=album,
            year=year,
            available_qualities=available,
            platform=_PLATFORM,
            detected_quality=quality,
            track_id=track_id,
            genre=info.get("genre") or "",
            tags=" ".join(info.get("tags") or []) if isinstance(info.get("tags"), list)
                 else (info.get("tags") or ""),
        )

    # ------------------------------------------------------------------ #
    # Descarga                                                             #
    # ------------------------------------------------------------------ #

    def download(
        self,
        url: str,
        output_path: str,
        quality_preset: dict,
        progress_callback: Callable[[float], None],
        cancel_check: Optional[Callable[[], bool]] = None,
        oauth_token: str = "",
        on_speed: Optional[Callable[[str, str], None]] = None,
    ) -> str:

        def hook(d: dict):
            if cancel_check and cancel_check():
                raise yt_dlp.utils.DownloadError("Cancelado por el usuario")
            if d["status"] == "downloading":
                if on_speed:
                    on_speed(d.get("_speed_str", "").strip(), d.get("_eta_str", "").strip())
                frag_idx = d.get("fragment_index") or 0
                frag_total = d.get("fragment_count") or 0
                if frag_total and progress_callback:
                    progress_callback(min(frag_idx / frag_total, 0.99))
                else:
                    total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
                    done = d.get("downloaded_bytes") or 0
                    if total and progress_callback:
                        progress_callback(min(done / total, 0.99))
            elif d["status"] == "finished" and progress_callback:
                progress_callback(1.0)

        convert_to = quality_preset.get("convert_to")
        sc_format = quality_preset.get("sc_format", "bestaudio/best")

        postprocessors: list[dict] = []
        if convert_to:
            postprocessors.append({
                "key": "FFmpegExtractAudio",
                "preferredcodec": convert_to,
                "preferredquality": quality_preset.get("bitrate", "0"),
            })
            # FFmpegMetadata embebe tags básicos vía ffmpeg.
            # La carátula se embebe por PostProcessor (mutagen) para mayor confiabilidad;
            # EmbedThumbnail de yt-dlp deja archivos .jpg sueltos cuando falla.
            postprocessors.append({"key": "FFmpegMetadata", "add_metadata": True})

        ydl_opts: dict = {
            "format": sc_format,
            "outtmpl": output_path + ".%(ext)s",
            "postprocessors": postprocessors,
            "writethumbnail": False,
            "progress_hooks": [hook],
            "quiet": False,
            "no_warnings": True,
            "retries": 3,
            "fragment_retries": 3,
        }
        if loc := ffmpeg_location():
            ydl_opts["ffmpeg_location"] = loc
        if oauth_token:
            ydl_opts["extractor_args"] = {
                "soundcloud": {"oauth_token": [oauth_token]}
            }

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])
        except yt_dlp.utils.DownloadError as exc:
            err = str(exc)
            if "Cancelado" in err or "Cancelled" in err:
                raise RuntimeError("cancelled") from exc
            if "Go+" in err or "premium" in err.lower():
                raise RuntimeError("Track requiere SoundCloud Go+ (de pago)") from exc
            raise RuntimeError(_clean(err)) from exc

        return _find_file(output_path, convert_to)


def _clean(msg: str) -> str:
    import re
    msg = re.sub(r"ERROR: \[soundcloud\] [\w:./]+: ", "", msg)
    return msg[:200]


def _find_file(base: str, preferred_ext: str | None) -> str:
    """Encuentra el archivo descargado dado el path base."""
    if preferred_ext:
        candidate = base + f".{preferred_ext}"
        if os.path.exists(candidate):
            return candidate
    matches = [
        m for m in _glob.glob(base + ".*")
        if not m.endswith((".webp", ".jpg", ".png", ".part"))
    ]
    return matches[0] if matches else base + ".mp3"
