"""
ConfigManager: Gestiona persistencia y validación de configuración.
Separa config de la GUI (MainWindow).
"""
import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, Optional

from utils.exceptions import ConfigurationError

logger = logging.getLogger(__name__)

# Ubicación estable de config.json, igual que la BD (~/.music_downloader/).
# Antes vivía junto al ejecutable/código (base_dir); en el .exe empaquetado
# eso significaba perderlo en cada rebuild (dist/ se borra con --clean).
DEFAULT_CONFIG_PATH = Path.home() / ".music_downloader" / "config.json"


class ConfigManager:
    """Gestiona config.json con validación y valores por defecto."""

    # Esquema por defecto
    DEFAULT_CONFIG = {
        "dest_folder": os.path.expanduser("~/Music"),
        "max_workers": 3,
        "quality_preset": "mp3_320",
        "filename_pattern": "{artist} - {title}",
        "subfolder_by_artist": False,
        "subfolder_by_genre": False,
        "embed_genre": True,
        "normalize_volume": False,
        "remove_silence": False,
        "embed_artwork": True,
        "embed_metadata": True,
        "embed_lyrics": False,
        "organize_with_beets": False,
        "oauth_token": "",
        "delay": 0.5,
        "log_level": "INFO",
        "theme": "dark",
        "color_scheme": "blue",
    }

    def __init__(self, config_path: str = None):
        self.config_path = Path(config_path) if config_path else DEFAULT_CONFIG_PATH
        self._config = {}
        self.load()

    def load(self) -> None:
        """Carga config desde archivo, usa defaults si no existe."""
        try:
            if self.config_path.exists():
                with open(self.config_path, "r", encoding="utf-8") as f:
                    file_config = json.load(f)
                # Merge: archivo + defaults
                self._config = {**self.DEFAULT_CONFIG, **file_config}
                logger.info(f"Configuración cargada desde: {self.config_path}")
            else:
                self._config = self.DEFAULT_CONFIG.copy()
                logger.info("Config no existe, usando defaults")
                self.save()
        except json.JSONDecodeError as e:
            logger.error(f"Error parseando config.json: {e}")
            self._config = self.DEFAULT_CONFIG.copy()
            raise ConfigurationError(f"config.json corrupto: {e}")
        except Exception as e:
            logger.error(f"Error cargando configuración: {e}")
            raise ConfigurationError(f"No se pudo cargar config: {e}")

    def save(self) -> None:
        """Persiste config a archivo."""
        try:
            self.config_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.config_path, "w", encoding="utf-8") as f:
                json.dump(self._config, f, indent=2, ensure_ascii=False)
            logger.debug(f"Configuración guardada en: {self.config_path}")
        except Exception as e:
            logger.error(f"Error guardando configuración: {e}")
            raise ConfigurationError(f"No se pudo guardar config: {e}")

    def get(self, key: str, default: Any = None) -> Any:
        """Obtiene valor de config."""
        return self._config.get(key, default)

    def set(self, key: str, value: Any) -> None:
        """Establece y persiste valor de config."""
        self._config[key] = value
        self.save()

    def update(self, updates: Dict[str, Any]) -> None:
        """Actualiza múltiples valores y persiste."""
        self._config.update(updates)
        self.save()

    def reset_to_defaults(self) -> None:
        """Resetea config a defaults."""
        self._config = self.DEFAULT_CONFIG.copy()
        self.save()
        logger.info("Configuración reseteada a defaults")

    def get_all(self) -> Dict[str, Any]:
        """Retorna copia de toda la config."""
        return self._config.copy()

    def validate_dest_folder(self, path: str) -> bool:
        """Valida que la carpeta destino sea accesible."""
        try:
            p = Path(path)
            p.mkdir(parents=True, exist_ok=True)
            return p.is_dir() and os.access(p, os.W_OK)
        except Exception as e:
            logger.error(f"Carpeta destino no válida {path}: {e}")
            return False

    def validate_oauth_token(self, token: str) -> bool:
        """Valida formato básico de OAuth token."""
        if not token:
            return False
        # Formato: "OAuth 2-XXXXXXX"
        return token.startswith("OAuth 2-") and len(token) > 20

    def validate(self) -> bool:
        """Valida toda la config."""
        issues = []

        # Validar carpeta destino
        if not self.validate_dest_folder(self.get("dest_folder")):
            issues.append("dest_folder no es accesible")

        # Validar workers
        workers = self.get("max_workers")
        if not isinstance(workers, int) or workers < 1 or workers > 16:
            issues.append("max_workers debe estar entre 1 y 16")

        # Validar delay
        delay = self.get("delay")
        if not isinstance(delay, (int, float)) or delay < 0 or delay > 5:
            issues.append("delay debe estar entre 0 y 5")

        # Validar preset
        valid_presets = ["mp3_128", "mp3_256", "mp3_320", "flac"]
        if self.get("quality_preset") not in valid_presets:
            issues.append(f"quality_preset inválido: {valid_presets}")

        if issues:
            logger.warning(f"Config inválida: {', '.join(issues)}")
            return False

        logger.info("✓ Configuración validada correctamente")
        return True
