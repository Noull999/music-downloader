"""
Handler para YouTube — videos individuales, playlists y YouTube Music.
URLs soportadas:
  - youtube.com/watch?v=XXX
  - youtu.be/XXX
  - music.youtube.com/watch?v=XXX
  - youtube.com/playlist?list=XXX
  - youtube.com/watch?v=XXX&list=YYY  (video + playlist)
"""
import glob as _glob
import logging
import os
import re
from typing import Callable, Optional
from urllib.parse import urlparse, parse_qs

import yt_dlp

from handlers.base_handler import BaseHandler, TrackMetadata, ffmpeg_location

logger = logging.getLogger(__name__)

# Mensajes de error mapeados desde errores de yt-dlp
ERROR_MESSAGES: dict[str, str] = {
    "video_unavailable": "Video no disponible o eliminado",
    "private_video": "Video privado — no se puede descargar",
    "age_restricted": "Video con restricción de edad — requiere login",
    "region_blocked": "Video bloqueado en tu región",
    "live_stream": "Es un livestream en curso — no se puede descargar",
    "copyright_block": "Video bloqueado por copyright en tu país",
    "rate_limit": "YouTube está limitando descargas. Esperá unos minutos.",
    "members_only": "Contenido exclusivo para miembros del canal",
}

_YT_DOMAINS = {
    "youtube.com",
    "www.youtube.com",
    "youtu.be",
    "music.youtube.com",
    "m.youtube.com",
}


