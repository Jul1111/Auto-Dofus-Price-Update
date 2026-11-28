#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Sauvegarde / restauration des réglages : config (profils, personnages associés, raccourcis),
images des repères « Hôtel de vente », chiffres appris et derniers parcours Ctrl+F3.

Un seul fichier .zip, pour changer de PC ou réinstaller. La restauration n'extrait que ces
fichiers-là (jamais de chemin ni d'autre fichier), après avoir mis les actuels de côté.
"""
from __future__ import annotations

import fnmatch
import json
import time
import zipfile
from pathlib import Path
from typing import List, Optional

from dofus_helper import core

CONFIG_NAME = core.CONFIG_PATH.name
PATTERNS = (CONFIG_NAME, "hdv_anchor*.png", core.DIGITS_PATH.name, "dofus_relist_runs.json")
META = "sauvegarde.json"
SAFETY_DIR = "sauvegardes"


def _allowed(name: str) -> bool:
    return "/" not in name and "\\" not in name and any(fnmatch.fnmatch(name, p) for p in PATTERNS)


def backup_files(base: Path) -> List[Path]:
    """Fichiers à sauvegarder présents dans `base`."""
    return sorted(f for f in Path(base).iterdir() if f.is_file() and _allowed(f.name))


def make_backup(dest: Path, base: Optional[Path] = None) -> Path:
    base = Path(base or core.BASE_DIR)
    files = backup_files(base)
    if not any(f.name == CONFIG_NAME for f in files):
        raise ValueError("aucun réglage à sauvegarder (l'outil n'a encore rien enregistré)")
    dest = Path(dest)
    with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr(META, json.dumps({"version": core.app_version(), "date": time.strftime("%Y-%m-%d %H:%M"),
                                     "files": [f.name for f in files]}, ensure_ascii=False))
        for f in files:
            z.write(f, f.name)
    return dest


def read_backup(path: Path) -> dict:
    """Vérifie une sauvegarde : {"version", "date", "files", "profiles"}. ValueError si invalide."""
    try:
        with zipfile.ZipFile(path) as z:
            names = [n for n in z.namelist() if _allowed(n)]
            if CONFIG_NAME not in names:
                raise ValueError("ce fichier n'est pas une sauvegarde de Dofus Price Helper")
            data = json.loads(z.read(CONFIG_NAME).decode("utf-8")) or {}
            try:
                meta = json.loads(z.read(META).decode("utf-8"))
            except (KeyError, ValueError):
                meta = {}
    except zipfile.BadZipFile:
        raise ValueError("fichier abîmé ou pas au format zip")
    except (OSError, UnicodeDecodeError) as e:
        raise ValueError(f"lecture impossible ({e})")
    if not isinstance(data, dict):
        raise ValueError("réglages illisibles dans la sauvegarde")
    profiles = set((data.get("PROFILES") or {}).keys()) | {data.get("PROFILE") or core.DEFAULT_PROFILE}
    return {"version": meta.get("version", "?"), "date": meta.get("date", "?"), "files": names,
            "profiles": sorted(str(p) for p in profiles)}


def restore_backup(path: Path, base: Optional[Path] = None) -> Path:
    """Restaure la sauvegarde dans `base`. Les fichiers actuels sont d'abord gardés dans
    `base/sauvegardes/avant_restauration_….zip` (retourné)."""
    base = Path(base or core.BASE_DIR)
    info = read_backup(path)                       # ValueError si ce n'est pas une sauvegarde
    keep_dir = base / SAFETY_DIR
    keep_dir.mkdir(exist_ok=True)
    keep = keep_dir / f"avant_restauration_{time.strftime('%Y%m%d_%H%M%S')}.zip"
    with zipfile.ZipFile(keep, "w", zipfile.ZIP_DEFLATED) as z:
        for f in backup_files(base):
            z.write(f, f.name)
    with zipfile.ZipFile(path) as z:
        for name in info["files"]:
            target = base / name
            tmp = target.with_suffix(target.suffix + ".tmp")
            tmp.write_bytes(z.read(name))
            tmp.replace(target)
    return keep
