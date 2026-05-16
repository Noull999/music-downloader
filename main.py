"""
Music Downloader — entry point.
Ejecutar: python main.py

1. Valida dependencias en startup
2. Configura logging
3. Inicia GUI
"""
import sys
import logging
import traceback
import customtkinter as ctk
from tkinter import messagebox

from utils.logger import setup_logging
from utils.dependencies import validate_all_dependencies
from utils.exceptions import DependencyNotFoundError
from gui.main_window import MainWindow

logger = None


def global_exception_handler(exc_type, exc_value, exc_traceback):
    """Maneja todas las excepciones no capturadas globalmente."""
    if logger:
        logger.critical(f"EXCEPCION NO CAPTURADA: {exc_type.__name__}: {exc_value}")
        logger.critical("".join(traceback.format_tb(exc_traceback)))
    else:
        print(f"EXCEPCION NO CAPTURADA: {exc_type.__name__}: {exc_value}")
        traceback.print_tb(exc_traceback)
    sys.exit(255)


def validate_startup() -> bool:
    """Valida todas las dependencias críticas antes de iniciar la app."""
    try:
        print("🔍 Validando dependencias...")
        results = validate_all_dependencies()

        # Mostrar estado
        print("\n✓ Dependencias validadas:")
        for dep, info in results.items():
            status = "✓" if info["status"] == "OK" else "⚠"
            version = f" v{info.get('version', 'N/A')}" if "version" in info else ""
            print(f"  {status} {dep}{version}")

        return True

    except DependencyNotFoundError as e:
        print(f"\n❌ ERROR DE DEPENDENCIA:\n{e}\n")
        # Mostrar dialog
        root = ctk.CTk()
        root.withdraw()
        messagebox.showerror(
            "Dependencia Faltante",
            f"No se puede iniciar Music Downloader:\n\n{e}"
        )
        root.destroy()
        return False

    except Exception as e:
        print(f"\n❌ ERROR AL VALIDAR:\n{e}\n")
        root = ctk.CTk()
        root.withdraw()
        messagebox.showerror(
            "Error de Validación",
            f"Error al validar dependencias:\n\n{e}"
        )
        root.destroy()
        return False


def main():
    """Entry point principal."""
    # 1️⃣ Validar dependencias PRIMERO
    if not validate_startup():
        sys.exit(1)

    # 2️⃣ Configurar logging
    global logger
    logger = setup_logging(log_level="INFO")
    logger.info("="*60)
    logger.info("🎵 Music Downloader iniciado")
    logger.info("="*60)

    # Instalar manejador global de excepciones
    sys.excepthook = global_exception_handler

    # 3️⃣ Inicializar GUI
    app = None
    try:
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")
        logger.info("Inicializando ventana principal...")
        app = MainWindow()
        logger.info("Ventana principal lista. Iniciando event loop...")
        app.mainloop()
        logger.info("Event loop terminó normalmente")
    except KeyboardInterrupt:
        logger.info("Interrupción por teclado")
        sys.exit(0)
    except Exception as e:
        logger.exception("Error fatal en GUI")
        try:
            root = ctk.CTk()
            root.withdraw()
            messagebox.showerror(
                "Error Fatal",
                f"Error iniciando aplicación:\n\n{e}"
            )
            root.destroy()
        except Exception:
            pass
        sys.exit(1)


if __name__ == "__main__":
    main()
