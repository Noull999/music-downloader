#!/usr/bin/env python3
"""
Wrapper para ejecutar la app con debug habilitado.
"""
import sys
import os

# Agregar debug al path
sys.path.insert(0, os.path.dirname(__file__))

# Importar y activar debug
import debug_download
debug_download.patch_download_manager()

print("🔍 Debug activado. Iniciando app...")
print("   Verifica debug_download.log para detalles de descarga.")

# Ejecutar app normal
if __name__ == '__main__':
    from main import main
    main()
