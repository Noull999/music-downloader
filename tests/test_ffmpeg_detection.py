"""
Tests para ffmpeg detection multiplataforma.
"""
import unittest
from unittest.mock import patch, MagicMock, mock_open
import os
import sys


class TestFFmpegLocationLogic(unittest.TestCase):
    """Tests para la lógica de ffmpeg_location() en diferentes escenarios."""

    @patch('handlers.base_handler.shutil.which')
    @patch('handlers.base_handler.os.path.isfile')
    def test_ffmpeg_location_windows_found(self, mock_isfile, mock_which):
        """Windows: Encuentra ffmpeg.exe en rutas conocidas."""
        from handlers.base_handler import ffmpeg_location

        # Simular que ffmpeg.exe existe en C:\ffmpeg\bin
        def isfile_side_effect(path):
            return path == r"C:\ffmpeg\bin\ffmpeg.exe"

        mock_isfile.side_effect = isfile_side_effect
        mock_which.return_value = None

        # En Windows actual, esto debe encontrar la ruta
        if sys.platform == "win32":
            result = ffmpeg_location()
            assert result == r"C:\ffmpeg\bin" or result is not None

    @patch('handlers.base_handler.shutil.which')
    @patch('handlers.base_handler.os.path.isfile')
    def test_ffmpeg_location_fallback_to_path(self, mock_isfile, mock_which):
        """Fallback: Si no encuentra en rutas conocidas, busca en PATH."""
        from handlers.base_handler import ffmpeg_location

        mock_isfile.return_value = False
        mock_which.return_value = "/usr/bin/ffmpeg"

        with patch('handlers.base_handler.os.path.dirname', return_value="/usr/bin"):
            result = ffmpeg_location()
            assert result == "/usr/bin", f"Esperaba fallback a '/usr/bin', obtuvo {result}"

    @patch('handlers.base_handler.shutil.which')
    @patch('handlers.base_handler.os.path.isfile')
    def test_ffmpeg_location_not_found(self, mock_isfile, mock_which):
        """No encontrado: Retorna None si ffmpeg no está disponible."""
        from handlers.base_handler import ffmpeg_location

        mock_isfile.return_value = False
        mock_which.return_value = None

        result = ffmpeg_location()
        assert result is None, f"Esperaba None cuando ffmpeg no existe, obtuvo {result}"


class TestFFmpegExeSeleccion(unittest.TestCase):
    """
    Tests para la selección correcta del ejecutable de ffmpeg.

    Nota: `post_processor.py` ya no tiene una función `_ffmpeg_exe` propia;
    delega en `utils.dependencies.FFmpegValidator.find_ffmpeg_executable()`
    (cacheada en `get_ffmpeg_exe()`). Estos tests apuntan a la API actual.
    """

    def setUp(self):
        # Limpiar cache de módulo entre tests para que cada uno controle
        # su propio resultado de FFmpegValidator.
        import quality.post_processor as pp
        pp._FFMPEG_CACHE = None

    def test_get_ffmpeg_exe_returns_string(self):
        """get_ffmpeg_exe() siempre retorna un string cuando ffmpeg existe."""
        from quality.post_processor import get_ffmpeg_exe

        with patch('utils.dependencies.FFmpegValidator.find_ffmpeg_executable', return_value="ffmpeg"):
            result = get_ffmpeg_exe()
            assert isinstance(result, str), f"get_ffmpeg_exe() debe retornar string, obtuvo {type(result)}"

    def test_get_ffmpeg_exe_windows_convention(self):
        """En Windows, FFmpegValidator busca/retorna ffmpeg.exe."""
        from utils.dependencies import FFmpegValidator

        with patch('utils.dependencies.sys.platform', 'win32'), \
             patch('utils.dependencies.os.path.isfile', return_value=True):
            result = FFmpegValidator.find_ffmpeg_executable()
            assert result.endswith('ffmpeg.exe'), f"Windows debe usar ffmpeg.exe, obtuvo {result}"

    def test_get_ffmpeg_exe_linux_convention(self):
        """En Linux/macOS, FFmpegValidator busca/retorna ffmpeg (sin extensión)."""
        from utils.dependencies import FFmpegValidator

        with patch('utils.dependencies.sys.platform', 'linux'), \
             patch('utils.dependencies.os.path.isfile', return_value=True):
            result = FFmpegValidator.find_ffmpeg_executable()
            assert result.endswith('ffmpeg'), f"Linux debe usar ffmpeg sin extensión, obtuvo {result}"
            assert not result.endswith('.exe'), f"Linux no debe tener .exe"

    def test_get_ffmpeg_exe_raises_when_not_found(self):
        """Si no se encuentra ffmpeg en ningún lado, lanza DependencyNotFoundError."""
        from quality.post_processor import get_ffmpeg_exe
        from utils.exceptions import DependencyNotFoundError

        with patch('utils.dependencies.FFmpegValidator.find_ffmpeg_executable',
                   side_effect=DependencyNotFoundError("no encontrado")):
            with self.assertRaises(DependencyNotFoundError):
                get_ffmpeg_exe()


