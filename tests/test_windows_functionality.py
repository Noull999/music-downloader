"""
Tests de funcionamiento específicos para Windows (plataforma principal
del usuario). Corren en cualquier SO via mocks de `sys.platform`,
`shutil.which` y `os.path.isfile` — no requieren estar en Windows real
ni tener ffmpeg/fpcalc/beet instalados.

Cubre: detección de ffmpeg, sanitización de nombres (chars inválidos +
nombres reservados de dispositivo), dispatch de codec/tags mp3 vs flac
con rutas estilo Windows, resolución de `beet`/`fpcalc` vía PATHEXT, y
que la config por defecto resuelve rutas de usuario en Windows.
"""
import os
import sys
import unittest
from unittest.mock import patch, MagicMock


# ────────────────────────────────────────────────────────────────────── #
# sanitize_filename: caracteres inválidos + nombres reservados de Windows #
# ────────────────────────────────────────────────────────────────────── #

class TestSanitizeFilenameWindows(unittest.TestCase):
    """
    Windows prohíbe: los caracteres \\/:*?"<>|, espacios/puntos finales,
    y ciertos nombres de dispositivo reservados (CON, PRN, AUX, NUL,
    COM1-9, LPT1-9) como nombre de archivo O carpeta, con o sin extensión,
    sin importar mayúsculas/minúsculas.
    """

    def test_reserved_device_names_are_escaped(self):
        from download_manager import sanitize_filename

        for reserved in ["CON", "con", "PRN", "AUX", "NUL", "COM1", "com3", "LPT1", "lpt9"]:
            result = sanitize_filename(reserved)
            self.assertNotEqual(result.upper(), reserved.upper(),
                                 f"'{reserved}' debe escaparse, Windows lo rechaza tal cual")

    def test_reserved_device_name_with_extension_is_escaped(self):
        """'con.mp3' es tan inválido en Windows como 'con' a secas."""
        from download_manager import sanitize_filename

        result = sanitize_filename("con.mp3")
        stem = result.split(".", 1)[0]
        self.assertNotEqual(stem.upper(), "CON", f"'con.mp3' debe escaparse, obtuvo '{result}'")

    def test_normal_artist_names_containing_reserved_substring_untouched(self):
        """
        Un artista real que solo CONTIENE 'con' (ej. 'Conan') no debe
        escaparse — solo el nombre completo coincidente es el problema.
        """
        from download_manager import sanitize_filename

        result = sanitize_filename("Conan")
        self.assertEqual(result, "Conan")

    def test_invalid_windows_chars_replaced(self):
        from download_manager import sanitize_filename

        dirty = 'AC/DC: Back In Black? "Live"*<test>|.mp3'
        result = sanitize_filename(dirty)
        for char in '\\/:*?"<>|':
            self.assertNotIn(char, result)

    def test_trailing_dots_and_spaces_stripped(self):
        """Windows ignora/rechaza espacios y puntos al final del nombre."""
        from download_manager import sanitize_filename

        result = sanitize_filename("Track Name. . .   ")
        self.assertFalse(result.endswith(" "))
        self.assertFalse(result.endswith("."))


# ────────────────────────────────────────────────────────────────────── #
# FFmpegValidator: deteccion de ffmpeg.exe en rutas conocidas de Windows  #
# ────────────────────────────────────────────────────────────────────── #

