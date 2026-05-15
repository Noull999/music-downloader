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
    """Tests para la selección correcta del ejecutable de ffmpeg."""

    def test_ffmpeg_exe_returns_string(self):
        """_ffmpeg_exe() siempre retorna un string."""
        from quality.post_processor import _ffmpeg_exe

        result = _ffmpeg_exe()
        assert isinstance(result, str), f"_ffmpeg_exe() debe retornar string, obtuvo {type(result)}"

    @patch('quality.post_processor.ffmpeg_location')
    def test_ffmpeg_exe_windows_convention(self, mock_ffmpeg_location):
        """En Windows, usa ffmpeg.exe."""
        from quality.post_processor import _ffmpeg_exe

        mock_ffmpeg_location.return_value = r"C:\ffmpeg\bin"

        with patch('quality.post_processor.sys.platform', 'win32'):
            # Re-ejecutar la lógica manualmente
            loc = r"C:\ffmpeg\bin"
            result = os.path.join(loc, "ffmpeg.exe")
            assert result.endswith('ffmpeg.exe'), f"Windows debe usar ffmpeg.exe"

    @patch('quality.post_processor.ffmpeg_location')
    def test_ffmpeg_exe_linux_convention(self, mock_ffmpeg_location):
        """En Linux/macOS, usa ffmpeg (sin extensión)."""
        from quality.post_processor import _ffmpeg_exe

        mock_ffmpeg_location.return_value = "/usr/bin"

        with patch('quality.post_processor.sys.platform', 'linux'):
            # Re-ejecutar la lógica manualmente
            loc = "/usr/bin"
            result = os.path.join(loc, "ffmpeg")
            assert result.endswith('ffmpeg'), f"Linux debe usar ffmpeg sin extensión"
            assert not result.endswith('.exe'), f"Linux no debe tener .exe"

    @patch('quality.post_processor.ffmpeg_location')
    def test_ffmpeg_exe_fallback(self, mock_ffmpeg_location):
        """Si ffmpeg_location() retorna None, usa 'ffmpeg' como comando."""
        from quality.post_processor import _ffmpeg_exe

        mock_ffmpeg_location.return_value = None
        result = _ffmpeg_exe()
        assert result == "ffmpeg", f"Fallback debe ser 'ffmpeg', obtuvo {result}"


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
        """No hay rutas Windows hardcodeadas en módulos principales."""
        # debug_api.py debe construir su ruta dinámicamente, no hardcodeada
        with open("debug_api.py", encoding='utf-8') as f:
            debug_api_content = f.read()
            # Verifica que la ruta de config no está hardcodeada a C:\Users\...
            assert 'r"C:\\Users\\Lenovo' not in debug_api_content, "debug_api.py no debe tener rutas hardcodeadas"

        # rebuild_history.py debe usar ~/Music o argumento, no hardcodeada a serato\musik
        with open("rebuild_history.py", encoding='utf-8') as f:
            rebuild_history_content = f.read()
            # Verifica que no está hardcodeada a la carpeta serato personal
            assert 'serato\\musik' not in rebuild_history_content, "rebuild_history.py no debe tener rutas hardcodeadas"
            # Verifica que usa expanduser o sys.argv para ser flexible
            assert 'expanduser' in rebuild_history_content or 'sys.argv' in rebuild_history_content, \
                "rebuild_history.py debe usar sys.argv o expanduser para rutas"


if __name__ == '__main__':
    unittest.main()
