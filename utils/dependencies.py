"""
Validación robusta de dependencias externas.
Verifica ffmpeg en startup y proporciona feedback claro.
"""
import os
import sys
import shutil
import subprocess
import logging
from typing import Optional, Tuple

from utils.exceptions import DependencyNotFoundError, DependencyVersionError

logger = logging.getLogger(__name__)


# Rutas conocidas por SO
_FFMPEG_CANDIDATES = {
    "win32": [
        r"C:\ffmpeg\bin",
        r"C:\Program Files\ffmpeg\bin",
        r"C:\Program Files (x86)\ffmpeg\bin",
    ],
    "darwin": [
        "/opt/homebrew/bin",
        "/usr/local/bin",
        "/usr/local/opt/ffmpeg/bin",
    ],
    "linux": [
        "/usr/bin",
        "/usr/local/bin",
        "/snap/bin",
    ]
}

_MIN_FFMPEG_VERSION = "4.0"  # Versión mínima requerida


class FFmpegValidator:
    """Valida existencia, ubicación y versión de FFmpeg."""

    @staticmethod
    def find_ffmpeg_executable() -> str:
        """
        Busca ffmpeg en rutas conocidas + PATH del sistema.
        Retorna: ruta completa a ffmpeg ejecutable
        Lanza: DependencyNotFoundError si no encuentra
        """
        platform = sys.platform
        ffmpeg_name = "ffmpeg.exe" if platform == "win32" else "ffmpeg"

        # 1️⃣ PyInstaller bundle (_MEIPASS)
        meipass = getattr(sys, "_MEIPASS", "")
        if meipass:
            candidate = os.path.join(meipass, "ffmpeg", ffmpeg_name)
            if os.path.isfile(candidate):
                logger.info(f"FFmpeg encontrado en bundle: {candidate}")
                return candidate

        # 2️⃣ Buscar en rutas conocidas del SO
        candidates = _FFMPEG_CANDIDATES.get(platform, [])
        for path in candidates:
            candidate = os.path.join(path, ffmpeg_name)
            if os.path.isfile(candidate):
                logger.info(f"FFmpeg encontrado en: {candidate}")
                return candidate

        # 3️⃣ Buscar en PATH del sistema
        ffmpeg_path = shutil.which(ffmpeg_name)
        if ffmpeg_path:
            logger.info(f"FFmpeg encontrado en PATH: {ffmpeg_path}")
            return ffmpeg_path

        # 4️⃣ No encontrado → Error claro
        raise DependencyNotFoundError(
            f"FFmpeg no está instalado en tu sistema.\n\n"
            f"Descargas:\n"
            f"  • Windows: https://ffmpeg.org/download.html\n"
            f"  • macOS: brew install ffmpeg\n"
            f"  • Linux: sudo apt install ffmpeg\n\n"
            f"Búsqueda en:\n"
            f"  • Rutas estándar: {', '.join(candidates)}\n"
            f"  • PATH del sistema: {os.environ.get('PATH', 'No configurado')}"
        )

    @staticmethod
    def get_ffmpeg_version(ffmpeg_path: str) -> str:
        """Obtiene versión de FFmpeg. Retorna ej: '6.1'"""
        try:
            result = subprocess.run(
                [ffmpeg_path, "-version"],
                capture_output=True,
                timeout=5,
                text=True
            )

            if result.returncode != 0:
                raise DependencyVersionError(
                    f"No se puede ejecutar FFmpeg en: {ffmpeg_path}\n"
                    f"Error: {result.stderr[:200]}"
                )

            # Parsea primera línea: "ffmpeg version 6.1 Copyright..."
            first_line = result.stdout.split('\n')[0]
            parts = first_line.split()

            for i, part in enumerate(parts):
                if part == "version" and i + 1 < len(parts):
                    version = parts[i + 1]
                    logger.info(f"FFmpeg versión: {version}")
                    return version

            raise ValueError("No se pudo parsear versión")

        except subprocess.TimeoutExpired:
            raise DependencyVersionError("FFmpeg timeout al obtener versión")
        except Exception as e:
            raise DependencyVersionError(f"Error obteniendo versión FFmpeg: {e}")

    @staticmethod
    def compare_versions(version1: str, version2: str) -> int:
        """
        Compara versiones semánticas.
        Retorna: -1 si v1 < v2, 0 si v1 == v2, 1 si v1 > v2
        Ej: compare_versions("5.1", "6.0") → -1
        """
        # Builds git de ffmpeg ("N-124445-g22d06b39ce") son master, siempre
        # más nuevos que cualquier release numerada.
        if version1.startswith("N-"):
            return 1
        if version2.startswith("N-"):
            return -1

        def normalize(v):
            parts = v.split('.')
            return [int(x) for x in parts[:3]]  # Mayor.Menor.Parche

        try:
            v1 = normalize(version1)
            v2 = normalize(version2)

            # Pad con ceros
            while len(v1) < 3:
                v1.append(0)
            while len(v2) < 3:
                v2.append(0)

            if v1 < v2:
                return -1
            elif v1 > v2:
                return 1
            else:
                return 0
        except (ValueError, AttributeError):
            logger.warning(f"No se pudo comparar versiones: {version1} vs {version2}")
            return 0  # Asumir iguales si no se puede parsear

    @staticmethod
    def validate() -> Tuple[str, str]:
        """
        Validación COMPLETA de FFmpeg:
        1. Encuentra ejecutable
        2. Verifica versión ≥ 4.0
        3. Valida que funciona

        Retorna: (ffmpeg_path, version)
        Lanza: DependencyNotFoundError o DependencyVersionError
        """
        ffmpeg_path = FFmpegValidator.find_ffmpeg_executable()
        version = FFmpegValidator.get_ffmpeg_version(ffmpeg_path)

        # Verificar versión mínima
        if FFmpegValidator.compare_versions(version, _MIN_FFMPEG_VERSION) < 0:
            raise DependencyVersionError(
                f"FFmpeg versión {version} es muy vieja.\n"
                f"Versión mínima requerida: {_MIN_FFMPEG_VERSION}\n"
                f"Actualiza desde: https://ffmpeg.org/download.html"
            )

        logger.info(f"✓ FFmpeg validado: {ffmpeg_path} (v{version})")
        return ffmpeg_path, version


