"""
Helpers para layouts responsivos en CustomTkinter.
Permite que la UI se adapte a diferentes tamaños de pantalla.
"""
import customtkinter as ctk
from typing import Tuple


class ResponsiveLayout:
    """Utilidades para diseños responsivos."""

    @staticmethod
    def calculate_sidebar_width(window_width: int) -> int:
        """
        Calcula ancho dinámico del sidebar.
        - Pantallas < 1000px: 250px
        - Pantallas 1000-1500px: 300px
        - Pantallas > 1500px: 350px
        """
        if window_width < 1000:
            return 250
        elif window_width < 1500:
            return 300
        else:
            return 350

    @staticmethod
    def calculate_content_width(window_width: int, sidebar_width: int) -> int:
        """Calcula ancho del contenido (rest del espacio)."""
        return max(window_width - sidebar_width, 500)

    @staticmethod
    def get_padding_for_screen_width(width: int) -> Tuple[int, int]:
        """Retorna (padx, pady) basado en ancho de pantalla."""
        if width < 800:
            return (8, 8)
        elif width < 1200:
            return (12, 10)
        else:
            return (16, 12)

    @staticmethod
    def get_font_scale(width: int) -> float:
        """Retorna factor de escala de fuentes basado en ancho."""
        if width < 800:
            return 0.9
        elif width < 1200:
            return 1.0
        else:
            return 1.1

    @staticmethod
    def get_button_width(available_width: int) -> int:
        """Calcula ancho de botones basado en espacio disponible."""
        if available_width < 300:
            return available_width - 20
        elif available_width < 500:
            return (available_width - 30) // 2
        else:
            return (available_width - 40) // 3


class GridHelper:
    """Helper para configurar grillas responsive."""

    @staticmethod
    def configure_responsive_grid(
        frame: ctk.CTkFrame,
        columns: int = 1,
        rows: int = 1,
        expand_col: int = 0,
        expand_row: int = 0,
    ) -> None:
        """
        Configura una grilla responsive.

        Args:
            frame: Frame a configurar
            columns: Número de columnas
            rows: Número de filas
            expand_col: Columna que se expande (weight=1)
            expand_row: Fila que se expande (weight=1)
        """
        for col in range(columns):
            weight = 1 if col == expand_col else 0
            frame.grid_columnconfigure(col, weight=weight)

        for row in range(rows):
            weight = 1 if row == expand_row else 0
            frame.grid_rowconfigure(row, weight=weight)


class BreakpointListener:
    """Detecta cambios de tamaño y dispara callbacks."""

    def __init__(self, window: ctk.CTk):
        self.window = window
        self.last_width = window.winfo_width()
        self.last_height = window.winfo_height()
        self._callbacks = []
        self._poll_interval = 200  # ms

        # Iniciar polling
        self._schedule_check()

    def on_resize(self, callback) -> None:
        """Registra callback para cuando cambia el tamaño."""
        self._callbacks.append(callback)

    def _schedule_check(self) -> None:
        """Verifica periódicamente cambios de tamaño."""
        try:
            current_width = self.window.winfo_width()
            current_height = self.window.winfo_height()

            # Detectar breakpoints comunes
            if (
                abs(current_width - self.last_width) > 50
                or abs(current_height - self.last_height) > 50
            ):
                self.last_width = current_width
                self.last_height = current_height

                for callback in self._callbacks:
                    try:
                        callback(current_width, current_height)
                    except Exception as e:
                        print(f"Error en callback resize: {e}")

            # Próxima verificación
            self.window.after(self._poll_interval, self._schedule_check)
        except:
            # Window destruida
            pass
