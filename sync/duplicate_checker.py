"""
Verifica si una canción ya existe en la carpeta o historial.
Maneja: nombres exactos, nombres similares (fuzzy), URLs en historial.
"""
import os
import unicodedata
import re
import logging
from pathlib import Path
from thefuzz import fuzz

logger = logging.getLogger(__name__)


class DuplicateChecker:
    """
    Detecta duplicados usando tres estrategias:
    1. Historial de URLs (más confiable, sin falsos positivos)
    2. Búsqueda fuzzy en nombres de archivos (tolera tildes, espacios)
    3. Nombres exactos
    """

    SIMILARITY_THRESHOLD = 55  # % de similitud para considerar duplicado (muy tolerante para archivos reorganizados por Picard)

    def __init__(self, download_history, similarity_threshold: int = 85):
        """
        Args:
            download_history: Objeto DownloadHistory con método is_downloaded(url)
            similarity_threshold: % de similitud fuzzy (0-100)
        """
        self.history = download_history
        self.SIMILARITY_THRESHOLD = similarity_threshold

    def is_duplicate(
        self,
        track_url: str,
        track_title: str,
        artist: str,
        folder: str
    ) -> tuple[bool, str]:
        """
        Verifica si una canción es duplicado.

        Args:
            track_url: URL de SoundCloud (permalink_url)
            track_title: Título de la canción
            artist: Nombre del artista
            folder: Carpeta de descargas

        Returns:
            (es_duplicado: bool, razon: str)
            razon explica por qué es duplicado (para mostrar al usuario)
        """

        # Verificación 1: ¿Está en el historial por URL? (más confiable)
        if self.history.is_downloaded(track_url):
            logger.debug(f"Duplicado por historial: {track_url}")
            return True, "Ya descargada anteriormente (historial)"

        # Verificación 2: ¿Existe archivo similar en la carpeta?
        if os.path.exists(folder):
            similar_file = self._find_similar_file(track_title, artist, folder)
            if similar_file:
                logger.debug(
                    f"Duplicado por archivo similar: "
                    f"{similar_file} ≈ {artist} - {track_title}"
                )
                return True, f"Archivo similar encontrado: {similar_file}"

        return False, ""

    def get_new_tracks(
        self,
        all_likes: list,
        download_folder: str
    ) -> tuple[list, list]:
        """
        Filtra una lista de tracks y separa nuevos de duplicados.

        Args:
            all_likes: Lista de SoundCloudTrack
            download_folder: Ruta a la carpeta de descargas

        Returns:
            (tracks_nuevos: list, tracks_duplicados: list[tuple])
            tracks_duplicados es lista de (track, razon)
        """
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

        logger.info(
            f"Duplicados: {len(duplicates)} | "
            f"Nuevos: {len(new_tracks)}"
        )
        return new_tracks, duplicates

    # ── Internos ─────────────────────────────────────────────────────── #

    def _normalize(self, text: str) -> str:
        """
        Normaliza texto para comparación fuzzy.
        - Sin tildes/diacríticos (á→a, ñ→n)
        - Minúsculas
        - Sin caracteres especiales (guardar espacios)
        - Espacios normalizados
        """
        # Quitar tildes y diacríticos (NFD decomposition)
        text = unicodedata.normalize('NFD', text)
        text = ''.join(c for c in text if unicodedata.category(c) != 'Mn')

        # Minúsculas
        text = text.lower()

        # Quitar caracteres especiales excepto espacios
        text = re.sub(r'[^\w\s]', '', text)

        # Normalizar espacios múltiples a uno solo
        text = ' '.join(text.split())

        return text

    def _find_similar_file(self, title: str, artist: str, folder: str) -> str | None:
        """
        Busca un archivo con nombre similar en la carpeta de destino.

        Estrategia:
        1. Normalizar search_string (artist + title)
        2. Buscar en archivos de audio con extensiones comunes
        3. Comparar con fuzzy matching (tolera tildes, espacios, mayúsculas)
        4. Si similaridad > threshold, considerarlo duplicado

        Args:
            title: Título de la canción
            artist: Artista
            folder: Ruta carpeta

        Returns:
            Nombre del archivo similar encontrado, o None
        """
        search_string = self._normalize(f"{artist} {title}")
        audio_extensions = {'.mp3', '.m4a', '.flac', '.wav', '.ogg', '.opus', '.aac'}

        logger.debug(f"Buscando duplicado de: '{artist} - {title}' (normalizado: {search_string})")

        try:
            for file_path in Path(folder).rglob('*'):
                # Saltar si no es archivo o no es audio
                if not file_path.is_file():
                    continue
                if file_path.suffix.lower() not in audio_extensions:
                    continue

                # Normalizar nombre del archivo (sin extensión)
                file_name = self._normalize(file_path.stem)

                # Comparar con múltiples métodos de fuzzy matching
                # y usar la mejor similitud encontrada
                token_sort = fuzz.token_sort_ratio(search_string, file_name)
                partial = fuzz.partial_token_sort_ratio(search_string, file_name)
                ratio = fuzz.ratio(search_string, file_name)

                similarity = max(token_sort, partial, ratio)

                if similarity >= self.SIMILARITY_THRESHOLD:
                    logger.info(
                        f"✓ Duplicado encontrado: '{file_path.name}' "
                        f"(similitud {similarity}% ≈ {artist} - {title})"
                    )
                    return file_path.name

        except (OSError, PermissionError) as e:
            logger.warning(f"Error explorando carpeta {folder}: {e}")

        return None
