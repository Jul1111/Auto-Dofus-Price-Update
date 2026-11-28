"""Calibration automatique : trouve l'Hôtel de vente à l'écran et en déduit toutes les zones.

L'HDV s'agrandit ou rapetisse d'un bloc (résolution, échelle de l'interface) : un modèle
mesuré une fois (modele_hdv/, voir packaging/build_hdv_model.py) suffit.
1. le bandeau du haut (titre + onglets) est cherché à plusieurs tailles -> position et échelle ;
2. chaque zone est placée à l'échelle, puis recalée sur le texte fixe le plus proche
   (« Prix du lot », « PRIX MOYEN »…) : le panneau de gauche peut glisser de quelques pixels ;
3. la hauteur des lignes de « mes ventes » est mesurée à l'écran.

Limite : le modèle vient de Dofus 3 en FRANÇAIS. Une autre langue ou une interface de l'HDV
modifiée par une mise à jour du jeu ne sera pas reconnue (calibration manuelle dans ce cas).
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np

from dofus_helper import core

MODEL_DIR = core.APP_DIR / "modele_hdv"
SCALES = (0.45, 2.2)          # tailles cherchées (1 = capture du modèle)
HEADER_MIN = 0.55             # score mini du bandeau du haut
LANDMARK_MIN = 0.55           # score mini d'un texte fixe
LANDMARKS_NEEDED = 3          # textes fixes à retrouver pour accepter (sur 6)

_model_cache: Dict[str, dict] = {}


def load_model(path: Path = MODEL_DIR) -> dict:
    """modele.json + images (niveaux de gris). Lève FileNotFoundError si absent."""
    import cv2
    key = str(path)
    if key in _model_cache:
        return _model_cache[key]
    model = json.loads((path / "modele.json").read_text(encoding="utf-8"))
    model["header"]["img"] = cv2.imread(str(path / model["header"]["file"]), cv2.IMREAD_GRAYSCALE)
    for lm in model["landmarks"].values():
        lm["img"] = cv2.imread(str(path / lm["file"]), cv2.IMREAD_GRAYSCALE)
    if model["header"]["img"] is None or any(lm["img"] is None for lm in model["landmarks"].values()):
        raise FileNotFoundError(f"modèle de l'HDV incomplet : {path}")
    _model_cache[key] = model
    return model


@dataclass
class AutoCal:
    ok: bool
    message: str
    scale: float = 0.0
    score: float = 0.0
    fields: Dict[str, list] = field(default_factory=dict)    # champs de Config à écrire
    found: List[str] = field(default_factory=list)            # textes fixes retrouvés
    missing: List[str] = field(default_factory=list)


def _resize(img: np.ndarray, s: float) -> np.ndarray:
    import cv2
    w, h = max(1, int(round(img.shape[1] * s))), max(1, int(round(img.shape[0] * s)))
    return cv2.resize(img, (w, h), interpolation=cv2.INTER_AREA if s < 1 else cv2.INTER_CUBIC)


def _match(img: np.ndarray, tpl: np.ndarray) -> Tuple[float, Tuple[int, int]]:
    import cv2
    if tpl.shape[0] > img.shape[0] or tpl.shape[1] > img.shape[1] or tpl.size == 0:
        return -1.0, (0, 0)
    _, v, _, loc = cv2.minMaxLoc(cv2.matchTemplate(img, tpl, cv2.TM_CCOEFF_NORMED))
    return float(v), loc


def find_header(screen: np.ndarray, model: dict) -> Optional[Tuple[float, float, float, float]]:
    """Bandeau du haut de l'HDV -> (x, y, échelle, score) dans `screen` (gris), ou None.
    Recherche grossière en demi-résolution sur toutes les tailles, puis fine autour."""
    tpl = model["header"]["img"]
    f = 0.5
    small = _resize(screen, f)
    best = (-1.0, 1.0, (0, 0))
    for s in np.geomspace(SCALES[0], SCALES[1], 80):
        t = _resize(tpl, s * f)
        if t.shape[1] < 24:
            continue
        v, loc = _match(small, t)
        if v > best[0]:
            best = (v, s, loc)
    if best[0] < HEADER_MIN - 0.15:
        return None
    _, s0, (lx, ly) = best
    cx, cy = lx / f, ly / f
    m = int(12 + 6 * s0)
    fine = (-1.0, s0, (0.0, 0.0))
    for s in s0 * np.linspace(0.97, 1.03, 49):
        t = _resize(tpl, s)
        x0, y0 = int(max(0, cx - m)), int(max(0, cy - m))
        win = screen[y0:int(cy + t.shape[0] + m), x0:int(cx + t.shape[1] + m)]
        v, loc = _match(win, t)
        if v > fine[0]:
            fine = (v, s, (x0 + loc[0], y0 + loc[1]))
    v, s, (x, y) = fine
    if v < HEADER_MIN:
        return None
    return float(x), float(y), float(s), float(v)


def find_landmarks(screen: np.ndarray, model: dict, ax: float, ay: float, s: float,
                   slack: float = 0.0) -> Dict[str, Tuple[float, float, float]]:
    """Texte fixe -> (écart x, écart y, score) entre la place prévue et la place réelle.
    `slack` élargit la recherche proportionnellement à la distance au titre (échelle incertaine)."""
    out = {}
    for name, lm in model["landmarks"].items():
        t = _resize(lm["img"], s)
        u, v = lm["at"]
        px, py = ax + u * s, ay + v * s
        mx = lm["search"][0] * s + 2 + slack * abs(u) * s
        my = lm["search"][1] * s + 2 + slack * abs(v) * s
        x0, y0 = int(max(0, px - mx)), int(max(0, py - my))
        win = screen[y0:int(py + t.shape[0] + my), x0:int(px + t.shape[1] + mx)]
        score, loc = _match(win, t)
        if score >= LANDMARK_MIN:
            out[name] = (x0 + loc[0] - px, y0 + loc[1] - py, score)
    return out


def fit_frame(screen: np.ndarray, model: dict, hx: float, hy: float, s0: float
              ) -> Tuple[float, float, float, Dict[str, Tuple[float, float, float]]]:
    """Le bandeau seul (peu haut) donne l'échelle à ~3 % près. Les textes fixes, répartis sur
    toute la hauteur de l'HDV, la donnent bien mieux : position du titre et échelle ajustées
    sur l'ensemble (moindres carrés), les textes aberrants écartés.
    -> (x du titre, y du titre, échelle, écarts restants des textes fixes)."""
    hu, hv = model["header"]["at"]
    ax, ay, s = hx - hu * s0, hy - hv * s0, s0
    slack = 0.05
    for _ in range(3):
        lms = find_landmarks(screen, model, ax, ay, s, slack)
        # points : (coordonnée modèle, coordonnée écran, axe) ; le bandeau compte aussi
        pts = [(hu, hx, 0), (hv, hy, 1)]
        for name, (dx, dy, _) in lms.items():
            u, v = model["landmarks"][name]["at"]
            if model["landmarks"][name]["search"][0] <= 20:     # x fiable (pas « lots en vente »)
                pts.append((u, ax + u * s + dx, 0))
            pts.append((v, ay + v * s + dy, 1))
        for _ in range(2):
            A = np.array([[1.0 - k, float(k), m] for m, _, k in pts])
            b = np.array([e for _, e, _ in pts])
            sol, *_ = np.linalg.lstsq(A, b, rcond=None)
            res = np.abs(A @ sol - b)
            keep = res <= max(3.0, 2.5 * float(np.median(res)))
            if keep.all() or keep.sum() < 4:
                break
            pts = [p for p, k in zip(pts, keep) if k]
        ax, ay, s = (float(v) for v in sol)
        slack = 0.01
    return ax, ay, s, find_landmarks(screen, model, ax, ay, s)


def measure_row_step(screen: np.ndarray, x: int, y: int, guess: float) -> Optional[float]:
    """Hauteur des lignes de « mes ventes » mesurée à l'écran (bords des lignes), autour de la
    1re ligne (x, y). None si la liste n'est pas lisible (vide, trop courte)."""
    top = int(y - guess)
    strip = screen[max(0, top):int(y + 9 * guess), max(0, x - 40):x + 40]
    if strip.shape[0] < 4 * guess or strip.shape[1] < 20:
        return None
    prof = np.median(strip, axis=1)
    is_row = prof > (float(prof.min()) + float(prof.max())) / 2
    starts = [i for i in range(1, len(is_row)) if is_row[i] and not is_row[i - 1]]
    diffs = [b - a for a, b in zip(starts, starts[1:]) if 0.8 * guess <= b - a <= 1.2 * guess]
    if len(diffs) < 3:
        return None
    # pas moyen sur toute la série (les lignes tombent sur des pixels entiers : 49, 50, 49…)
    good = [a for a, b in zip(starts, starts[1:]) if 0.8 * guess <= b - a <= 1.2 * guess]
    span = (good[-1] - good[0]) + diffs[-1]
    return span / len(diffs)


