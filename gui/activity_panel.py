import customtkinter as ctk
from typing import Callable, Optional


class ActivityPanel(ctk.CTkFrame):
    """Real-time activity log for current downloads."""

    def __init__(self, parent, height: int = 120, **kwargs):
        super().__init__(parent, fg_color="transparent", **kwargs)

        self._height = height
        self._build_ui()

    def _build_ui(self):
        """Build the activity panel UI."""
        # Header
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", pady=(0, 8))

        ctk.CTkLabel(
            header, text="Actividad",
            font=ctk.CTkFont(size=12, weight="bold")
        ).pack(anchor="w")

        # Log text box
        self._log_text = ctk.CTkTextbox(
            self, height=self._height - 30,
            fg_color="#1e1e1e", text_color="#d4d4d4",
            font=ctk.CTkFont("Courier", size=9)
        )
        self._log_text.pack(fill="both", expand=True)
        self._log_text.configure(state="disabled")

    def log(self, message: str):
        """Add a line to the activity log."""
        try:
            self._log_text.configure(state="normal")

            # Auto-scroll: append at the end
            self._log_text.insert("end", f"{message}\n")

            # Keep only last 50 lines to avoid memory bloat
            content = self._log_text.get("1.0", "end-1c")
            if content:
                lines = content.split("\n")
                if len(lines) > 50:
                    excess = len(lines) - 50
                    self._log_text.delete("1.0", f"{excess}.0")

            # Auto-scroll to bottom
            self._log_text.see("end")

            self._log_text.configure(state="disabled")
        except Exception:
            pass  # silently ignore log errors to prevent crash

    def clear(self):
        """Clear the activity log."""
        self._log_text.configure(state="normal")
        self._log_text.delete("1.0", "end")
        self._log_text.configure(state="disabled")