class TestFFmpegValidatorWindows(unittest.TestCase):

    def test_finds_ffmpeg_exe_in_known_windows_paths(self):
        from utils.dependencies import FFmpegValidator, _FFMPEG_CANDIDATES

        expected = os.path.join(r"C:\ffmpeg\bin", "ffmpeg.exe")

        def isfile_side_effect(path):
            return path == expected

        with patch('utils.dependencies.sys.platform', 'win32'), \
             patch('utils.dependencies.os.path.isfile', side_effect=isfile_side_effect), \
             patch('utils.dependencies.shutil.which', return_value=None):
            result = FFmpegValidator.find_ffmpeg_executable()
            self.assertEqual(result, expected)

    def test_falls_back_to_system_path_on_windows(self):
        from utils.dependencies import FFmpegValidator

        with patch('utils.dependencies.sys.platform', 'win32'), \
             patch('utils.dependencies.os.path.isfile', return_value=False), \
             patch('utils.dependencies.shutil.which', return_value=r"C:\Users\Test\scoop\shims\ffmpeg.exe"):
            result = FFmpegValidator.find_ffmpeg_executable()
            self.assertTrue(result.endswith("ffmpeg.exe"))

    def test_raises_clear_error_when_not_found_on_windows(self):
        from utils.dependencies import FFmpegValidator
        from utils.exceptions import DependencyNotFoundError

        with patch('utils.dependencies.sys.platform', 'win32'), \
             patch('utils.dependencies.os.path.isfile', return_value=False), \
             patch('utils.dependencies.shutil.which', return_value=None):
            with self.assertRaises(DependencyNotFoundError) as ctx:
                FFmpegValidator.find_ffmpeg_executable()
            self.assertIn("Windows", str(ctx.exception))

    def test_pyinstaller_bundle_path_used_first_on_windows(self):
        """El .exe empaquetado (PyInstaller) trae su propio ffmpeg embebido."""
        from utils.dependencies import FFmpegValidator

        fake_meipass = r"C:\Users\Test\AppData\Local\Temp\_MEI12345"
        expected = os.path.join(fake_meipass, "ffmpeg", "ffmpeg.exe")

        def isfile_side_effect(path):
            return path == expected

        with patch('utils.dependencies.sys.platform', 'win32'), \
             patch.object(sys, '_MEIPASS', fake_meipass, create=True), \
             patch('utils.dependencies.os.path.isfile', side_effect=isfile_side_effect):
            result = FFmpegValidator.find_ffmpeg_executable()
            self.assertEqual(result, expected)


# ────────────────────────────────────────────────────────────────────── #
# post_processor: dispatch de codec/tags con rutas estilo Windows        #
# ────────────────────────────────────────────────────────────────────── #

class TestPostProcessorWindowsPaths(unittest.TestCase):
    """
    Verifica que el fix del bug FLAC (antes hardcodeado a .mp3) funciona
    igual con rutas absolutas de Windows (backslash + letra de unidad),
    ya que `os.path.splitext` opera sobre el string, no sobre el SO real.
    """

    def test_codec_args_dispatch_mp3_windows_path(self):
        from quality.post_processor import _FFMPEG_CODEC_ARGS

        win_path = r"C:\Users\Test\Music\Artist - Track.mp3"
        ext = os.path.splitext(win_path)[1].lower()
        self.assertEqual(ext, ".mp3")
        self.assertIn(ext, _FFMPEG_CODEC_ARGS)
        self.assertIn("libmp3lame", _FFMPEG_CODEC_ARGS[ext])

    def test_codec_args_dispatch_flac_windows_path(self):
        """
        Antes de la fix, CUALQUIER extensión terminaba reencodeada a
        libmp3lame+320k. Este test fija el comportamiento correcto: un
        .flac debe usar el codec flac, no mp3, incluso en ruta Windows.
        """
        from quality.post_processor import _FFMPEG_CODEC_ARGS

        win_path = r"C:\Users\Test\Music\Artist - Track.flac"
        ext = os.path.splitext(win_path)[1].lower()
        self.assertEqual(ext, ".flac")
        self.assertIn(ext, _FFMPEG_CODEC_ARGS)
        self.assertNotIn("libmp3lame", _FFMPEG_CODEC_ARGS[ext])

    def test_process_skips_missing_file_gracefully(self):
        """Con ruta Windows inexistente no debe lanzar, solo devolverla tal cual."""
        from quality.post_processor import PostProcessor

        pp = PostProcessor({"embed_metadata": True})
        missing = r"C:\Users\Test\Music\no_existe.mp3"
        result = pp.process(missing, {"title": "x", "artist": "y"})
        self.assertEqual(result, missing)

    def test_apply_ffmpeg_filters_temp_file_matches_extension(self):
        """
        El archivo temporal de ffmpeg debe conservar la extensión real
        (".pp_temp.flac", no ".pp_temp.mp3") — si no, ffmpeg escribiría
        un flac con extensión mp3 y viceversa.
        """
        from quality.post_processor import PostProcessor

        pp = PostProcessor({"normalize_volume": True})
        with patch('quality.post_processor.get_ffmpeg_exe', return_value=r"C:\ffmpeg\bin\ffmpeg.exe"), \
             patch('quality.post_processor.subprocess.run') as mock_run, \
             patch('quality.post_processor.os.path.exists', return_value=True), \
             patch('quality.post_processor.os.replace') as mock_replace:
            mock_run.return_value = MagicMock(returncode=0)

            input_file = r"C:\Users\Test\Music\track.flac"
            pp._apply_ffmpeg_filters(input_file, ".flac")

            cmd = mock_run.call_args[0][0]
            temp_file = cmd[-1]  # último argumento del comando ffmpeg
            self.assertTrue(temp_file.endswith(".pp_temp.flac"),
                             f"Temp file debe terminar en .pp_temp.flac, fue: {temp_file}")
            self.assertIn("flac", cmd, "El comando ffmpeg debe pedir codec flac, no mp3")


