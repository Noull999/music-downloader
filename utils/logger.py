"""
Logger centralizado con rotación y niveles configurables.
Reemplaza basicConfig en main.py
"""
import logging
import os
from logging.handlers import RotatingFileHandler
from pathlib import Path


def setup_logging(
    log_level: str = "INFO",
    log_file: str = "music_downloader.log",
    max_bytes: int = 5_242_880,  # 5 MB
    backup_count: int = 3,
) -> logging.Logger:
    """
    Configura logging con rotación de archivos.

    Args:
        log_level: DEBUG, INFO, WARNING, ERROR (default: INFO)
        log_file: nombre del archivo de log (se guarda en proyecto root)
        max_bytes: tamaño máximo antes de rotar (default: 5 MB)
        backup_count: número de backups a mantener (default: 3)

    Returns:
        Logger raíz configurado
    """
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)

    # Crear carpeta si no existe
    log_path = Path(log_file)
    log_path.parent.mkdir(parents=True, exist_ok=True)

    # Formato
    formatter = logging.Formatter(
        fmt="%(asctime)s [%(levelname)-8s] %(name)-20s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    # 1️⃣ Handler: Consola (stdout)
    console_handler = logging.StreamHandler()
    console_handler.setLevel(log_level)
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)

    # 2️⃣ Handler: Archivo con rotación
    file_handler = RotatingFileHandler(
        filename=str(log_path),
        maxBytes=max_bytes,
        backupCount=backup_count,
        encoding="utf-8"
    )
    file_handler.setLevel(logging.DEBUG)  # Archivo siempre captura TODO
    file_handler.setFormatter(formatter)
    root_logger.addHandler(file_handler)

    # Log inicial
    root_logger.info(
        f"Logging inicializado: {log_file} (max {max_bytes//1024//1024}MB, "
        f"{backup_count} backups)"
    )

    return root_logger


def get_logger(name: str) -> logging.Logger:
    """
    Obtiene logger para un módulo.
    Ej: logger = get_logger(__name__)
    """
    return logging.getLogger(name)