class YouTubeHandler(BaseHandler):

    def can_handle(self, url: str) -> bool:
        try:
            host = urlparse(url.strip()).netloc.lower()
            return host in _YT_DOMAINS
        except Exception:
            return False

    # ------------------------------------------------------------------ #
    # Detección de tipo de URL                                             #
    # ------------------------------------------------------------------ #

    def url_has_playlist(self, url: str) -> bool:
        """Retorna True si la URL tiene parámetro list= (puede ser video+playlist)."""
        try:
            qs = parse_qs(urlparse(url).query)
            return "list" in qs
        except Exception:
            return False

    def url_has_video(self, url: str) -> bool:
        """Retorna True si la URL tiene parámetro v= (video individual)."""
        try:
            parsed = urlparse(url)
            qs = parse_qs(parsed.query)
            return "v" in qs or parsed.netloc == "youtu.be"
        except Exception:
            return False

    def is_video_with_playlist(self, url: str) -> bool:
        """Retorna True si la URL es un video individual dentro de una playlist."""
        return self.url_has_video(url) and self.url_has_playlist(url)

    def strip_playlist_param(self, url: str) -> str:
        """Retorna la URL sin el parámetro list= (solo el video)."""
        from urllib.parse import urlencode, urlunparse
        parsed = urlparse(url)
        qs = parse_qs(parsed.query, keep_blank_values=True)
        qs.pop("list", None)
        qs.pop("index", None)
        new_query = urlencode({k: v[0] for k, v in qs.items()})
        return urlunparse(parsed._replace(query=new_query))

    # ------------------------------------------------------------------ #
    # Metadatos                                                            #
    # ------------------------------------------------------------------ #

    def get_metadata(self, url: str) -> list[TrackMetadata]:
        """
        Extrae metadatos.
        - URL de playlist pura → retorna todos los tracks (flat, rápido)
        - URL de video individual → retorna [track] con info completa
        - URL video+playlist → retorna [track] del video solamente;
          el GUI pregunta si el usuario quiere la playlist completa
        """
        is_playlist_only = (
            self.url_has_playlist(url) and not self.url_has_video(url)
        )

        if is_playlist_only:
            return self._fetch_playlist(url)

        # Video individual (con o sin list=)
        video_url = self.strip_playlist_param(url) if self.is_video_with_playlist(url) else url
        track = self._fetch_single(video_url)

        # Si también tiene playlist, marcar para que el GUI ofrezca la opción
        if self.is_video_with_playlist(url):
            track._playlist_url = url  # type: ignore[attr-defined]

        return [track]

    def get_playlist_tracks(self, playlist_url: str) -> list[TrackMetadata]:
        """Extrae todos los tracks de una playlist (llamado explícitamente por el GUI)."""
        return self._fetch_playlist(playlist_url)

    def _fetch_single(self, url: str) -> TrackMetadata:
        """Extrae info completa de un video individual (incluye formatos para detectar calidad)."""
        opts = {
            "quiet": True,
            "no_warnings": True,
            "skip_download": True,
        }
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=False)
        except yt_dlp.utils.DownloadError as exc:
            raise RuntimeError(self._map_error(str(exc))) from exc

        if not info:
            raise RuntimeError("No se pudo obtener información del video.")

        return self._parse(info, url)

    def _fetch_playlist(self, url: str) -> list[TrackMetadata]:
        """Extrae lista de tracks de una playlist de YouTube."""
        opts = {
            "quiet": True,
            "no_warnings": True,
            "extract_flat": "in_playlist",
            "skip_download": True,
            "socket_timeout": 30,  # Aumentado de 10 para playlists grandes
            "retries": 3,          # Aumentado de 1 para mayor robustez
            "ignoreerrors": True,  # Continuar si una entrada falla
        }
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=False)
        except yt_dlp.utils.DownloadError as exc:
            raise RuntimeError(self._map_error(str(exc))) from exc

        if not info:
            raise RuntimeError("No se pudo obtener la playlist.")

        entries = info.get("entries") or []
        tracks = []
        for entry in entries:
            if entry:
                try:
                    tracks.append(self._parse(entry, url))
                except Exception as e:
                    logger.debug(f"Error parseando entrada de playlist: {e}")
                    continue
        return tracks

    def _parse(self, info: dict, base_url: str = "") -> TrackMetadata:
        # Detectar YouTube Music
        uploader = info.get("uploader") or info.get("channel") or ""
        is_topic = uploader.endswith(" - Topic")
        url_str = info.get("webpage_url") or info.get("url") or base_url
        is_music_url = "music.youtube.com" in url_str

        if is_topic or is_music_url:
            platform = "YouTube Music"
        else:
            platform = "YouTube"

        # Artista: limpiar sufijo "- Topic" si existe
        artist = uploader
        if is_topic:
            artist = uploader[: -len(" - Topic")]
        # Preferir metadatos estructurados si yt-dlp los extrajo
        if info.get("artist"):
            artist = info["artist"]
        elif info.get("creator"):
            artist = info["creator"]

        title = info.get("title") or "Desconocido"
        duration = int(info.get("duration") or 0)
        thumbnail = info.get("thumbnail") or ""
        album = info.get("album") or ""

        # Si no hay thumbnail pero tenemos video_id, generar una URL de thumbnail estándar
        if not thumbnail and info.get("id"):
            video_id = info["id"]
            thumbnail = f"https://img.youtube.com/vi/{video_id}/maxresdefault.jpg"

        # Año: preferir release_year, fallback a upload_date
        year = str(info.get("release_year") or "")
        if not year and info.get("upload_date"):
            year = str(info["upload_date"])[:4]

        track_id = str(info.get("id") or url_str)

        # Calidad detectada (solo disponible con full info, no en extract_flat)
        formats = info.get("formats") or []
        detected_quality = self._best_audio_quality(formats)
        available = self._all_audio_qualities(formats)

        return TrackMetadata(
            url=url_str,
            title=title,
            artist=artist,
            duration=duration,
            thumbnail_url=thumbnail,
            album=album,
            year=year,
            available_qualities=available,
            platform=platform,
            detected_quality=detected_quality,
            track_id=track_id,
            genre=str(info.get("genre") or ""),
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
        yt_format = quality_preset.get("yt_format", "bestaudio/best")

        postprocessors: list[dict] = []
        if convert_to:
            postprocessors.append({
                "key": "FFmpegExtractAudio",
                "preferredcodec": convert_to,
                "preferredquality": quality_preset.get("bitrate", "0"),
            })
        postprocessors += [
            {"key": "FFmpegMetadata", "add_metadata": True},
            {"key": "EmbedThumbnail"},
        ]

        ydl_opts: dict = {
            "format": yt_format,
            "outtmpl": output_path + ".%(ext)s",
            "postprocessors": postprocessors,
            "writethumbnail": False,
            "progress_hooks": [hook],
            "quiet": False,
            "no_warnings": True,
            "retries": 3,
            "fragment_retries": 3,
            "no_playlist": True,
        }
        if loc := ffmpeg_location():
            ydl_opts["ffmpeg_location"] = loc

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])
        except yt_dlp.utils.DownloadError as exc:
            err = str(exc)
            if "Cancelado" in err or "Cancelled" in err:
                raise RuntimeError("cancelled") from exc
            raise RuntimeError(self._map_error(err)) from exc

        return _find_file(output_path, convert_to)

    # ------------------------------------------------------------------ #
    # Mapeo de errores                                                     #
    # ------------------------------------------------------------------ #

    def _map_error(self, msg: str) -> str:
        low = msg.lower()
        checks = [
            (["video unavailable", "this video is unavailable", "has been removed"], "video_unavailable"),
            (["private video", "is private"], "private_video"),
            (["age", "sign in to confirm your age"], "age_restricted"),
            (["not available in your country", "blocked in your country", "region"], "region_blocked"),
            (["live stream", "live event", "is live"], "live_stream"),
            (["copyright", "blocked on copyright grounds"], "copyright_block"),
            (["too many requests", "rate limit", "429"], "rate_limit"),
            (["members only", "member"], "members_only"),
        ]
        for keywords, key in checks:
            if any(kw in low for kw in keywords):
                return ERROR_MESSAGES[key]
        # Limpiar ruido de yt-dlp
        msg = re.sub(r"ERROR: \[youtube\] [\w:./]+: ", "", msg)
        return msg[:200]


def _find_file(base: str, preferred_ext: str | None) -> str:
    if preferred_ext:
        candidate = base + f".{preferred_ext}"
        if os.path.exists(candidate):
            return candidate
    matches = [
        m for m in _glob.glob(base + ".*")
        if not m.endswith((".webp", ".jpg", ".png", ".part"))
    ]
    return matches[0] if matches else base + ".mp3"
