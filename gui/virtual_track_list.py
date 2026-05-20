"""
Track List Virtualizado: renderiza solo items visibles + buffer.
Evita congelar UI con 1000+ canciones.
Uso: VirtualTrackList(parent, height=400, on_select=callback)
"""
import customtkinter as ctk
import logging

logger = logging.getLogger(__name__)

ITEM_HEIGHT = 50  # px por track
BUFFER_SIZE = 5   # items extra arriba/abajo para scroll suave


class VirtualTrackList(ctk.CTkFrame):
    """Canvas virtualizado que solo renderiza items visibles."""

    def __init__(
        self,
        parent,
        height: int = 400,
        on_select=None,
        on_double_click=None,
    ):
        super().__init__(parent, fg_color="transparent")
        self.configure(height=height)

        self._height = height
        self._items = []
        self._selected_idx = None
        self._on_select = on_select
        self._on_double_click = on_double_click
        self._visible_range = (0, 0)
        self._item_widgets = {}

        # Canvas scrolleable
        self._canvas = ctk.CTkCanvas(
            self, bg="#0d0e15", highlightthickness=0, height=height
        )
        self._canvas.pack(side="left", fill="both", expand=True)

        # Scrollbar
        scrollbar = ctk.CTkScrollbar(
            self, command=self._canvas.yview, fg_color="#1e1e2e"
        )
        scrollbar.pack(side="right", fill="y")
        self._canvas.configure(yscrollcommand=scrollbar.set)

        # Frame dentro del canvas para items
        self._frame = ctk.CTkFrame(self._canvas, fg_color="transparent")
        self._canvas_window = self._canvas.create_window(0, 0, window=self._frame, anchor="nw")

        # Eventos
        self._canvas.bind("<MouseWheel>", self._on_scroll)
        self._canvas.bind("<Button-4>", self._on_scroll)  # Linux scroll up
        self._canvas.bind("<Button-5>", self._on_scroll)  # Linux scroll down

    def load_items(self, items: list) -> None:
        """Carga lista de items (puede ser muy grande)."""
        self._items = items
        self._update_visible_items()
        logger.debug(f"✓ Lazy list cargada ({len(items)} items)")

    def _on_scroll(self, event):
        """Detecta scroll y actualiza items visibles."""
        delta = -1 if event.delta > 0 else 1
        self._canvas.yview_scroll(delta, "units")
        self._update_visible_items()

    def _update_visible_items(self) -> None:
        """Renderiza solo items visibles + buffer."""
        if not self._items:
            return

        # Calcular rango visible
        scroll_y = self._canvas.yview()[0]
        visible_start = int(scroll_y * len(self._items))
        visible_count = max(1, self._height // ITEM_HEIGHT)
        visible_end = min(len(self._items), visible_start + visible_count + BUFFER_SIZE)
        visible_start = max(0, visible_start - BUFFER_SIZE // 2)

        if (visible_start, visible_end) == self._visible_range:
            return  # No cambió, no renderizar

        # Limpiar widgets fuera del rango
        to_remove = [
            idx for idx in self._item_widgets.keys()
            if not (visible_start <= idx < visible_end)
        ]
        for idx in to_remove:
            self._item_widgets[idx].destroy()
            del self._item_widgets[idx]

        # Renderizar nuevos items en rango
        for idx in range(visible_start, visible_end):
            if idx not in self._item_widgets:
                self._render_item(idx)

        self._visible_range = (visible_start, visible_end)

    def _render_item(self, idx: int) -> None:
        """Renderiza un item individual."""
        item = self._items[idx]
        widget = self._create_item_widget(idx, item)
        self._item_widgets[idx] = widget
        self._frame.grid_rowconfigure(idx, weight=0, minsize=ITEM_HEIGHT)

    def _create_item_widget(self, idx: int, item) -> ctk.CTkFrame:
        """Crea widget para un item. Override en subclase."""
        frame = ctk.CTkFrame(self._frame, fg_color="transparent")
        frame.grid(row=idx, column=0, sticky="ew", padx=4, pady=2)
        frame.grid_columnconfigure(0, weight=1)

        # Renderizar contenido del item
        text = f"{idx+1}. {item.get('title', 'N/A')[:60]}"
        label = ctk.CTkLabel(
            frame, text=text, font=ctk.CTkFont(size=11),
            text_color="#e5e7eb", anchor="w"
        )
        label.pack(side="left", fill="both", expand=True, padx=8)

        # Click handler
        label.bind("<Button-1>", lambda _: self._select_item(idx))
        frame.bind("<Button-1>", lambda _: self._select_item(idx))

        return frame

    def _select_item(self, idx: int) -> None:
        """Selecciona un item."""
        self._selected_idx = idx
        if self._on_select:
            self._on_select(idx, self._items[idx])

    def get_selected(self):
        """Retorna item seleccionado (None si ninguno)."""
        if self._selected_idx is not None and self._selected_idx < len(self._items):
            return self._items[self._selected_idx]
        return None

    def clear(self) -> None:
        """Limpia lista."""
        self._frame.destroy()
        self._frame = ctk.CTkFrame(self._canvas, fg_color="transparent")
        self._canvas_window = self._canvas.create_window(0, 0, window=self._frame, anchor="nw")
        self._items = []
        self._item_widgets = {}
        self._selected_idx = None
