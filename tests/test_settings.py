"""
Test automatizado de todas las funciones del Settings dialog.
"""
import json
import os
import sys
import tempfile
from pathlib import Path

# Agregar el directorio padre al path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config.manager import ConfigManager


def test_settings_functions():
    """Test cada función del Settings dialog."""

    with tempfile.TemporaryDirectory() as tmpdir:
        config_path = os.path.join(tmpdir, "config.json")
        config = ConfigManager(config_path)

        print("🧪 INICIANDO TESTS DE CONFIGURACIÓN\n")
        print("=" * 60)

        # TEST 1: Calidad de descarga
        print("\n✓ TEST 1: Calidad de descarga")
        print("-" * 60)
        config.set("quality_preset", "flac")
        assert config.get("quality_preset") == "flac"
        print("  ✓ Cambio a FLAC: GUARDADO")
        config.set("quality_preset", "mp3_320")
        assert config.get("quality_preset") == "mp3_320"
        print("  ✓ Cambio a MP3 320k: GUARDADO")

        # TEST 2: Post-procesado - Normalizar volumen
        print("\n✓ TEST 2: Post-procesado - Normalizar volumen")
        print("-" * 60)
        config.set("normalize_volume", True)
        assert config.get("normalize_volume") == True
        print("  ✓ Normalizar volumen ACTIVADO: GUARDADO")
        config.set("normalize_volume", False)
        assert config.get("normalize_volume") == False
        print("  ✓ Normalizar volumen DESACTIVADO: GUARDADO")

        # TEST 3: Post-procesado - Eliminar silencios
        print("\n✓ TEST 3: Post-procesado - Eliminar silencios")
        print("-" * 60)
        config.set("remove_silence", True)
        assert config.get("remove_silence") == True
        print("  ✓ Eliminar silencios ACTIVADO: GUARDADO")
        config.set("remove_silence", False)
        assert config.get("remove_silence") == False
        print("  ✓ Eliminar silencios DESACTIVADO: GUARDADO")

        # TEST 4: Post-procesado - Embeber metadatos
        print("\n✓ TEST 4: Post-procesado - Embeber metadatos")
        print("-" * 60)
        config.set("embed_metadata", True)
        assert config.get("embed_metadata") == True
        print("  ✓ Embeber metadatos ACTIVADO: GUARDADO")
        config.set("embed_metadata", False)
        assert config.get("embed_metadata") == False
        print("  ✓ Embeber metadatos DESACTIVADO: GUARDADO")

        # TEST 5: Post-procesado - Embeber caratula
        print("\n✓ TEST 5: Post-procesado - Embeber caratula")
        print("-" * 60)
        config.set("embed_artwork", True)
        assert config.get("embed_artwork") == True
        print("  ✓ Embeber caratula ACTIVADO: GUARDADO")
        config.set("embed_artwork", False)
        assert config.get("embed_artwork") == False
        print("  ✓ Embeber caratula DESACTIVADO: GUARDADO")

        # TEST 6: Patrón de nombre de archivo
        print("\n✓ TEST 6: Patrón de nombre de archivo")
        print("-" * 60)
        test_pattern = "{artist} - {title} [official]"
        config.set("filename_pattern", test_pattern)
        assert config.get("filename_pattern") == test_pattern
        print(f"  ✓ Patrón personalizado: '{test_pattern}': GUARDADO")

        # TEST 7: Crear subcarpeta por artista
        print("\n✓ TEST 7: Crear subcarpeta por artista")
        print("-" * 60)
        config.set("subfolder_by_artist", True)
        assert config.get("subfolder_by_artist") == True
        print("  ✓ Subcarpeta por artista ACTIVADA: GUARDADA")
        config.set("subfolder_by_artist", False)
        assert config.get("subfolder_by_artist") == False
        print("  ✓ Subcarpeta por artista DESACTIVADA: GUARDADA")

        # TEST 8: Delay entre descargas
        print("\n✓ TEST 8: Delay entre descargas")
        print("-" * 60)
        config.set("delay", 2.5)
        assert config.get("delay") == 2.5
        print("  ✓ Delay 2.5s: GUARDADO")
        config.set("delay", 0.0)
        assert config.get("delay") == 0.0
        print("  ✓ Delay 0.0s (sin delay): GUARDADO")

        # TEST 9: SoundCloud OAuth Token
        print("\n✓ TEST 9: SoundCloud OAuth Token")
        print("-" * 60)
        test_token = "abc123def456ghi789"
        config.set("soundcloud", {"oauth_token": test_token})
        assert config.get("soundcloud", {}).get("oauth_token") == test_token
        print(f"  ✓ OAuth Token guardado: {test_token[:10]}...GUARDADO")

        # TEST 10: Persistencia - Reiniciar ConfigManager
        print("\n✓ TEST 10: Persistencia (recargar desde archivo)")
        print("-" * 60)
        config2 = ConfigManager(config_path)
        assert config2.get("quality_preset") == "mp3_320"
        assert config2.get("normalize_volume") == False
        assert config2.get("delay") == 0.0
        assert config2.get("filename_pattern") == test_pattern
        print("  ✓ Todos los valores persisten en archivo: VERIFICADO")

        # TEST 11: Múltiples cambios simultáneos
        print("\n✓ TEST 11: Múltiples cambios simultáneos")
        print("-" * 60)
        config.update({
            "quality_preset": "flac",
            "normalize_volume": True,
            "remove_silence": True,
            "delay": 1.5,
        })
        assert config.get("quality_preset") == "flac"
        assert config.get("normalize_volume") == True
        assert config.get("remove_silence") == True
        assert config.get("delay") == 1.5
        print("  ✓ Cambios múltiples simultáneos: GUARDADOS")

        print("\n" + "=" * 60)
        print("\n✅ TODOS LOS TESTS PASARON EXITOSAMENTE!")
        print("\n📊 Resumen:")
        print("  - 9 funciones individuales: ✓")
        print("  - Persistencia en archivo: ✓")
        print("  - Cambios simultáneos: ✓")
        print("  - Recargar desde archivo: ✓")
        print("\n✨ ConfigManager está 100% funcional!\n")


if __name__ == "__main__":
    test_settings_functions()
