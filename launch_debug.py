#!/usr/bin/env python3
"""
Launch app with debug enabled - UTF-8 compatible version.
"""
import sys
import io

# Force UTF-8 output
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

# Add debug to path
import os
sys.path.insert(0, os.path.dirname(__file__))

# Import and activate debug
import debug_download
debug_download.patch_download_manager()

print("[DEBUG] Debug activado. Iniciando app...")
print("[DEBUG] Verifica debug_download.log para detalles de descarga.")

if __name__ == '__main__':
    from main import main
    main()