# ────────────────────────────────────────────────────────────────────── #
# Resolución de binarios opcionales (beet.exe / fpcalc.exe) vía PATHEXT  #
# ────────────────────────────────────────────────────────────────────── #

class TestOptionalBinariesWindowsResolution(unittest.TestCase):
    """
    En Windows, `shutil.which("beet")` resuelve automáticamente a
    beet.exe/beet.bat/beet.cmd usando %PATHEXT% — nuestro código llama
    which() con el nombre sin extensión a propósito, dejando que Windows
    resuelva. Estos tests confirman que el resultado (con extensión) se
    usa tal cual en el subprocess, sin recortarlo ni romperlo.
    """

    def test_beets_organize_uses_resolved_windows_path(self):
        from quality.post_processor import PostProcessor

        pp = PostProcessor({"organize_with_beets": True})
        resolved = r"C:\Users\Test\scoop\shims\beet.exe"

        with patch('quality.post_processor.shutil.which', return_value=resolved), \
             patch('quality.post_processor.subprocess.run') as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stderr="")
            file_path = r"C:\Users\Test\Music\track.mp3"

            result = pp._organize_with_beets(file_path)

            cmd = mock_run.call_args[0][0]
            self.assertEqual(cmd[0], resolved)
            self.assertIn(file_path, cmd)
            self.assertEqual(result, file_path)

    def test_beets_organize_noop_when_beet_not_on_path(self):
        """Sin 'beet' en PATH (caso más común), no debe lanzar ni bloquear."""
        from quality.post_processor import PostProcessor

        pp = PostProcessor({"organize_with_beets": True})
        with patch('quality.post_processor.shutil.which', return_value=None), \
             patch('quality.post_processor.subprocess.run') as mock_run:
            file_path = r"C:\Users\Test\Music\track.mp3"
            result = pp._organize_with_beets(file_path)

            mock_run.assert_not_called()
            self.assertEqual(result, file_path)

    def test_audio_fingerprint_unavailable_without_fpcalc_exe(self):
        from utils.audio_fingerprint import is_available

        fake_acoustid = MagicMock()
        fake_acoustid.have_chromaprint = True
        with patch.dict('sys.modules', {'acoustid': fake_acoustid}), \
             patch('shutil.which', return_value=None):
            self.assertFalse(is_available())

    def test_audio_fingerprint_available_when_fpcalc_exe_resolved(self):
        from utils.audio_fingerprint import is_available

        fake_acoustid = MagicMock()
        fake_acoustid.have_chromaprint = True
        with patch.dict('sys.modules', {'acoustid': fake_acoustid}), \
             patch('shutil.which', return_value=r"C:\ProgramData\chocolatey\bin\fpcalc.exe"):
            self.assertTrue(is_available())


# ────────────────────────────────────────────────────────────────────── #
# Config: rutas por defecto resuelven correctamente en Windows           #
# ────────────────────────────────────────────────────────────────────── #

class TestConfigWindowsPaths(unittest.TestCase):

    def test_default_dest_folder_resolves_under_windows_home(self):
        """
        `os.path.expanduser("~/Music")` debe resolver bajo el HOME/USERPROFILE
        del usuario, sin dejar el símbolo '~' literal en la ruta — algo que
        rompería `os.makedirs`/`Path.mkdir` en Windows.
        """
        import importlib
        import config.manager as manager

        fake_home = r"C:\Users\Test"
        with patch.dict(os.environ, {"USERPROFILE": fake_home, "HOME": fake_home}):
            importlib.reload(manager)
            dest = manager.ConfigManager.DEFAULT_CONFIG["dest_folder"]
            self.assertNotIn("~", dest)

        importlib.reload(manager)  # restaurar estado normal para otros tests

    def test_new_windows_related_defaults_present(self):
        """Los flags nuevos (letras/beets) tienen default seguro (False)."""
        from config.manager import ConfigManager

        self.assertIn("embed_lyrics", ConfigManager.DEFAULT_CONFIG)
        self.assertIn("organize_with_beets", ConfigManager.DEFAULT_CONFIG)
        self.assertFalse(ConfigManager.DEFAULT_CONFIG["embed_lyrics"])
        self.assertFalse(ConfigManager.DEFAULT_CONFIG["organize_with_beets"])


if __name__ == '__main__':
    unittest.main()
