#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Construit la version Windows sans Python : dist/DofusPriceHelper-<version>.zip
------------------------------------------------------------------------------
Contenu du zip (dossier DofusPriceHelper/) :
  DofusPriceHelper.exe   l'interface (PyInstaller, mode dossier : démarrage rapide)
  _internal/             Python, bibliothèques, Tesseract inclus (anglais : chiffres seulement)
  LISEZ-MOI.txt          installation, antivirus, emplacement des réglages

Utilisation (Windows, depuis la racine du projet, dépendances + pyinstaller installés) :
  python packaging/build.py --version v1.0.0 [--tesseract-dir "C:\\Program Files\\Tesseract-OCR"]

Le même script tourne dans GitHub Actions (.github/workflows/build-exe.yml).
"""
from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BUILD = ROOT / "build"
DIST = ROOT / "dist"
NAME = "DofusPriceHelper"
MIN_TESSERACT = (5, 0)

README = """Dofus Price Helper {version}
================================

Lancement : double-clic sur DofusPriceHelper.exe (garder le dossier _internal à côté).
Rien d'autre à installer : Tesseract (lecture des chiffres) est inclus. Si un Tesseract 5
ou plus récent est déjà installé sur le PC, c'est lui qui est utilisé.

Réglages, calibration et historique : %APPDATA%\\Dofus Price Helper
Ils sont gardés quand tu passes à une nouvelle version (nouveau zip, nouveau dossier).

Windows / antivirus
-------------------
L'exe n'est pas signé et il lit le clavier (raccourcis F1, F2…) et simule des touches :
Windows SmartScreen peut afficher « Windows a protégé votre PC » -> « Informations
complémentaires » -> « Exécuter quand même ». Certains antivirus peuvent le signaler.
Le code source est public : https://github.com/Jul1111/Auto-Dofus-Price-Update

Si les raccourcis ne réagissent pas dans le jeu : clic droit sur l'exe -> « Exécuter en
tant qu'administrateur ».