class YtDlpValidator:
    """Valida yt-dlp está instalado y funciona."""

    @staticmethod
    def validate() -> str:
        """
        Valida yt-dlp importando el módulo (no el CLI: dentro del .exe
        empaquetado solo existe el módulo, no el comando en PATH).
        Retorna: versión de yt-dlp
        Lanza: DependencyNotFoundError
        """
        try:
            import yt_dlp
            version = yt_dlp.version.__version__
            logger.info(f"✓ yt-dlp validado: {version}")
            return version
        except ImportError:
            raise DependencyNotFoundError(
                "yt-dlp no está instalado.\n"
                "Instala: pip install yt-dlp"
            )
        except Exception as e:
            raise DependencyNotFoundError(f"Error validando yt-dlp: {e}")


class MutagenValidator:
    """Valida mutagen para embedding de tags."""

    @staticmethod
    def validate() -> bool:
        """
        Verifica mutagen disponible.
        Retorna: True si disponible
        Lanza: DependencyNotFoundError si falta
        """
        try:
            import mutagen
            # mutagen >= 1.47 ya no expone __version__; usar metadata del paquete
            try:
                from importlib.metadata import version as _pkg_version
                mutagen_version = _pkg_version("mutagen")
            except Exception:
                mutagen_version = getattr(mutagen, "__version__", "desconocida")
            logger.info(f"✓ mutagen validado: {mutagen_version}")
            return True
        except ImportError:
            raise DependencyNotFoundError(
                "mutagen no está instalado.\n"
                "Para embedding de tags, instala: pip install mutagen"
            )


def validate_all_dependencies() -> dict:
    """
    Valida TODAS las dependencias necesarias.
    Retorna: dict con estado de cada dependencia
    Lanza: Exception si hay dependencia crítica faltante
    """
    results = {}

    # FFmpeg (CRÍTICO)
    try:
        ffmpeg_path, ffmpeg_version = FFmpegValidator.validate()
        results["ffmpeg"] = {
            "status": "OK",
            "version": ffmpeg_version,
            "path": ffmpeg_path,
            "critical": True
        }
    except Exception as e:
        results["ffmpeg"] = {
            "status": "ERROR",
            "error": str(e),
            "critical": True
        }
        logger.error(f"FFmpeg validation failed: {e}")

    # yt-dlp (CRÍTICO)
    try:
        yt_dlp_version = YtDlpValidator.validate()
        results["yt-dlp"] = {
            "status": "OK",
            "version": yt_dlp_version,
            "critical": True
        }
    except Exception as e:
        results["yt-dlp"] = {
            "status": "ERROR",
            "error": str(e),
            "critical": True
        }
        logger.error(f"yt-dlp validation failed: {e}")

    # mutagen (OPCIONAL - para tags)
    try:
        MutagenValidator.validate()
        results["mutagen"] = {
            "status": "OK",
            "critical": False
        }
    except Exception as e:
        results["mutagen"] = {
            "status": "WARNING",
            "error": str(e),
            "critical": False
        }
        logger.warning(f"mutagen not available: {e}")

    # Verificar dependencias críticas
    critical_failures = [
        k for k, v in results.items()
        if v.get("critical") and v.get("status") == "ERROR"
    ]

    if critical_failures:
        error_msg = "Dependencias críticas faltantes:\n\n"
        for dep in critical_failures:
            error_msg += f"❌ {dep}: {results[dep]['error']}\n\n"
        raise DependencyNotFoundError(error_msg)

    logger.info(f"✓ Todas las dependencias validadas: {results}")
    return results
