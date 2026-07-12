#!/usr/bin/env python3
"""
Build script para Music Downloader.

Uso:
    python scripts/build.py [--console] [--no-ffmpeg] [--clean]

Opciones:
    --console      Ejecutable con consola (útil para debug)
    --no-ffmpeg    No incluir ffmpeg en el bundle
    --clean        Borra previous builds antes de armar
"""
import argparse
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
SYSTEM = platform.system()
PYTHON = sys.executable


def run(cmd: list[str], **kwargs):
    print(f"> {' '.join(cmd)}")
    return subprocess.run(cmd, **kwargs)


def ensure_ffmpeg() -> Path | None:
    """Asegura que exista un ffmpeg válido para empaquetar."""
    target_dir = BASE / "build" / "ffmpeg"
    target_dir.mkdir(parents=True, exist_ok=True)

    if SYSTEM == "Windows":
        target = target_dir / "ffmpeg.exe"
        if target.exists() and target.stat().st_size > 1_000_000:
            print(f"✓ ffmpeg ya presente en {target}")
            return target

        print("⬇️  Descargando ffmpeg para Windows...")
        # URL oficial básica (essentials build)
        url = "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip"
        zip_path = target_dir / "ffmpeg.zip"

        import urllib.request
        urllib.request.urlretrieve(url, zip_path)

        print("📦 Extrayendo...")
        import zipfile
        with zipfile.ZipFile(zip_path, "r") as zf:
            zf.extractall(target_dir)

        # Buscar el ffmpeg.exe dentro del extracto
        for root, _, files in os.walk(target_dir):
            for f in files:
                if f.lower() == "ffmpeg.exe":
                    src = Path(root) / f
                    dst = target_dir / "ffmpeg.exe"
                    shutil.move(str(src), str(dst))
                    # limpiar
                    shutil.rmtree(target_dir / "ffmpeg-*", ignore_errors=True)
                    zip_path.unlink(missing_ok=True)
                    print(f"✓ ffmpeg listo en {dst}")
                    return dst

        print("⚠️  No se pudo extraer ffmpeg.exe del zip descargado")
        return None

    else:
        # Linux / macOS: usa el del sistema
        path = shutil.which("ffmpeg")
        if path:
            print(f"✓ ffmpeg del sistema: {path}")
            return Path(path)
        print("⚠️  ffmpeg no encontrado en PATH; se construirá sin incluirlo")
        return None


def build(console: bool, no_ffmpeg: bool, clean: bool):
    # 1️⃣ Limpiar si pide
    if clean:
        for folder in [BASE / "build", BASE / "dist"]:
            if folder.exists():
                print(f"🧹 Borrando {folder}")
                shutil.rmtree(folder)

    # 2️⃣ ffmpeg
    ffmpeg_path = None if no_ffmpeg else ensure_ffmpeg()

    # 3️⃣ PyInstaller
    cmd = [
        PYTHON, "-m", "PyInstaller",
        str(BASE / "music-downloader.spec"),
        "--clean",
        "--noconfirm",
    ]
    if console:
        cmd += ["--console"]
    else:
        cmd += ["--windowed"]

    res = run(cmd, cwd=BASE)
    if res.returncode != 0:
        print("❌ PyInstaller falló")
        raise SystemExit(res.returncode)

    # 4️⃣ Mover ffmpeg al bundle
    if ffmpeg_path and ffmpeg_path.exists():
        # En Windows el .exe queda en dist/MusicDownloader.exe y los datos en dist/_internal
        bundle_root = BASE / "dist"
        internal = bundle_root / "_internal" / "ffmpeg"
        internal.mkdir(parents=True, exist_ok=True)
        dst = internal / ffmpeg_path.name
        shutil.copy2(ffmpeg_path, dst)
        print(f"✅ ffmpeg copiado al bundle: {dst}")

    print("\n✅ Build finalizado:")
    print(f"   {bundle_root / ('MusicDownloader.exe' if SYSTEM == 'Windows' else 'MusicDownloader')}")


def main():
    parser = argparse.ArgumentParser(description="Build Music Downloader")
    parser.add_argument("--console", action="store_true", help="Modo consola")
    parser.add_argument("--no-ffmpeg", action="store_true", help="Sin ffmpeg embebido")
    parser.add_argument("--clean", action="store_true", help="Clean build")
    args = parser.parse_args()

    build(console=args.console, no_ffmpeg=args.no_ffmpeg, clean=args.clean)


if __name__ == "__main__":
    main()
