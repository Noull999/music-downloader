"""
Gestor de temas: Dark/Light mode con esquemas de color personalizables.
"""
from typing import Dict, Tuple
import customtkinter as ctk


THEMES = {
    "dark": {
        "bg_primary": "#0a0a0a",
        "bg_secondary": "#1a1a1a",
        "bg_tertiary": "#2a2a2a",
        "fg_primary": "#ffffff",
        "fg_secondary": "#9ca3af",
        "accent": "#3b82f6",
        "success": "#10b981",
        "error": "#ef4444",
        "warning": "#f59e0b",
    },
    "light": {
        "bg_primary": "#ffffff",
        "bg_secondary": "#f3f4f6",
        "bg_tertiary": "#e5e7eb",
        "fg_primary": "#1f2937",
        "fg_secondary": "#6b7280",
        "accent": "#2563eb",
        "success": "#059669",
        "error": "#dc2626",
        "warning": "#d97706",
    }
}

COLOR_SCHEMES = {
    "blue": {"primary": "#3b82f6", "hover": "#1d4ed8"},
    "green": {"primary": "#10b981", "hover": "#059669"},
    "purple": {"primary": "#8b5cf6", "hover": "#6d28d9"},
    "red": {"primary": "#ef4444", "hover": "#dc2626"},
    "amber": {"primary": "#f59e0b", "hover": "#d97706"},
}


class ThemeManager:
    """Gestiona temas y colores de la aplicación."""

    def __init__(self, theme: str = "dark", color_scheme: str = "blue"):
        self.current_theme = theme
        self.current_color_scheme = color_scheme
        self._apply_theme(theme, color_scheme)

    @staticmethod
    def _apply_theme(theme: str, color_scheme: str) -> None:
        """Aplica tema a CustomTkinter."""
        valid_themes = list(THEMES.keys())
        valid_schemes = list(COLOR_SCHEMES.keys())

        if theme not in valid_themes:
            theme = "dark"
        if color_scheme not in valid_schemes:
            color_scheme = "blue"

        ctk.set_appearance_mode(theme)
        ctk.set_default_color_theme(color_scheme)

    def switch_theme(self, theme: str) -> None:
        """Cambia entre dark/light."""
        if theme not in THEMES:
            raise ValueError(f"Tema inválido: {theme}")
        self.current_theme = theme
        self._apply_theme(theme, self.current_color_scheme)

    def switch_color_scheme(self, scheme: str) -> None:
        """Cambia esquema de color."""
        if scheme not in COLOR_SCHEMES:
            raise ValueError(f"Esquema inválido: {scheme}")
        self.current_color_scheme = scheme
        self._apply_theme(self.current_theme, scheme)

    def get_color(self, key: str) -> str:
        """Obtiene color del tema actual."""
        return THEMES[self.current_theme].get(key, "#000000")

    def get_scheme_color(self, key: str = "primary") -> str:
        """Obtiene color del esquema actual."""
        return COLOR_SCHEMES[self.current_color_scheme].get(key, "#3b82f6")

    @staticmethod
    def get_available_themes() -> list:
        """Retorna lista de temas disponibles."""
        return list(THEMES.keys())

    @staticmethod
    def get_available_color_schemes() -> list:
        """Retorna lista de esquemas disponibles."""
        return list(COLOR_SCHEMES.keys())
