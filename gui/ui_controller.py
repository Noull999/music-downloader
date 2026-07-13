"""
UIController: Orquesta la lógica de negocio separada de la presentación.
Separa MainWindow (presentación pura) de lógica (eventos, callbacks).
"""
import logging
import os
import json
from typing import Callable, Optional
from models import TrackInfo, STATUS_DONE, STATUS_ERROR
from download_manager import DownloadManager
from db.history import DownloadHistory
from config.manager import ConfigManager
from sync.soundcloud_api import SoundCloudAPIClient

logger = logging.getLogger(__name__)


class UIController:
    """
    Controlador central que orquesta:
    - ConfigManager (persistencia)
    - DownloadHistory (BD de descargas)
    - DownloadManager (descarga)
    - Callbacks a GUI
    """

    def __init__(self, base_dir: str = None):
        # Construir ruta config.json a partir de base_dir
        if base_dir:
            config_path = os.path.join(base_dir, "config.json")
        else:
            config_path = "config.json"

        self.config = ConfigManager(config_path)
        self.history = DownloadHistory()
        self.download_manager = DownloadManager()

        # Validar config en startup
        if not self.config.validate():
            logger.warning("⚠️  Configuración tiene valores inválidos")

    def get_config(self) -> dict:
        """Retorna toda la configuración."""
        return self.config.get_all()

    def get_config_value(self, key: str, default=None):
        """Obtiene valor de config."""
        return self.config.get(key, default)

    def set_config_value(self, key: str, value) -> None:
        """Establece valor de config (se persiste automáticamente)."""
        self.config.set(key, value)
        logger.debug(f"Config actualizado: {key} = {value}")

    def is_track_downloaded(self, url: str) -> bool:
        """Verifica si track ya fue descargado."""
        return self.history.is_downloaded(url)

    def get_download_count(self) -> int:
        """Retorna total de descargas registradas."""
        return self.history.get_download_count()

    def get_recent_downloads(self, limit: int = 50):
        """Retorna descargas recientes."""
        return self.history.get_recent_downloads(limit)

    def record_download(self, track: TrackInfo) -> None:
        """Registra descarga en historial."""
        try:
            # Usar local_path del track si existe, si no usar el track.url como fallback
            local_path = getattr(track, 'local_path', '')

            logger.debug(f"Registrando descarga: {track.title} (url: {track.url[:50]}...)")

            self.history.add_download(
                url=track.url,
                title=track.title,
                artist=track.artist,
                album=track.album,
                platform=track.platform,
                local_path=local_path,
                duration=getattr(track, 'duration', 0),
            )
            logger.info(f"✓ Descarga registrada: {track.title}")
        except Exception as e:
            logger.error(f"Error registrando descarga: {e}", exc_info=True)

    def start_download_manager(self) -> None:
        """Inicia el thread pool de descargas."""
        max_workers = self.config.get("max_workers", 3)
        self.download_manager.start(max_workers)
        logger.info(f"DownloadManager iniciado con {max_workers} workers")

    def shutdown_download_manager(self) -> None:
        """Cierra el thread pool."""
        self.download_manager.shutdown()
        logger.info("DownloadManager cerrado")

    def pause_downloads(self) -> None:
        """Pausa todas las descargas."""
        self.download_manager.pause_all()
        logger.info("⏸️  Descargas pausadas")

    def resume_downloads(self) -> None:
        """Reanuda descargas pausadas."""
        self.download_manager.resume_all()
        logger.info("▶️  Descargas reanudadas")

    def cancel_download(self, url: str) -> None:
        """Cancela descarga específica."""
        self.download_manager.cancel_track(url)

    def cancel_all_downloads(self) -> None:
        """Cancela todas las descargas."""
        self.download_manager.cancel_all()

    def get_stats(self) -> dict:
        """Retorna estadísticas de descarga."""
        return self.history.get_stats()

    def export_history(self, output_path: str) -> None:
        """Exporta historial a CSV."""
        self.history.export_to_csv(output_path)
        logger.info(f"✓ Historial exportado a: {output_path}")

    def reset_history(self) -> None:
        """Limpia completamente el historial."""
        self.history.clear_history()
        logger.warning("✓ Historial borrado")

    def reset_config(self) -> None:
        """Resetea config a valores por defecto."""
        self.config.reset_to_defaults()
        logger.warning("✓ Configuración reseteada a defaults")

    def import_soundcloud_likes(self) -> dict:
        """
        Importa tus likes de SoundCloud a la BD como "ya descargados".
        No descarga archivos, solo guarda metadatos.

        Returns:
            {
                'success': bool,
                'imported': int,
                'skipped': int,
                'error': str or None
            }
        """
        try:
            # Cargar config con estructura anidada - intenta 2 métodos
            config_path = self.config.config_path

            # Método 1: Leer archivo directamente
            try:
                with open(config_path, 'r', encoding='utf-8') as f:
                    full_config = json.load(f)
            except (FileNotFoundError, json.JSONDecodeError):
                # Fallback: usar lo que ya está en memoria
                full_config = self.config.get_all()

            sc_config = full_config.get("soundcloud", {})
            oauth_token = sc_config.get("oauth_token", "").strip()
            client_id = sc_config.get("client_id", "").strip()

            # Debug logging
            logger.debug(f"Config path: {config_path}")
            logger.debug(f"SoundCloud config keys: {list(sc_config.keys())}")
            logger.debug(f"Token presente: {bool(oauth_token)}")
            logger.debug(f"Client ID presente: {bool(client_id)}")

            if not oauth_token or not client_id:
                return {
                    'success': False,
                    'imported': 0,
                    'skipped': 0,
                    'error': f'OAuth token o client_id no configurados. Config path: {config_path}'
                }

            # Conectar a SoundCloud
            logger.info("🔄 Conectando a SoundCloud...")
            api = SoundCloudAPIClient(oauth_token, client_id)

            # Validar credenciales
            logger.info("🔐 Validando credenciales...")
            user_info = api.validate_credentials()
            if not user_info:
                return {
                    'success': False,
                    'imported': 0,
                    'skipped': 0,
                    'error': 'Credenciales inválidas o token expirado'
                }
            logger.info(f"✓ Conectado como: {user_info.get('full_name', 'Unknown')}")

            # Obtener likes
            logger.info("📥 Obteniendo tus likes de SoundCloud...")
            likes = api.get_likes()

            if not likes:
                return {
                    'success': True,
                    'imported': 0,
                    'skipped': 0,
                    'error': 'No hay likes en tu cuenta'
                }

            # Importar a historial
            imported = 0
            skipped = 0

            for like in likes:
                try:
                    # Verificar si ya existe
                    if self.history.is_downloaded(like.url):
                        skipped += 1
                        continue

                    # Agregar como "ya descargado"
                    self.history.add_download(
                        url=like.url,
                        title=like.title,
                        artist=like.artist,
                        album="",
                        platform="soundcloud",
                        local_path="",  # Sin archivo local
                        duration=like.duration_ms // 1000 if like.duration_ms else 0,
                    )
                    imported += 1

                except Exception as e:
                    logger.error(f"Error importando {like.title}: {e}")
                    skipped += 1

            logger.info(f"✅ Importados: {imported} likes | Omitidos: {skipped}")

            return {
                'success': True,
                'imported': imported,
                'skipped': skipped,
                'error': None
            }

        except Exception as e:
            error_msg = f"Error sincronizando likes: {str(e)}"
            logger.error(error_msg)
            return {
                'success': False,
                'imported': 0,
                'skipped': 0,
                'error': error_msg
            }