Avertissement
-------------
Les conditions d'utilisation d'Ankama interdisent en général les logiciels tiers qui
interagissent avec le client de jeu. Utilisation à vos risques.
Projet indépendant, non affilié à Ankama. Licence MIT.
Tesseract OCR : licence Apache 2.0 (voir _internal/tesseract/LICENSES).
"""


def find_tesseract(given: str | None) -> Path:
    cands = [given] if given else [shutil.which("tesseract"), r"C:\Program Files\Tesseract-OCR\tesseract.exe"]
    for c in cands:
        if not c:
            continue
        p = Path(c)
        p = p / "tesseract.exe" if p.is_dir() else p
        if p.exists():
            return p
    sys.exit(f"Tesseract introuvable ({given or 'PATH / Program Files'}).")


def tesseract_version(exe: Path) -> tuple:
    out = subprocess.run([str(exe), "--version"], capture_output=True, text=True)
    m = re.search(r"tesseract\s+v?(\d+)\.(\d+)", out.stdout + out.stderr, re.IGNORECASE)
    if not m:
        sys.exit(f"Version de Tesseract illisible : {out.stdout + out.stderr!r}")
    return int(m.group(1)), int(m.group(2))


def needed_dlls(exe: Path) -> list:
    """DLL chargées par tesseract.exe (dépendances, récursivement), parmi celles de son dossier.
    Les autres (cairo, pango… des outils d'entraînement) ne sont pas incluses."""
    import pefile   # installé avec PyInstaller
    src = exe.parent
    local = {f.name.lower(): f for f in src.glob("*.dll")}
    seen, todo = set(), [exe]
    while todo:
        pe = pefile.PE(str(todo.pop()), fast_load=True)
        pe.parse_data_directories(directories=[pefile.DIRECTORY_ENTRY["IMAGE_DIRECTORY_ENTRY_IMPORT"],
                                               pefile.DIRECTORY_ENTRY["IMAGE_DIRECTORY_ENTRY_DELAY_IMPORT"]])
        for entry in getattr(pe, "DIRECTORY_ENTRY_IMPORT", []) + getattr(pe, "DIRECTORY_ENTRY_DELAY_IMPORT", []):
            name = entry.dll.decode(errors="ignore").lower()
            if name in local and name not in seen:
                seen.add(name)
                todo.append(local[name])
        pe.close()
    return sorted(local[n] for n in seen)


def copy_tesseract(exe: Path, dest: Path) -> None:
    """Le strict nécessaire : tesseract.exe, ses DLL, eng.traineddata (chiffres), licences."""
    src = exe.parent
    if dest.exists():
        shutil.rmtree(dest)
    (dest / "tessdata").mkdir(parents=True)
    shutil.copy2(exe, dest)
    dlls = needed_dlls(exe)
    for dll in dlls:
        shutil.copy2(dll, dest)
    print(f"{len(dlls)} DLL incluses sur {len(list(src.glob('*.dll')))}")
    shutil.copy2(src / "tessdata" / "eng.traineddata", dest / "tessdata")
    lic = dest / "LICENSES"
    lic.mkdir()
    for f in [src / "doc" / "LICENSE", src / "doc" / "AUTHORS", src / "LICENSE"]:
        if f.exists():
            shutil.copy2(f, lic / f"tesseract-{f.name}.txt")
    (lic / "README.txt").write_text(
        "Tesseract OCR (Apache License 2.0) : https://github.com/tesseract-ocr/tesseract\n"
        "Version Windows : UB Mannheim, https://github.com/UB-Mannheim/tesseract\n",
        encoding="utf-8")


def check_bundled(dest: Path) -> None:
    """Le Tesseract copié doit fonctionner SEUL (DLL et tessdata complets)."""
    out = subprocess.run([str(dest / "tesseract.exe"), "--list-langs"], capture_output=True, text=True,
                         cwd=dest)
    if out.returncode != 0 or "eng" not in out.stdout:
        sys.exit(f"Tesseract copié inutilisable : {out.stdout}{out.stderr}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--version", default="dev", help="ex. v1.0.0 (nom du tag)")
    ap.add_argument("--tesseract-dir", help="dossier ou exe de Tesseract à inclure")
    ap.add_argument("--out", default=str(DIST), help="dossier de sortie (défaut : dist/)")
    args = ap.parse_args()
    dist = Path(args.out).resolve()
    version = args.version

    exe = find_tesseract(args.tesseract_dir)
    ver = tesseract_version(exe)
    print(f"Tesseract inclus : {exe} ({ver[0]}.{ver[1]})")
    if ver < MIN_TESSERACT:
        sys.exit(f"Tesseract {ver} trop ancien (>= {MIN_TESSERACT} requis).")

    BUILD.mkdir(exist_ok=True)
    tess = BUILD / "tesseract"
    copy_tesseract(exe, tess)
    check_bundled(tess)
    (BUILD / "version.txt").write_text(version, encoding="utf-8")

    cmd = [sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--windowed",
           "--name", NAME, "--distpath", str(dist), "--workpath", str(BUILD / "pyinstaller"),
           "--specpath", str(BUILD),
           "--collect-data", "customtkinter",
           str(ROOT / "dofus_price_helper_psg.py")]
    print(" ".join(cmd))
    subprocess.run(cmd, check=True, cwd=ROOT)

    app = dist / NAME
    internal = app / "_internal"   # = sys._MEIPASS (APP_DIR dans dofus_core)
    # Tesseract et version.txt copiés APRÈS PyInstaller : passés en --add-data, ses DLL étaient
    # analysées et dupliquées à la racine (~35 Mo de plus).
    shutil.copytree(tess, internal / "tesseract")
    shutil.copy2(BUILD / "version.txt", internal / "version.txt")
    # Module vidéo d'OpenCV (~40 Mo) : inutile, l'outil ne lit que des captures d'écran.
    for f in internal.glob("cv2/opencv_videoio_ffmpeg*.dll"):
        f.unlink()
    (app / "LISEZ-MOI.txt").write_text(README.format(version=version), encoding="utf-8")
    shutil.copy2(ROOT / "LICENSE", app / "LICENSE.txt")

    zip_path = dist / f"{NAME}-{version}.zip"
    zip_path.unlink(missing_ok=True)
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for f in sorted(app.rglob("*")):
            z.write(f, Path(NAME) / f.relative_to(app))
    print(f"OK : {zip_path} ({zip_path.stat().st_size / 1e6:.0f} Mo)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