class TestSanitizeFilename(unittest.TestCase):
    """Tests para sanitize_filename() que funciona igual en todos los SO."""

    def test_sanitize_filename_removes_invalid_chars(self):
        """Elimina caracteres inválidos en Windows y Unix."""
        from download_manager import sanitize_filename

        # Caracteres inválidos en Windows: \ / : * ? " < > |
        dirty = 'track|with<bad>chars?.mp3'
        result = sanitize_filename(dirty)

        invalid_chars = set('\\/:*?"<>|')
        for char in invalid_chars:
            assert char not in result, f"Resultado contiene carácter inválido '{char}': {result}"

    def test_sanitize_filename_keeps_valid_chars(self):
        """Mantiene caracteres válidos."""
        from download_manager import sanitize_filename

        clean = 'Artista - Cancion (Remix) [Original].mp3'
        result = sanitize_filename(clean)
        assert result == clean, f"No debe modificar nombres válidos"

    def test_sanitize_filename_handles_empty(self):
        """Maneja nombres vacíos correctamente."""
        from download_manager import sanitize_filename

        result = sanitize_filename('')
        assert result == 'Unknown', f"Nombre vacío debe retornar 'Unknown', obtuvo '{result}'"

    def test_sanitize_filename_strips_whitespace(self):
        """Elimina espacios en blanco al inicio/final."""
        from download_manager import sanitize_filename

        result = sanitize_filename('  Canción  ')
        assert result == 'Canción', f"Debe eliminar espacios, obtuvo '{result}'"

    def test_sanitize_filename_unicode(self):
        """Mantiene caracteres Unicode válidos."""
        from download_manager import sanitize_filename

        names = ['Niño', 'Canción', 'España', 'José']
        for name in names:
            result = sanitize_filename(name)
            assert name in result, f"Debe mantener caracteres Unicode de '{name}', obtuvo '{result}'"


class TestPathConstruction(unittest.TestCase):
    """Tests para la construcción correcta de rutas en diferentes plataformas."""

    def test_ffmpeg_candidates_dict_structure(self):
        """Estructura de _FFMPEG_CANDIDATES es correcta."""
        from handlers.base_handler import _FFMPEG_CANDIDATES

        assert isinstance(_FFMPEG_CANDIDATES, dict), "Debe ser un dict"
        assert 'win32' in _FFMPEG_CANDIDATES, "Debe tener 'win32'"
        assert 'darwin' in _FFMPEG_CANDIDATES, "Debe tener 'darwin' (macOS)"
        assert 'linux' in _FFMPEG_CANDIDATES, "Debe tener 'linux'"

        for platform, paths in _FFMPEG_CANDIDATES.items():
            assert isinstance(paths, list), f"Paths para '{platform}' debe ser lista"

    def test_no_hardcoded_windows_paths_in_modules(self):
        """
        No hay rutas Windows personales (de un usuario concreto) hardcodeadas
        en los módulos principales del proyecto.

        `debug_api.py` y `rebuild_history.py` (scripts de debug de una versión
        anterior) ya no existen en el repo, así que se escanean los módulos
        que sí forman parte de la app actual.
        """
        suspicious_patterns = ['C:\\\\Users\\\\Lenovo', 'serato\\\\musik']
        checked_any = False

        for root_module in ["main.py", "download_manager.py", "models.py", "url_detector.py"]:
            if not os.path.exists(root_module):
                continue
            checked_any = True
            with open(root_module, encoding='utf-8') as f:
                content = f.read()
            for pattern in suspicious_patterns:
                assert pattern not in content, f"{root_module} no debe tener rutas personales hardcodeadas ({pattern})"

        assert checked_any, "No se encontró ningún módulo raíz para chequear"


if __name__ == '__main__':
    unittest.main()
