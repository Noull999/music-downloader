#!/usr/bin/env python3
"""
Test: Verificar que la selección de carpeta de destino funciona correctamente.
"""
import os
import sys
import tempfile
from pathlib import Path

# Agregar root al path
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from gui.ui_controller import UIController

def test_dest_folder():
    """Prueba que la carpeta de destino se guarde y recupere correctamente."""
    print("🧪 Test: Selección de carpeta de destino")
    print("-" * 50)

    # Crear carpeta temporal para test
    with tempfile.TemporaryDirectory() as tmpdir:
        config_path = os.path.join(tmpdir, "test_config.json")
        base_dir = tmpdir

        # 1. Inicializar UIController
        print("✓ Inicializando UIController...")
        controller = UIController(base_dir=base_dir)

        # 2. Obtener carpeta por defecto
        default_folder = controller.get_config_value("dest_folder")
        print(f"  Default: {default_folder}")

        # 3. Establecer nueva carpeta
        new_folder = os.path.join(tmpdir, "descargas")
        print(f"\n✓ Estableciendo nueva carpeta: {new_folder}")
        controller.set_config_value("dest_folder", new_folder)

        # 4. Verificar que se guardó en config
        retrieved = controller.get_config_value("dest_folder")
        print(f"  Recuperada: {retrieved}")
        assert retrieved == new_folder, f"❌ No coincide: {retrieved} != {new_folder}"
        print("  ✓ Se guardó correctamente en memoria")

        # 5. Crear nueva instancia para verificar persistencia
        print("\n✓ Creando nueva instancia para verificar persistencia...")
        controller2 = UIController(base_dir=base_dir)
        retrieved2 = controller2.get_config_value("dest_folder")
        print(f"  Recuperada (nueva instancia): {retrieved2}")
        assert retrieved2 == new_folder, f"❌ No persistió: {retrieved2} != {new_folder}"
        print("  ✓ Se persistió correctamente en config.json")

        # 6. Verificar que el archivo config.json existe
        config_file = os.path.join(base_dir, "config.json")
        assert os.path.exists(config_file), f"❌ config.json no existe en {config_file}"
        print(f"\n✓ config.json existe: {config_file}")

        # 7. Leer config.json y verificar contenido
        import json
        with open(config_file, "r") as f:
            config_json = json.load(f)
        print(f"  dest_folder en JSON: {config_json.get('dest_folder')}")
        assert config_json.get("dest_folder") == new_folder, "❌ No está en JSON"
        print("  ✓ Correctamente guardado en JSON")

        # 8. Validar carpeta destino
        print(f"\n✓ Validando carpeta destino...")
        is_valid = controller2.config.validate_dest_folder(new_folder)
        print(f"  Es válida: {is_valid}")
        assert is_valid, f"❌ Carpeta no es válida: {new_folder}"
        print("  ✓ Carpeta validada correctamente")

    print("\n" + "=" * 50)
    print("✅ Todos los tests pasaron!")
    print("=" * 50)

if __name__ == "__main__":
    try:
        test_dest_folder()
    except AssertionError as e:
        print(f"\n❌ Test falló: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Error inesperado: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
