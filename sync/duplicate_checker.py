"""
Verifica si una canción ya existe en la biblioteca o en el historial.
Maneja: URLs ya descargadas y nombres de archivo similares (fuzzy).

La normalización y comparación difusa vive en sync/match_utils.py, compartida
con la reconciliación de biblioteca para que ambos flujos decidan igual sobre
el mismo par de canciones.
"""
import logging
from pathlib import Path
from typing import Iterable, Optional

from sync import match_utils

logger = logging.getLogger(__name__)


class DuplicateChecker:
    """
    Detecta duplicados con dos estrategias, en orden:

    1. URL en el historial de descargas — exacta, sin falsos positivos.
    2. Archivo de nombre similar en la biblioteca — difusa, tolera tildes,
       mayúsculas, reordenamientos y el ruido de promo ("[FREE DL]", etc).

    La búsqueda difusa recorre TODAS las carpetas de la biblioteca, no solo
    la carpeta de descarga: la música bajada antes de usar la app suele vivir
    en carpetas por género hermanas al destino, y antes no se detectaba,
    así que se re-descargaba.
    """

    def __init__(
        self,
        download_history,
        similarity_threshold: int = match_utils.MATCH_THRESHOLD,
        library_folders: Optional[Iterable[str]] = None,
    ):
        """
        Args:
            download_history: Objeto con método is_downloaded(url)
            similarity_threshold: % de similitud (0-100) sobre títulos ya
                normalizados por match_utils.clean_for_match
            library_folders: Carpetas extra a considerar además de la de
                descarga (p.ej. la raíz de la biblioteca con las carpetas
                por género)
        """
        self.history = download_history
        self.similarity_threshold = similarity_threshold
        self.library_folders = list(library_folders or [])

        # Índice construido bajo demanda y reutilizado: antes se re-recorría
        # el disco entero una vez por cada canción a verificar.
        self._index: Optional[list[tuple[Path, set[str]]]] = None
        self._indexed_folders: Optional[tuple[str, ...]] = None

    # ── API pública ──────────────────────────────────────────────────── #

    def is_duplicate(
        self,
        track_url: str,
        track_title: str,
        artist: str,
        folder: str
    ) -> tuple[bool, str]:
        """
        Verifica si una canción ya la tenés.

        Args:
            track_url: URL de SoundCloud (permalink_url)
            track_title: Título de la canción (según SoundCloud)
            artist: Uploader de SoundCloud (ver match_utils sobre por qué
                    no es necesariamente el artista real)
            folder: Carpeta de descarga

        Returns:
            (es_duplicado, razón_para_mostrar_al_usuario)
        """
        if self.history.is_downloaded(track_url):
            logger.debug("Duplicado por historial: %s", track_url)
            return True, "Ya descargada anteriormente (historial)"

        match = self._find_similar_file(track_title, artist, folder)
        if match:
            return True, f"Archivo similar encontrado: {match}"

        return False, ""

    def get_new_tracks(
        self,
        all_likes: list,
        download_folder: str
    ) -> tuple[list, list]:
        """
        Separa una lista de tracks en nuevos y duplicados.

        Args:
            all_likes: Lista de SoundCloudTrack
            download_folder: Carpeta de descargas

        Returns:
            (tracks_nuevos, [(track, razón), ...])
        """
        # Construye el índice una vez para todo el lote.
        self._ensure_index(download_folder)

        new_tracks = []
        duplicates = []

        for track in all_likes:
            is_dup, reason = self.is_duplicate(
                track.url, track.title, track.artist, download_folder
            )
            if is_dup:
                duplicates.append((track, reason))
            else:
                new_tracks.append(track)

        logger.info("Duplicados: %d | Nuevos: %d", len(duplicates), len(new_tracks))
        return new_tracks, duplicates

    def invalidate_index(self) -> None:
        """
        Descarta el índice cacheado. Llamar tras descargar archivos nuevos
        para que la próxima verificación los tenga en cuenta.
        """
        self._index = None
        self._indexed_folders = None

    # ── Internos ─────────────────────────────────────────────────────── #

    def _folders_to_scan(self, download_folder: str) -> tuple[str, ...]:
        folders = [download_folder, *self.library_folders]
        seen, ordered = set(), []
        for f in folders:
            if f and f not in seen:
                seen.add(f)
                ordered.append(f)
        return tuple(ordered)

    def _ensure_index(self, download_folder: str) -> list[tuple[Path, set[str]]]:
        folders = self._folders_to_scan(download_folder)
        if self._index is None or self._indexed_folders != folders:
            logger.info("Indexando biblioteca para detección de duplicados: %s", ", ".join(folders))
            self._index = match_utils.index_audio_files(folders)
            self._indexed_folders = folders
            logger.info("Índice listo: %d archivos de audio", len(self._index))
        return self._index

    def _find_similar_file(self, title: str, artist: str, folder: str) -> Optional[str]:
        """
        Busca el archivo MÁS parecido de la biblioteca (no el primero que
        supere el umbral). Devuelve su nombre, o None si ninguno alcanza.
        """
        index = self._ensure_index(folder)
        candidates = match_utils.like_candidates(artist, title)
        if not candidates:
            return None

        path, score = match_utils.find_best_match(
            candidates, index, self.similarity_threshold
        )
        if path is None:
            return None

        logger.info(
            "✓ Duplicado encontrado: '%s' (similitud %d%% ≈ %s - %s)",
            path.name, score, artist, title,
        )
        return path.name
