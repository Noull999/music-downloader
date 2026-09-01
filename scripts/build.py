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
                try:
                    shutil.rmtree(folder)
                except OSError as e:
                    # Archivos bloqueados (ej: el log de una instancia abierta
                    # de la app) no impiden el build: PyInstaller pisa el exe.
                    print(f"⚠️  No se pudo borrar todo {folder} ({e}); se continúa")

    # 2️⃣ ffmpeg
    ffmpeg_path = None if no_ffmpeg else ensure_ffmpeg()

    # 3️⃣ PyInstaller
    # (ffmpeg se embebe leyendo build/ffmpeg/ffmpeg.exe desde el propio .spec,
    # ya que el build es onefile y no existe dist/_internal para copiarlo después)
    cmd = [
        PYTHON, "-m", "PyInstaller",
        str(BASE / "MusicDownloader.spec"),
        "--clean",
        "--noconfirm",
    ]

    res = run(cmd, cwd=BASE)
    if res.returncode != 0:
        print("❌ PyInstaller falló")
        raise SystemExit(res.returncode)

    if ffmpeg_path and ffmpeg_path.exists():
        print(f"✅ ffmpeg embebido en el .exe (bundle onefile): {ffmpeg_path}")

    bundle_root = BASE / "dist"
    exe_path = bundle_root / ("MusicDownloader.exe" if SYSTEM == "Windows" else "MusicDownloader")

    # 4️⃣ Firma (solo Windows): sin firma, Smart App Control (activado por
    # defecto en instalaciones nuevas de Windows 11 tras su período de
    # evaluación) bloquea directamente cualquier .exe sin reputación
    # conocida. No hace falta certificado pago: uno autofirmado, agregado a
    # los almacenes de confianza de ESTA cuenta de Windows, alcanza para que
    # SAC lo permita correr en esta misma PC (no sirve para distribuirlo a
    # otra máquina, que no confía en el certificado).
    if SYSTEM == "Windows" and exe_path.exists():
        sign_windows(exe_path)

    print("\n✅ Build finalizado:")
    print(f"   {exe_path}")


def sign_windows(exe_path: Path) -> None:
    """Firma el .exe con un certificado autofirmado, creándolo si hace falta."""
    ps_script = f"""
$subject = "CN=Music Downloader (local build)"
$cert = Get-ChildItem Cert:\\CurrentUser\\My -CodeSigningCert |
    Where-Object {{ $_.Subject -eq $subject }} | Select-Object -First 1

if (-not $cert) {{
    $cert = New-SelfSignedCertificate -Subject $subject -Type CodeSigningCert `
        -KeyUsage DigitalSignature -KeyExportPolicy Exportable `
        -CertStoreLocation "Cert:\\CurrentUser\\My" -NotAfter (Get-Date).AddYears(10)

    $rootStore = New-Object System.Security.Cryptography.X509Certificates.X509Store("Root", "CurrentUser")
    $rootStore.Open("ReadWrite"); $rootStore.Add($cert); $rootStore.Close()
    $pubStore = New-Object System.Security.Cryptography.X509Certificates.X509Store("TrustedPublisher", "CurrentUser")
    $pubStore.Open("ReadWrite"); $pubStore.Add($cert); $pubStore.Close()
}}

Set-AuthenticodeSignature -FilePath "{exe_path}" -Certificate $cert | Out-Null
"""
    result = subprocess.run(
        ["powershell", "-ExecutionPolicy", "Bypass", "-NoProfile", "-Command", ps_script],
        capture_output=True, text=True,
    )
    if result.returncode == 0:
        print("✅ .exe firmado (certificado local, alcanza para Smart App Control en esta PC)")
    else:
        print(f"⚠️  No se pudo firmar el .exe automáticamente: {result.stderr.strip()}")
        print("    Si Windows lo bloquea al abrirlo, corré manualmente:")
        print(f'    powershell -Command "Set-AuthenticodeSignature -FilePath \'{exe_path}\' -Certificate $cert"')


def main():
    parser = argparse.ArgumentParser(description="Build Music Downloader")
    parser.add_argument("--console", action="store_true", help="Modo consola")
    parser.add_argument("--no-ffmpeg", action="store_true", help="Sin ffmpeg embebido")
    parser.add_argument("--clean", action="store_true", help="Clean build")
    args = parser.parse_args()

    build(console=args.console, no_ffmpeg=args.no_ffmpeg, clean=args.clean)


if __name__ == "__main__":
    main()
