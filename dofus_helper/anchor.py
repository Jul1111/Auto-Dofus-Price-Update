"""Repère HDV et profils : les zones suivent la fenêtre de l'Hôtel de vente."""
from __future__ import annotations

import re
from pathlib import Path
from typing import TYPE_CHECKING, Dict, List, Optional, Tuple

import numpy as np

from .base import ANCHOR_PATH
from .ocr import BORDER, grab_screen, preprocess

if TYPE_CHECKING:
    from .base import Point, Region
    from .config import Config


# --------------------------------------------------------------------------
# Repère HDV : les zones suivent la fenêtre de l'Hôtel de vente
# --------------------------------------------------------------------------
ANCHOR_OK = 0.90      # score au même endroit : pas bougé
ANCHOR_FOUND = 0.80   # score mini pour accepter une nouvelle position
REGION_FIELDS = ("table_region", "qty_region", "avg_region", "count_region", "mine_region", "anchor_region",
                 "name_region")
POINT_FIELDS = ("price_field", "sell_button", "modify_button", "relist_row")
PROFILE_FIELDS = REGION_FIELDS + POINT_FIELDS + ("relist_step", "calib_window")   # ce que contient un profil
DEFAULT_PROFILE = "Principal"


def profile_name_problem(name: str, existing: List[str]) -> Optional[str]:
    """Pourquoi `name` ne peut pas être un nouveau profil (None = accepté)."""
    if not name:
        return "donne un nom au profil"
    if len(name) > 30:
        return "nom trop long (30 caractères au plus)"
    if any(name.casefold() == n.casefold() for n in existing):
        return f"le profil « {name} » existe déjà"
    return None


def anchor_path(cfg: "Config", profile: Optional[str] = None) -> Path:
    """Image du repère « Hôtel de vente » du profil (hdv_anchor.png pour « Principal »)."""
    name = profile or cfg.profile
    if name == DEFAULT_PROFILE:
        return ANCHOR_PATH
    import hashlib
    slug = re.sub(r"[^A-Za-z0-9_-]+", "_", name).strip("_")[:20] or "profil"
    return ANCHOR_PATH.with_name(f"hdv_anchor_{slug}_{hashlib.sha1(name.encode()).hexdigest()[:6]}.png")


def save_anchor(img_bgr: np.ndarray, path: Optional[Path] = None) -> None:
    import cv2
    cv2.imwrite(str(path or ANCHOR_PATH), img_bgr)


_anchor_cache: Dict[str, Tuple[float, np.ndarray]] = {}


def load_anchor(path: Optional[Path] = None) -> Optional[np.ndarray]:
    import cv2
    p = Path(path or ANCHOR_PATH)
    if not p.exists():
        return None
    mt = p.stat().st_mtime
    cached = _anchor_cache.get(str(p))
    if cached and cached[0] == mt:
        return cached[1]
    img = cv2.imread(str(p))
    if img is not None:
        _anchor_cache[str(p)] = (mt, img)
    return img


def _gray(img: np.ndarray) -> np.ndarray:
    import cv2
    return cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) if img.ndim == 3 else img


def anchor_score(img: np.ndarray, tpl: np.ndarray) -> float:
    import cv2
    a, t = _gray(img), _gray(tpl)
    if a.shape != t.shape or a.size == 0:
        return 0.0
    return float(cv2.matchTemplate(a, t, cv2.TM_CCOEFF_NORMED)[0, 0])


def screen_bounds() -> Region:
    """Rectangle de TOUS les écrans (peut commencer en négatif)."""
    import mss
    with mss.mss() as sct:
        m = sct.monitors[0]
        return m["left"], m["top"], m["width"], m["height"]


