"""
Dialogo de configuracion: calidad de descarga + post-procesado + opciones de archivo.
"""
import customtkinter as ctk
from quality.presets import QUALITY_PRESETS, PRESET_ORDER, DEFAULT_PRESET


class SettingsDialog(ctk.CTkToplevel):
    """Ventana modal de configuracion avanzada."""

    def __init__(self, parent, config: dict):
        super().__init__(parent)
        self.title("Configuracion")
        self.geometry("540x700")
        self.resizable(True, True)
        self.grab_set()
        self.transient(parent)

        self._config = config
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
            scroll, text="Configuracion",
            font=ctk.CTkFont(size=17, weight="bold"),
        ).grid(row=row, column=0, padx=24, pady=(20, 4), sticky="w")

        # ── Calidad de descarga ──────────────────────────────────────── #
        row += 1
        ctk.CTkLabel(
            scroll, text="Calidad de descarga",
            font=ctk.CTkFont(size=12, weight="bold"),
        ).grid(row=row, column=0, padx=24, pady=(8, 0), sticky="w")

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
        ctk.CTkLabel(
            scroll, text="Post-procesado",
            font=ctk.CTkFont(size=12, weight="bold"),
        ).grid(row=row, column=0, padx=24, pady=(8, 0), sticky="w")

        self._normalize_var = ctk.BooleanVar(value=False)
        self._silence_var = ctk.BooleanVar(value=False)
        self._artwork_var = ctk.BooleanVar(value=True)
        self._metadata_var = ctk.BooleanVar(value=True)

        row += 1
        pp_frame = ctk.CTkFrame(scroll, fg_color="transparent")
        pp_frame.grid(row=row, column=0, padx=28, pady=(2, 8), sticky="ew")

        options = [
            (self._normalize_var, "Normalizar volumen entre canciones",
             "Todas suenan al mismo volumen (-14 LUFS / EBU R128). Requiere ffmpeg."),
            (self._silence_var, "Eliminar silencios largos al inicio/final",
             "Quita silencios >0.5s. Requiere ffmpeg."),
            (self._metadata_var, "Embeber metadatos (ID3 tags)",
             "Artista, titulo, album, ano en el archivo."),
            (self._artwork_var, "Embeber caratula en alta resolucion",
             "Descarga thumbnail y la embebe en el MP3."),
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
        ctk.CTkLabel(
            scroll, text="Nombre de archivo",
            font=ctk.CTkFont(size=12, weight="bold"),
        ).grid(row=row, column=0, padx=24, pady=(8, 0), sticky="w")

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

        # ── Delay ───────────────────────────────────────────────────── #
        row += 1
        ctk.CTkLabel(
            scroll, text="Delay entre descargas (segundos)",
            font=ctk.CTkFont(size=12, weight="bold"),
        ).grid(row=row, column=0, padx=24, pady=(8, 0), sticky="w")

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
        ctk.CTkLabel(
            scroll, text="SoundCloud OAuth Token (opcional)",
            font=ctk.CTkFont(size=12, weight="bold"),
        ).grid(row=row, column=0, padx=24, pady=(8, 0), sticky="w")

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

        pattern = self._config.get("filename_pattern", "{artist} - {title}")
        self._pattern_entry.delete(0, "end")
        self._pattern_entry.insert(0, pattern)

        self._subfolder_var.set(self._config.get("subfolder_by_artist", False))

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
        self._config.update({
            "quality_preset": self._quality_var.get(),
            "normalize_volume": self._normalize_var.get(),
            "remove_silence": self._silence_var.get(),
            "embed_artwork": self._artwork_var.get(),
            "embed_metadata": self._metadata_var.get(),
            "filename_pattern": pattern,
            "subfolder_by_artist": self._subfolder_var.get(),
            "delay": round(self._delay_slider.get(), 1),
        })
        # Guardar token en ruta unificada y limpiar key obsoleta
        self._config.setdefault("soundcloud", {})["oauth_token"] = self._token_entry.get().strip()
        self._config.pop("oauth_token", None)
        self.destroy()
