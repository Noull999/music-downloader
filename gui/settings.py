"""
Dialogo de configuracion: calidad de descarga + post-procesado + opciones de archivo.
"""
import customtkinter as ctk
from quality.presets import QUALITY_PRESETS, PRESET_ORDER, DEFAULT_PRESET
from utils.genres import UNCLASSIFIED_FOLDER


class SettingsDialog(ctk.CTkToplevel):
    """Ventana modal de configuracion avanzada."""

    def __init__(self, parent, config: dict, on_save_callback=None):
        super().__init__(parent)
        self.title("Configuracion")
        self.geometry("540x700")
        self.resizable(True, True)
        self.grab_set()
        self.transient(parent)

        self._config = config
        self._on_save_callback = on_save_callback
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)

        self._build()
        self._load_values()

    # ------------------------------------------------------------------ #
    # Construccion                                                         #
    # ------------------------------------------------------------------ #

    def _build(self):
        # Contenido scrolleable
        scroll = ctk.CTkScrollableFrame(self, fg_color="transparent")
        scroll.grid(row=0, column=0, sticky="nsew", padx=0, pady=0)
        scroll.grid_columnconfigure(0, weight=1)

        row = 0

        # Titulo
        ctk.CTkLabel(
            scroll, text="⚙️ Configuración",
            font=ctk.CTkFont(size=18, weight="bold"),
        ).grid(row=row, column=0, padx=24, pady=(20, 4), sticky="w")

        # ── Calidad de descarga ──────────────────────────────────────── #
        row += 1
        header_frame = ctk.CTkFrame(scroll, fg_color="#1e1e2e", corner_radius=6)
        header_frame.grid(row=row, column=0, padx=24, pady=(12, 0), sticky="ew", ipady=8)
        header_frame.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            header_frame, text="🎵 Calidad de descarga",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color="#60a5fa",
        ).grid(row=0, column=0, padx=16, pady=0, sticky="w")

        self._quality_var = ctk.StringVar(value=DEFAULT_PRESET)
        self._warning_lbl = ctk.CTkLabel(
            scroll, text="", text_color="#f59e0b",
            font=ctk.CTkFont(size=11), wraplength=460, justify="left",
        )

        row += 1
        quality_frame = ctk.CTkFrame(scroll, fg_color="transparent")
        quality_frame.grid(row=row, column=0, padx=28, pady=(2, 4), sticky="ew")

        for key in PRESET_ORDER:
            preset = QUALITY_PRESETS[key]
            radio = ctk.CTkRadioButton(
                quality_frame,
                text=preset["label"],
                variable=self._quality_var,
                value=key,
                command=self._on_quality_change,
            )
            radio.pack(anchor="w", pady=2)
            desc = ctk.CTkLabel(
                quality_frame, text=f"   {preset['description']}",
                font=ctk.CTkFont(size=11), text_color="#6b7280",
                anchor="w",
            )
            desc.pack(anchor="w", pady=(0, 4))

        row += 1
        self._warning_lbl.grid(row=row, column=0, padx=28, pady=(0, 8), sticky="ew")

        # ── Post-procesado ───────────────────────────────────────────── #
        row += 1
        pp_header = ctk.CTkFrame(scroll, fg_color="#1e1e2e", corner_radius=6)
        pp_header.grid(row=row, column=0, padx=24, pady=(12, 0), sticky="ew", ipady=8)
        pp_header.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            pp_header, text="🎚️ Post-procesado",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color="#34d399",
        ).grid(row=0, column=0, padx=16, pady=0, sticky="w")

        self._normalize_var = ctk.BooleanVar(value=False)
        self._silence_var = ctk.BooleanVar(value=False)
        self._artwork_var = ctk.BooleanVar(value=True)
        self._metadata_var = ctk.BooleanVar(value=True)
        self._lyrics_var = ctk.BooleanVar(value=False)
        self._genre_var = ctk.BooleanVar(value=True)
        self._beets_var = ctk.BooleanVar(value=False)

        row += 1
        pp_frame = ctk.CTkFrame(scroll, fg_color="transparent")
        pp_frame.grid(row=row, column=0, padx=28, pady=(2, 8), sticky="ew")

        options = [
            (self._normalize_var, "Normalizar volumen entre canciones",
             "Todas suenan al mismo volumen (-14 LUFS / EBU R128). Requiere ffmpeg."),
            (self._silence_var, "Eliminar silencios largos al inicio/final",
             "Quita silencios >0.5s. Requiere ffmpeg."),
            (self._metadata_var, "Embeber metadatos (ID3 tags)",
             "Artista, titulo, album, ano en el archivo. Ahora tambien en FLAC."),
            (self._artwork_var, "Embeber caratula en alta resolucion",
             "Descarga thumbnail y la embebe en el archivo (MP3 y FLAC)."),
            (self._lyrics_var, "Buscar y embeber letras",
             "Via syncedlyrics (LRCLIB/Musixmatch/etc). Requiere 'pip install syncedlyrics'."),
            (self._genre_var, "Embeber género en el archivo",
             "Guarda el género (SoundCloud, normalizado) como tag del archivo."),
            (self._beets_var, "Organizar con beets tras descargar",
             "Ejecuta 'beet import' si el CLI 'beet' esta instalado y configurado. Opcional."),
        ]
        for var, label, desc in options:
            ctk.CTkCheckBox(pp_frame, text=label, variable=var).pack(anchor="w", pady=2)
            ctk.CTkLabel(
                pp_frame, text=f"   {desc}",
                font=ctk.CTkFont(size=11), text_color="#6b7280", anchor="w",
            ).pack(anchor="w", pady=(0, 6))

        # Nota importante
        row += 1
        ctk.CTkLabel(
            scroll, text="Nota importante",
            font=ctk.CTkFont(size=12, weight="bold"),
        ).grid(row=row, column=0, padx=24, pady=(8, 0), sticky="w")

        row += 1
        ctk.CTkLabel(
            scroll,
            text=(
                "No es posible mejorar la calidad de un audio mas alla del "
                "original disponible en la plataforma. La normalizacion, metadatos "
                "y caratulas son optimizaciones reales. No hay reconstruccion de audio."
            ),
            font=ctk.CTkFont(size=11), text_color="#6b7280",
            wraplength=462, justify="left",
        ).grid(row=row, column=0, padx=28, pady=(2, 12), sticky="ew")

        # ── Archivo ─────────────────────────────────────────────────── #
        row += 1
        file_header = ctk.CTkFrame(scroll, fg_color="#1e1e2e", corner_radius=6)
        file_header.grid(row=row, column=0, padx=24, pady=(12, 0), sticky="ew", ipady=8)
        file_header.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            file_header, text="📁 Nombre de archivo",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color="#fbbf24",
        ).grid(row=0, column=0, padx=16, pady=0, sticky="w")

        row += 1
        self._pattern_entry = ctk.CTkEntry(
            scroll, placeholder_text="{artist} - {title}",
        )
        self._pattern_entry.grid(row=row, column=0, padx=28, pady=(2, 2), sticky="ew")

        row += 1
        ctk.CTkLabel(
            scroll, text="   Variables: {artist}, {title}",
            font=ctk.CTkFont(size=11), text_color="#6b7280",
        ).grid(row=row, column=0, padx=28, pady=(0, 4), sticky="w")

        row += 1
        self._subfolder_var = ctk.BooleanVar(value=False)
        ctk.CTkCheckBox(
            scroll, text="Crear subcarpeta por artista",
            variable=self._subfolder_var,
        ).grid(row=row, column=0, padx=28, pady=(0, 4), sticky="w")

        row += 1
        self._subfolder_genre_var = ctk.BooleanVar(value=False)
        ctk.CTkCheckBox(
            scroll, text="Crear subcarpeta por género",
            variable=self._subfolder_genre_var,
        ).grid(row=row, column=0, padx=28, pady=(0, 2), sticky="w")
        row += 1
        ctk.CTkLabel(
            scroll,
            text="   Usa el género de SoundCloud normalizado. Si ya tenés una "
                 "carpeta con ese género (ej. 'PSYTRANCE'), la reutiliza tal "
                 "cual en vez de crear otra. Sin género reconocido → carpeta "
                 f"'{UNCLASSIFIED_FOLDER}'.",
            font=ctk.CTkFont(size=11), text_color="#6b7280",
            wraplength=462, justify="left",
        ).grid(row=row, column=0, padx=28, pady=(0, 4), sticky="ew")

        # ── Delay ───────────────────────────────────────────────────── #
        row += 1
        delay_header = ctk.CTkFrame(scroll, fg_color="#1e1e2e", corner_radius=6)
        delay_header.grid(row=row, column=0, padx=24, pady=(12, 0), sticky="ew", ipady=8)
        delay_header.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            delay_header, text="⏱️ Delay entre descargas",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color="#f472b6",
        ).grid(row=0, column=0, padx=16, pady=0, sticky="w")

        row += 1
        delay_row = ctk.CTkFrame(scroll, fg_color="transparent")
        delay_row.grid(row=row, column=0, padx=28, pady=(2, 8), sticky="ew")
        delay_row.grid_columnconfigure(0, weight=1)

        self._delay_val_lbl = ctk.CTkLabel(delay_row, text="0.5", width=36)
        self._delay_val_lbl.grid(row=0, column=1, padx=(8, 0))

        self._delay_slider = ctk.CTkSlider(
            delay_row, from_=0, to=5, number_of_steps=50,
            command=lambda v: self._delay_val_lbl.configure(text=f"{v:.1f}"),
        )
        self._delay_slider.grid(row=0, column=0, sticky="ew")

        # ── SoundCloud OAuth ─────────────────────────────────────────── #
        row += 1
        oauth_header = ctk.CTkFrame(scroll, fg_color="#1e1e2e", corner_radius=6)
        oauth_header.grid(row=row, column=0, padx=24, pady=(12, 0), sticky="ew", ipady=8)
        oauth_header.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            oauth_header, text="☁️ SoundCloud OAuth (opcional)",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color="#a78bfa",
        ).grid(row=0, column=0, padx=16, pady=0, sticky="w")

        row += 1
        self._token_entry = ctk.CTkEntry(
            scroll, placeholder_text="Pegar token aqui...", show="*",
        )
        self._token_entry.grid(row=row, column=0, padx=28, pady=(2, 4), sticky="ew")

        row += 1
        ctk.CTkLabel(
            scroll, text="   Mejora limites de descarga en SoundCloud.",
            font=ctk.CTkFont(size=11), text_color="#6b7280",
        ).grid(row=row, column=0, padx=28, pady=(0, 12), sticky="w")

        # ── Botones ─────────────────────────────────────────────────── #
        btn_row = ctk.CTkFrame(self, fg_color="transparent")
        btn_row.grid(row=1, column=0, padx=24, pady=(4, 20), sticky="e")

        ctk.CTkButton(
            btn_row, text="Cancelar",
            fg_color="#374151", hover_color="#4b5563",
            command=self.destroy,
        ).pack(side="left", padx=(0, 8))

        ctk.CTkButton(btn_row, text="Guardar", command=self._save).pack(side="left")

    # ------------------------------------------------------------------ #
    # Carga y guardado                                                     #
    # ------------------------------------------------------------------ #

    def _load_values(self):
        self._quality_var.set(self._config.get("quality_preset", DEFAULT_PRESET))
        self._normalize_var.set(self._config.get("normalize_volume", False))
        self._silence_var.set(self._config.get("remove_silence", False))
        self._artwork_var.set(self._config.get("embed_artwork", True))
        self._metadata_var.set(self._config.get("embed_metadata", True))
        self._lyrics_var.set(self._config.get("embed_lyrics", False))
        self._genre_var.set(self._config.get("embed_genre", True))
        self._beets_var.set(self._config.get("organize_with_beets", False))

        pattern = self._config.get("filename_pattern", "{artist} - {title}")
        self._pattern_entry.delete(0, "end")
        self._pattern_entry.insert(0, pattern)

        self._subfolder_var.set(self._config.get("subfolder_by_artist", False))
        self._subfolder_genre_var.set(self._config.get("subfolder_by_genre", False))

        delay = float(self._config.get("delay", 0.5))
        self._delay_slider.set(delay)
        self._delay_val_lbl.configure(text=f"{delay:.1f}")

        # Leer de la ruta unificada; mantener compatibilidad con key antigua
        token = (self._config.get("soundcloud", {}).get("oauth_token", "")
                 or self._config.get("oauth_token", ""))
        self._token_entry.delete(0, "end")
        if token:
            self._token_entry.insert(0, token)

        self._on_quality_change()

    def _on_quality_change(self):
        key = self._quality_var.get()
        warning = QUALITY_PRESETS.get(key, {}).get("warning") or ""
        self._warning_lbl.configure(text=warning)

    def _save(self):
        pattern = self._pattern_entry.get().strip() or "{artist} - {title}"
        updates = {
            "quality_preset": self._quality_var.get(),
            "normalize_volume": self._normalize_var.get(),
            "remove_silence": self._silence_var.get(),
            "embed_artwork": self._artwork_var.get(),
            "embed_metadata": self._metadata_var.get(),
            "embed_lyrics": self._lyrics_var.get(),
            "embed_genre": self._genre_var.get(),
            "organize_with_beets": self._beets_var.get(),
            "filename_pattern": pattern,
            "subfolder_by_artist": self._subfolder_var.get(),
            "subfolder_by_genre": self._subfolder_genre_var.get(),
            "delay": round(self._delay_slider.get(), 1),
        }
        # Guardar token en ruta unificada y limpiar key obsoleta
        updates.setdefault("soundcloud", {})["oauth_token"] = self._token_entry.get().strip()
        updates.pop("oauth_token", None)

        # Llamar callback para persistir cambios
        if self._on_save_callback:
            self._on_save_callback(updates)

        self.destroy()
