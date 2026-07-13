#!/usr/bin/env python3
"""
Genera assets/icon.ico a partir de assets/icon_source_transparent.png
(el emblema recortado con fondo transparente).

Uso:
    python scripts/make_icon.py
"""
from pathlib import Path
from PIL import Image, ImageDraw, ImageFilter

BASE = Path(__file__).resolve().parents[1]
SRC = BASE / "assets" / "icon_source_transparent.png"
OUT_ICO = BASE / "assets" / "icon.ico"
OUT_PNG = BASE / "assets" / "icon.png"

CANVAS = 1024
CORNER_RADIUS = 180
BG_COLOR = (13, 13, 15, 255)
ICON_SIZES = [16, 24, 32, 48, 64, 128, 256]


def rounded_square(size: int, radius: int, color) -> Image.Image:
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.rounded_rectangle([0, 0, size - 1, size - 1], radius=radius, fill=color)
    return img


def main():
    emblem = Image.open(SRC).convert("RGBA")

    # Recortar al bounding box real del contenido (descarta el margen transparente)
    bbox = emblem.getbbox()
    emblem = emblem.crop(bbox)

    # Encajar el emblema en un cuadrado, dejando margen para que no toque los bordes
    target = int(CANVAS * 0.82)
    ratio = min(target / emblem.width, target / emblem.height)
    new_size = (int(emblem.width * ratio), int(emblem.height * ratio))
    emblem = emblem.resize(new_size, Image.LANCZOS)

    # Fondo: cuadrado redondeado oscuro (estilo icono de app)
    canvas = rounded_square(CANVAS, CORNER_RADIUS, BG_COLOR)

    # Glow suave detrás del emblema (a partir de su propio alpha, teñido de rojo)
    glow_source = emblem.resize((int(new_size[0] * 1.15), int(new_size[1] * 1.15)), Image.LANCZOS)
    glow = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    glow_layer = Image.new("RGBA", glow_source.size, (255, 40, 40, 0))
    glow_layer.putalpha(glow_source.getchannel("A").point(lambda a: min(a, 130)))
    glow_layer = glow_layer.filter(ImageFilter.GaussianBlur(24))
    gx = (CANVAS - glow_layer.width) // 2
    gy = (CANVAS - glow_layer.height) // 2
    glow.paste(glow_layer, (gx, gy), glow_layer)

    # Máscara para que el glow no se salga del cuadrado redondeado
    mask = rounded_square(CANVAS, CORNER_RADIUS, (255, 255, 255, 255)).getchannel("A")
    canvas = Image.alpha_composite(canvas, Image.composite(glow, Image.new("RGBA", canvas.size, (0, 0, 0, 0)), mask))

    # Emblema centrado encima
    ex = (CANVAS - new_size[0]) // 2
    ey = (CANVAS - new_size[1]) // 2
    canvas.paste(emblem, (ex, ey), emblem)

    canvas.save(OUT_PNG)
    canvas.save(OUT_ICO, sizes=[(s, s) for s in ICON_SIZES])
    print(f"OK: {OUT_ICO}")
    print(f"OK: {OUT_PNG}")


if __name__ == "__main__":
    main()
