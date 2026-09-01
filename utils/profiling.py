"""
Decorador @timeit para profiling de funciones clave.
Mide tiempo de ejecución y registra en log.
Uso: @timeit("nombre descriptivo")
"""
import functools
import logging
import time
from typing import Callable, TypeVar, Any

logger = logging.getLogger(__name__)

F = TypeVar("F", bound=Callable[..., Any])


def timeit(name: str = ""):
    """Decorador para medir tiempo de ejecución de funciones."""

    def decorator(func: F) -> F:
        func_name = name or func.__name__

        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            start = time.perf_counter()
            try:
                result = func(*args, **kwargs)
                return result
            finally:
                elapsed = time.perf_counter() - start
                if elapsed > 0.1:  # Solo log si > 100ms
                    logger.info(f"⏱️  {func_name}: {elapsed*1000:.1f}ms")

        return wrapper

    return decorator