def find_anchor(tpl: np.ndarray) -> Optional[Point]:
    """Cherche le titre de l'HDV sur tout l'écran : d'abord en demi-résolution (rapide),
    puis précisément autour du meilleur endroit. Retourne le coin haut-gauche ou None."""
    import cv2
    sx, sy, sw, sh = screen_bounds()
    full = _gray(grab_screen((sx, sy, sw, sh)))
    t = _gray(tpl)
    th, tw = t.shape
    if th >= full.shape[0] or tw >= full.shape[1]:
        return None
    small = cv2.resize(full, None, fx=0.5, fy=0.5, interpolation=cv2.INTER_AREA)
    ts = cv2.resize(t, None, fx=0.5, fy=0.5, interpolation=cv2.INTER_AREA)
    _, best, _, loc = cv2.minMaxLoc(cv2.matchTemplate(small, ts, cv2.TM_CCOEFF_NORMED))
    if best < ANCHOR_FOUND - 0.1:
        # image très détaillée : la demi-résolution la brouille -> recherche pleine résolution
        _, best, _, loc = cv2.minMaxLoc(cv2.matchTemplate(full, t, cv2.TM_CCOEFF_NORMED))
        if best < ANCHOR_FOUND:
            return None
        return sx + loc[0], sy + loc[1]
    cx, cy = loc[0] * 2, loc[1] * 2
    x0, y0 = max(0, cx - 6), max(0, cy - 6)
    win = full[y0:y0 + th + 12, x0:x0 + tw + 12]
    if win.shape[0] < th or win.shape[1] < tw:
        return None
    _, best, _, loc = cv2.minMaxLoc(cv2.matchTemplate(win, t, cv2.TM_CCOEFF_NORMED))
    if best < ANCHOR_FOUND:
        return None
    return sx + x0 + loc[0], sy + y0 + loc[1]


def shift_zones(cfg: "Config", dx: int, dy: int) -> None:
    for f in REGION_FIELDS:
        r = getattr(cfg, f)
        if r:
            setattr(cfg, f, [r[0] + dx, r[1] + dy, r[2], r[3]])
    for f in POINT_FIELDS:
        p = getattr(cfg, f)
        if p:
            setattr(cfg, f, [p[0] + dx, p[1] + dy])


def zone_hint(name: str, region) -> Optional[str]:
    """Conseil si une zone calibrée semble mal taillée (trop serrée = chiffres coupés)."""
    x, y, w, h = region
    if name in ("qty", "avg", "count", "mine") and h < 18:
        return f"zone haute de {h} px seulement : les chiffres risquent d'être coupés, ajoute de la marge en haut et en bas"
    if name in ("avg", "count") and w < 40:
        return f"zone large de {w} px seulement : prends tout le nombre avec de la marge"
    if name == "count" and w < 70:
        return "prends toute la ligne « 21/100 lots en vente »"
    if name == "anchor" and (w < 80 or h < 14):
        return "prends tout le titre « Hôtel de vente » (et un peu de la barre autour)"
    if name == "table" and h < 60:
        return "le tableau doit couvrir les 4 lignes (lot 1 à lot 1000)"
    return None


CUT_CHECK_ZONES = ("qty", "avg", "count")   # petites zones de texte : un chiffre coupé y est fréquent


def text_touches_edge(img_bgr: np.ndarray, scale: int = 2) -> bool:
    """Du texte touche le HAUT ou le BAS de la zone : chiffres probablement coupés (zone trop
    serrée ou décalée). La lecture peut alors réussir par chance… ou échouer plus tard."""
    import cv2
    th = preprocess(img_bgr, scale)[BORDER:-BORDER, BORDER:-BORDER]
    ink = (th < 128).astype(np.uint8)
    n, _, stats, _ = cv2.connectedComponentsWithStats(ink, connectivity=8)
    for k in range(1, n):
        x, y, w, h, area = (int(v) for v in stats[k])
        if area < 4 * scale * scale or w > 16 * scale or h < 3 * scale:
            continue  # poussière, traits du cadre
        if y == 0 or y + h >= ink.shape[0]:
            return True
    return False


def cut_text_hint(name: str, region) -> Optional[str]:
    """Conseil si le texte de la zone calibrée touche son bord (capture de l'écran, ~1 ms)."""
    if name not in CUT_CHECK_ZONES or not region:
        return None
    try:
        cut = text_touches_edge(grab_screen(tuple(region)))
    except Exception:
        return None
    if cut:
        return ("le texte touche le bord haut ou bas de la zone (chiffre coupé ?) : recalibre en "
                "laissant 3-4 px de marge au-dessus et en dessous")
    return None


def rect_from_points(p1: Point, p2: Point) -> Region:
    x1, x2 = sorted((p1[0], p2[0]))
    y1, y2 = sorted((p1[1], p2[1]))
    return x1, y1, max(1, x2 - x1), max(1, y2 - y1)

