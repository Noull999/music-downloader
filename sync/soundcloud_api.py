"""
Cliente para la API interna de SoundCloud (api-v2.soundcloud.com).
No es scraping: son requests que hace el navegador oficial de soundcloud.com.
No requiere Playwright ni Selenium.
"""
import requests
import time
import logging
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class SoundCloudTrack:
    """Metadatos de una canción de SoundCloud extraída de la API."""
    id: int
    url: str
    title: str
    artist: str
    duration_ms: int
    artwork_url: Optional[str]
    genre: Optional[str]
    created_at: str

    def __repr__(self) -> str:
        return f"<SoundCloudTrack '{self.artist}' - '{self.title}' ({self.duration_ms}ms)>"


class SoundCloudAPIClient:
    """
    Cliente para la API interna de SoundCloud (api-v2.soundcloud.com).
    Usa OAuth token del navegador (extrae manualmente desde F12 → Network).
    """

    BASE_URL = "https://api-v2.soundcloud.com"

    def __init__(self, oauth_token: str, client_id: str):
        """
        Inicializa el cliente con credenciales.

        Args:
            oauth_token: Formato "OAuth 2-XXXXX-XXXXX-XXXXXXXXXX"
                        Extraer desde DevTools (F12) → Network → Authorization header
            client_id: String alfanumérico. Aparece en cualquier request a api-v2
                       como parámetro "client_id=XXXXX"
        """
        self.oauth_token = oauth_token.strip()
        self.client_id = client_id.strip()
        self.user_id = None  # Se obtiene en validate_credentials()
        self.session = requests.Session()
        self._setup_headers()

    def _setup_headers(self):
        """Configura headers para que parezcan requests del navegador oficial."""
        self.session.headers.update({
            "Authorization": self.oauth_token,
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                         "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "Origin": "https://soundcloud.com",
            "Referer": "https://soundcloud.com/",
            "Content-Type": "application/json; charset=utf-8",
        })

    def validate_credentials(self) -> dict:
        """
        Verifica que el token OAuth es válido y retorna info del usuario actual.

        Returns:
            {
                "id": int,
                "username": str,
                "full_name": str,
                "followers_count": int,
                "likes_count": int
            }

        Raises:
            ValueError: Si el token es inválido o expirado
            ConnectionError: Si hay error en la API
        """
        try:
            response = self.session.get(
                f"{self.BASE_URL}/me",
                params={"client_id": self.client_id},
                timeout=10
            )
        except requests.Timeout:
            raise ConnectionError("Timeout conectando a SoundCloud API")
        except requests.RequestException as e:
            raise ConnectionError(f"Error de red: {e}")

        if response.status_code == 401:
            logger.warning("Token OAuth inválido o expirado")
            raise ValueError(
                "Token OAuth inválido o expirado. "
                "Extrae uno nuevo desde soundcloud.com (F12 → Network)"
            )

        if response.status_code != 200:
            logger.error(f"API error {response.status_code}: {response.text[:200]}")
            raise ConnectionError(
                f"Error de SoundCloud API: {response.status_code}"
            )

        data = response.json()
        self.user_id = data.get("id")
        result = {
            "id": self.user_id,
            "username": data.get("username", "Unknown"),
            "full_name": data.get("full_name", ""),
            "followers_count": data.get("followers_count", 0),
            "likes_count": data.get("public_likes_count", 0),
        }

        logger.info(
            f"✅ Credenciales válidas | Usuario: {result['username']} | "
            f"Likes: {result['likes_count']}"
        )
        return result

    def get_likes(self, limit: int = 200, max_pages: int = 50) -> list[SoundCloudTrack]:
        """
        Obtiene TODOS los likes del usuario autenticado, paginando automáticamente.

        Args:
            limit: Cantidad de items por página (máx 200 por la API)
            max_pages: Límite de páginas para evitar loops infinitos (safety)

        Returns:
            Lista de SoundCloudTrack ordenados por recencia (más nuevos primero)

        Raises:
            ConnectionError: Si hay error en la API
        """
        if not self.user_id:
            raise ValueError("Necesitas validar credenciales primero")

        tracks = []
        next_href = None
        page = 0

        logger.info(f"Obteniendo likes (máx {limit} por página)...")

        while page < max_pages:
            try:
                if next_href:
                    # Usar URL de siguiente página directamente
                    # (Ya incluye todos los parámetros necesarios)
                    response = self.session.get(next_href, timeout=10)
                else:
                    # Primera página - usar endpoint correcto: /users/{user_id}/likes
                    response = self.session.get(
                        f"{self.BASE_URL}/users/{self.user_id}/likes",
                        params={
                            "client_id": self.client_id,
                            "limit": limit,
                            "offset": 0,
                        },
                        timeout=10
                    )

            except requests.Timeout:
                logger.error(f"Timeout en página {page}")
                break
            except requests.RequestException as e:
                logger.error(f"Error de red en página {page}: {e}")
                break

            if response.status_code == 429:
                # Rate limiting: esperar y reintentar
                logger.warning(
                    "SoundCloud limitó requests (429). Esperando 30 segundos..."
                )
                time.sleep(30)
                continue

            if response.status_code != 200:
                logger.warning(
                    f"Error en página {page}: {response.status_code}. "
                    f"Deteniendo paginación."
                )
                break

            try:
                data = response.json()
            except requests.JSONDecodeError:
                logger.error(f"Respuesta no-JSON en página {page}")
                break

            collection = data.get("collection", [])
            logger.debug(f"Página {page}: {len(collection)} items")

            # Procesar cada item de la colección
            for item in collection:
                # Los likes pueden ser tracks o playlists
                # En /me/likes/tracks, cada item es {track: {...}}
                track_data = item.get("track")

                if not track_data:
                    # Item sin track (raro), saltar
                    continue

                # Filtrar solo tracks (no playlists, videos, etc)
                if track_data.get("kind") != "track":
                    continue

                # Crear objeto SoundCloudTrack
                try:
                    track = SoundCloudTrack(
                        id=track_data["id"],
                        url=track_data.get("permalink_url", ""),
                        title=track_data.get("title", "Unknown"),
                        artist=track_data.get("user", {}).get("username", "Unknown"),
                        duration_ms=track_data.get("duration", 0),
                        artwork_url=track_data.get("artwork_url"),
                        genre=track_data.get("genre"),
                        created_at=track_data.get("created_at", ""),
                    )
                    tracks.append(track)
                except (KeyError, TypeError) as e:
                    logger.warning(f"Error parseando track: {e}")
                    continue

            # Preparar siguiente página
            next_href = data.get("next_href")
            if not next_href:
                logger.info(f"Fin de la paginación. Total: {len(tracks)} likes")
                break

            page += 1
            # Delay entre páginas para no saturar la API
            time.sleep(1)

        # Sort by created_at descending (newest first), with fallback for missing dates
        tracks.sort(key=lambda t: t.created_at or "", reverse=True)

        logger.info(f"✅ Obtenidos {len(tracks)} likes")
        return tracks

    def get_recent_likes(self, count: int = 10) -> list[SoundCloudTrack]:
        """
        Obtiene solo los N likes más recientes. Más rápido para polling periódico.
        Ideal para auto-sync donde solo necesitas saber si hay algo nuevo.

        Args:
            count: Cantidad de likes recientes (default 10)

        Returns:
            Lista de SoundCloudTrack (máximo count items)
        """
        if not self.user_id:
            logger.error("Necesitas validar credenciales primero")
            return []

        logger.info(f"Obteniendo {count} likes más recientes...")
        try:
            response = self.session.get(
                f"{self.BASE_URL}/users/{self.user_id}/likes",
                params={
                    "client_id": self.client_id,
                    "limit": count,
                    "offset": 0,
                },
                timeout=10
            )
        except requests.RequestException as e:
            logger.error(f"Error obteniendo likes recientes: {e}")
            return []

        if response.status_code != 200:
            logger.error(f"Error API: {response.status_code}")
            return []

        try:
            data = response.json()
        except requests.JSONDecodeError:
            return []

        tracks = []
        for item in data.get("collection", []):
            track_data = item.get("track")
            if not track_data or track_data.get("kind") != "track":
                continue

            try:
                tracks.append(SoundCloudTrack(
                    id=track_data["id"],
                    url=track_data.get("permalink_url", ""),
                    title=track_data.get("title", "Unknown"),
                    artist=track_data.get("user", {}).get("username", "Unknown"),
                    duration_ms=track_data.get("duration", 0),
                    artwork_url=track_data.get("artwork_url"),
                    genre=track_data.get("genre"),
                    created_at=track_data.get("created_at", ""),
                ))
            except (KeyError, TypeError):
                continue

        # Sort by created_at descending (newest first), with fallback for missing dates
        tracks.sort(key=lambda t: t.created_at or "", reverse=True)

        logger.info(f"✅ Obtenidos {len(tracks)} likes recientes")
        return tracks
