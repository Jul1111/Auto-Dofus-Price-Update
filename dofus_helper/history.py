"""Historique des prix (CSV)."""
from __future__ import annotations

import csv
import os
import threading
import time
from pathlib import Path
from typing import TYPE_CHECKING, Optional

import numpy as np

from .base import HISTORY_HEADER, HISTORY_PATH
from .ocr import grab_screen

if TYPE_CHECKING:
    from .base import Region
    from .ocr import Reading
    from .config import Config


# --------------------------------------------------------------------------
# Historique
# --------------------------------------------------------------------------
_hist_lock = threading.Lock()


def name_region_for(cfg: Config) -> Optional[Region]:
    """Zone du nom de l'objet : calibrée, sinon au-dessus du champ « Prix du lot »
    (même place pour tous les objets dans le panneau de gauche)."""
    if cfg.name_region:
        return tuple(cfg.name_region)
    if cfg.price_field:
        x, y = cfg.price_field
        return (x - 12, y - 104, 175, 48)
    return None


def grab_name(cfg: Config) -> Optional[np.ndarray]:
    """Image du nom de l'objet (~1 ms) : sert d'empreinte pour reconnaître l'objet (item_key)."""
    region = name_region_for(cfg)
    if region is None:
        return None
    try:
        img = grab_screen(region)
        return img.copy() if img is not None and img.size else None
    except Exception:
        return None


def _history_row(ts: float, action, lot, selected, reading, new_price, status, cfg: Config, item: str):
    return [int(ts), time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(ts)),
            action, lot if lot else "", selected if selected else "",
            reading.value if reading and reading.value is not None else "",
            f"{reading.confidence:.0f}" if reading else "",
            new_price if new_price is not None else "",
            status, cfg.undercut_mode, cfg.undercut_value, cfg.rounding, item]


def _write_history(row: list, path: Path) -> None:
    with _hist_lock:
        try:
            if path.exists():
                # en-tête seul : relire tout le fichier à chaque ligne ralentissait avec l'historique
                with path.open("r", encoding="utf-8", newline="") as f:
                    header = next(csv.reader(f), None)
                if header == HISTORY_HEADER[:-1]:
                    # ancien format sans « item » : on ajoute la colonne, rien n'est perdu
                    with path.open("r", encoding="utf-8", newline="") as f:
                        rows = list(csv.reader(f))
                    tmp = path.with_suffix(".tmp")
                    with tmp.open("w", encoding="utf-8", newline="") as f:
                        w = csv.writer(f)
                        w.writerow(HISTORY_HEADER)
                        w.writerows(r + [""] for r in rows[1:])
                    os.replace(tmp, path)
                elif header != HISTORY_HEADER:  # format inconnu -> archivé
                    path.replace(path.with_name(path.stem + f"_old_{int(time.time())}.csv"))
            new_file = not path.exists()
            with path.open("a", encoding="utf-8", newline="") as f:
                w = csv.writer(f)
                if new_file:
                    w.writerow(HISTORY_HEADER)
                w.writerow(row)
        except OSError as e:
            print(f"[Historique] Écriture impossible: {e}")


def log_history(action: str, lot: Optional[int], selected: Optional[int],
                reading: Optional[Reading], new_price: Optional[int],
                status: str, cfg: Config, path: Optional[Path] = None) -> None:
    """Une ligne d'historique (colonne « item » laissée vide : gardée pour la compatibilité)."""
    _write_history(_history_row(time.time(), action, lot, selected, reading, new_price, status, cfg, ""),
                   path or HISTORY_PATH)