def locate(screen_bgr: np.ndarray, origin: Tuple[int, int] = (0, 0),
           model: Optional[dict] = None) -> AutoCal:
    """Calcule toutes les zones à partir d'une capture d'écran (`origin` = coin haut-gauche
    de la capture en coordonnées écran). Ne modifie rien."""
    model = model or load_model()
    screen = core._gray(screen_bgr)
    hdr = find_header(screen, model)
    if hdr is None:
        return AutoCal(False, "HDV introuvable à l'écran : ouvre l'Hôtel de vente sur l'onglet « Vente », "
                              "bien visible (rien par-dessus). Fonctionne avec Dofus 3 en français.")
    hx, hy, s, score = hdr
    ax, ay, s, lms = fit_frame(screen, model, hx, hy, s)     # (ax, ay) = repère (titre)
    missing = [n for n in model["landmarks"] if n not in lms]
    if len(lms) < LANDMARKS_NEEDED:
        return AutoCal(False, f"HDV reconnu (taille ×{s:.2f}) mais ses textes ne correspondent pas "
                              f"({len(lms)}/{len(model['landmarks'])} retrouvés). La calibration "
                              "automatique ne marche qu'avec la même version du jeu, en français, onglet "
                              "« Vente » avec un objet sélectionné. Sinon : calibration manuelle.",
                       s, score, found=list(lms), missing=missing)
    ox, oy = origin
    fields: Dict[str, list] = {}
    for name, z in model["zones"].items():
        v = z["value"]
        dx = lms.get(z["x"], (0, 0, 0))[0] if z["x"] else 0
        dy = lms.get(z["y"], (0, 0, 0))[1] if z["y"] else 0
        x = int(round(ax + v[0] * s + dx)) + ox
        y = int(round(ay + v[1] * s + dy)) + oy
        if len(v) == 4:
            fields[name] = [x, y, max(1, int(round(v[2] * s))), max(1, int(round(v[3] * s)))]
        else:
            fields[name] = [x, y]
    guess = model["row_step"] * s
    rx, ry = fields["relist_row"][0] - ox, fields["relist_row"][1] - oy
    step = measure_row_step(screen, rx, ry, guess) or guess
    fields["relist_step"] = int(round(step))
    msg = (f"HDV trouvé (taille ×{s:.2f} par rapport au modèle, {len(lms)}/{len(model['landmarks'])} "
           f"textes fixes retrouvés) : toutes les zones sont placées.")
    return AutoCal(True, msg, s, score, fields, found=list(lms), missing=missing)


def apply(cfg: "core.Config", res: AutoCal, screen_bgr: np.ndarray, origin: Tuple[int, int] = (0, 0)) -> None:
    """Écrit les zones dans le profil actif et enregistre l'image du repère à cette taille."""
    for name, value in res.fields.items():
        setattr(cfg, name, value)
    cfg.mine_region = None                 # ton prix : lu dans le champ « Prix du lot »
    cfg.click_field = True
    x, y, w, h = res.fields["anchor_region"]
    ox, oy = origin
    crop = screen_bgr[y - oy:y - oy + h, x - ox:x - ox + w]
    if crop.size:
        core.save_anchor(crop.copy(), core.anchor_path(cfg))
