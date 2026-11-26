#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Lecture rapide des chiffres Dofus (sans Tesseract)
--------------------------------------------------
La police du jeu ne change pas : chaque chiffre est une tache noire (image binarisée
par dofus_core.preprocess) que l'on compare à des modèles 0-9.

Les modèles sont APPRIS sur l'écran de l'utilisateur : quand Tesseract lit un nombre avec
une très bonne confiance, chaque chiffre est découpé et enregistré (digit_templates.npz).
Dès que les 10 chiffres sont connus, la lecture rapide remplace Tesseract ; au moindre
chiffre douteux, on revient à Tesseract pour cette lecture.

`read_data()` renvoie un dict au format pytesseract.image_to_data, pour réutiliser
parse_table / parse_number tels quels.
"""
from __future__ import annotations

import threading
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np

NORM_H, NORM_W = 24, 20          # taille normalisée d'un chiffre
MIN_SCORE = 0.80                 # corrélation mini pour accepter un chiffre
MIN_MARGIN = 0.04                # écart mini avec le 2e meilleur chiffre
LEARN_CONF = 90.0                # confiance Tesseract mini pour apprendre
MIN_SAMPLES = 2                  # échantillons par chiffre avant usage
MAX_SAMPLES = 12

Box = Tuple[int, int, int, int]  # x, y, w, h


def normalize(glyph: np.ndarray) -> np.ndarray:
    """Tache (1 = encre) -> image NORM_H×NORM_W, hauteur normalisée, proportions gardées
    (un « 1 » reste étroit), centrée, valeurs centrées-réduites pour la corrélation."""
    import cv2
    h, w = glyph.shape
    nw = max(1, min(NORM_W, int(round(w * NORM_H / max(1, h)))))
    g = cv2.resize(glyph.astype(np.float32), (nw, NORM_H), interpolation=cv2.INTER_AREA)
    out = np.zeros((NORM_H, NORM_W), np.float32)
    x = (NORM_W - nw) // 2
    out[:, x:x + nw] = g
    out -= out.mean()
    n = np.linalg.norm(out)
    return out / n if n > 0 else out


def components(binary: np.ndarray) -> List[Box]:
    """Taches d'encre (texte noir sur fond blanc) -> boîtes."""
    import cv2
    ink = (binary < 128).astype(np.uint8)
    n, _, stats, _ = cv2.connectedComponentsWithStats(ink, connectivity=8)
    return [tuple(int(v) for v in stats[k, :4]) for k in range(1, n)]


class DigitReader:
    def __init__(self, path: Optional[Path] = None):
        self.path = path
        self.samples: Dict[int, List[np.ndarray]] = {d: [] for d in range(10)}
        # formes à ignorer apprises (flèche du menu Quantité, coin de cadre, reste d'icône)
        self.noise: List[np.ndarray] = []
        self._lock = threading.Lock()
        self._dirty = 0
        self.load()

    # ------------------------------------------------------------ modèles
    @property
    def ready(self) -> bool:
        return all(len(v) >= MIN_SAMPLES for v in self.samples.values())

    def known(self) -> List[int]:
        return [d for d, v in self.samples.items() if len(v) >= MIN_SAMPLES]

    def load(self) -> None:
        if not self.path or not self.path.exists():
            return
        try:
            with np.load(self.path) as data:   # fermé tout de suite : sinon save() échoue (Windows)
                for d in range(10):
                    key = f"d{d}"
                    if key in data:
                        self.samples[d] = [s for s in data[key]][:MAX_SAMPLES]
                if "noise" in data:
                    self.noise = [s for s in data["noise"]][:4 * MAX_SAMPLES]
        except Exception as e:  # fichier abîmé : on réapprend
            print(f"[Chiffres] Modèles illisibles ({e}), réapprentissage.")
            return
        if self.purge():
            self.save()

    # Un modèle mal étiqueté (Tesseract a lu « 8 » un 5 qu'on a appris comme 8) fait lire
    # TOUS les 5 en 8 : 4725 devient 4728, et Ctrl+F3 croit la modification ratée.
    def _sims(self, v: np.ndarray, digit: int, skip: Optional[np.ndarray] = None) -> Tuple[float, float]:
        """(ressemblance max à son chiffre, ressemblance max aux autres chiffres)."""
        own = max((float((v * s).sum()) for s in self.samples[digit] if s is not skip), default=-1.0)
        other = max((float((v * s).sum()) for d, lst in self.samples.items() if d != digit for s in lst),
                    default=-1.0)
        return own, other

    def purge(self) -> int:
        """Retire les modèles qui ressemblent plus à un AUTRE chiffre qu'au leur, le pire
        d'abord (un faux 8 qui est un 5 rend aussi les vrais 5 « suspects » : on recalcule)."""
        removed = 0
        with self._lock:
            while True:
                worst, gap = None, 0.0
                for d in range(10):
                    if len(self.samples[d]) < 2:
                        continue
                    for i, s in enumerate(self.samples[d]):
                        own, other = self._sims(s, d, skip=s)
                        if other - own > gap:
                            worst, gap = (d, i), other - own
                if worst is None:
                    break
                self.samples[worst[0]].pop(worst[1])
                removed += 1
        if removed:
            print(f"[Chiffres] {removed} modèle(s) mal appris retiré(s).")
        return removed

    def save(self) -> None:
        if not self.path:
            return
        with self._lock:
            arrays = {f"d{d}": np.array(v, np.float32) for d, v in self.samples.items() if v}
            if self.noise:
                arrays["noise"] = np.array(self.noise, np.float32)
            self._dirty = 0
        try:
            tmp = self.path.with_name(self.path.stem + "_tmp.npz")
            np.savez_compressed(tmp, **arrays)
            tmp.replace(self.path)
        except OSError as e:
            print(f"[Chiffres] Sauvegarde impossible : {e}")

    def add(self, digit: int, glyph: np.ndarray, sure: bool = False) -> None:
        """sure=False (lecture Tesseract) : refusé s'il ressemble plus à un autre chiffre
        déjà appris (Tesseract s'est sans doute trompé)."""
        v = normalize(glyph)
        with self._lock:
            lst = self.samples[digit]
            if any(float((v * s).sum()) > 0.97 for s in lst):
                return  # déjà connu
            if not sure and lst:
                own, other = self._sims(v, digit)
                if other >= 0.75 and other > own + 0.02:
                    return
            lst.append(v)
            if len(lst) > MAX_SAMPLES:
                lst.pop(0)
            self._dirty += 1

    def correct(self, binary: np.ndarray, text: str) -> int:
        """Image d'UN nombre dont on connaît la vraie valeur `text` (champ « Prix du lot »
        qu'on vient de remplir, confirmé par Tesseract) alors que la lecture rapide s'est
        trompée : retire les modèles d'autres chiffres qui ont gagné, apprend les bons.
        Retourne le nombre de modèles retirés."""
        comps = [c for c in components(binary) if c[3] >= 8]
        if not comps:
            return 0
        text_h = float(np.median([c[3] for c in comps]))
        glyphs = sorted(c for c in comps if 0.8 * text_h <= c[3] <= 1.3 * text_h)
        if len(glyphs) != len(text) or not text.isdigit():
            return 0
        removed = 0
        for (x, y, w, h), t in zip(glyphs, text):
            g = binary[y:y + h, x:x + w] < 128
            v = normalize(g)
            t = int(t)
            with self._lock:
                own = max((float((v * s).sum()) for s in self.samples[t]), default=-1.0)
                for d in range(10):
                    if d == t:
                        continue
                    keep = [s for s in self.samples[d] if float((v * s).sum()) < max(own, MIN_SCORE)]
                    removed += len(self.samples[d]) - len(keep)
                    self.samples[d] = keep
            self.add(t, g, sure=True)
        if removed:
            self._dirty += 1
            self.save()
        return removed

    # ------------------------------------------------------- apprentissage
    def reset(self) -> None:
        with self._lock:
            self.samples = {d: [] for d in range(10)}
            self.noise = []
            self._dirty = 1
        self.save()

    def add_noise(self, glyph: np.ndarray) -> None:
        v = normalize(glyph)
        with self._lock:
            if any(float((v * s).sum()) > 0.97 for s in self.noise):
                return
            if any(float((v * s).sum()) > 0.75 for lst in self.samples.values() for s in lst):
                return  # ressemble à un chiffre : jamais ignoré
            self.noise.append(v)
            if len(self.noise) > 4 * MAX_SAMPLES:
                self.noise.pop(0)
            self._dirty += 1

    def learn(self, binary: np.ndarray, data: Dict[str, list],
              bounds: Optional[List[Tuple[int, int]]] = None) -> int:
        """Apprend depuis un résultat Tesseract sur la MÊME image binaire.
        Un mot n'est utilisé que si sa confiance est très bonne et que le nombre de
        taches dans sa boîte = nombre de chiffres lus (pas de chiffres collés)."""
        comps = components(binary)
        added = 0
        for i, txt in enumerate(data["text"]):
            txt = str(txt).strip()
            if not txt or not txt.isdigit() or float(data["conf"][i]) < LEARN_CONF:
                continue
            x, y, w, h = (int(data[k][i]) for k in ("left", "top", "width", "height"))
            inside = [c for c in comps
                      if c[0] >= x - 2 and c[0] + c[2] <= x + w + 2
                      and c[1] >= y - 3 and c[1] + c[3] <= y + h + 3 and c[3] >= 0.5 * h]
            if len(inside) != len(txt):
                continue
            for (cx, cy, cw, ch), d in zip(sorted(inside), txt):
                glyph = binary[cy:cy + ch, cx:cx + cw] < 128
                self.add(int(d), glyph)
                added += 1
        # Taches de hauteur « chiffre » hors de tout mot que Tesseract a lu avec une
        # confiance correcte (>= 60) : ce ne sont pas des chiffres -> bruit connu.
        # Une tache qui ressemble à un chiffre appris n'est jamais classée bruit (add_noise).
        words = [i for i, t in enumerate(data["text"])
                 if str(t).strip() and float(data["conf"][i]) >= 60]
        if len(words) >= 3:
            boxes = [tuple(int(data[k][i]) for k in ("left", "top", "width", "height")) for i in words]
            for y0, y1 in (bounds or [(0, binary.shape[0])]):
                seg = [c for c in comps if y0 <= c[1] + c[3] / 2 < y1]
                tall = [c for c in seg if c[3] >= 8]
                if not tall:
                    continue
                text_h = float(np.median([c[3] for c in tall]))
                for (cx, cy, cw, ch) in seg:
                    if not 0.8 * text_h <= ch <= 1.3 * text_h:
                        continue
                    if any(cx + cw > x - 3 and cx < x + w + 3 and cy + ch > y - 3 and cy < y + h + 3
                           for x, y, w, h in boxes):
                        continue
                    self.add_noise(binary[cy:cy + ch, cx:cx + cw] < 128)
        if self._dirty >= 5:
            self.save()
        return added

    # ------------------------------------------------------------ lecture
    def classify(self, glyph: np.ndarray) -> Tuple[Optional[int], float]:
        """-> (chiffre, score) ; (-1, score) = bruit connu ; (None, score) = inconnu."""
        v = normalize(glyph)
        with self._lock:
            noise = max((float((v * s).sum()) for s in self.noise), default=-1.0)
        scores = []
        with self._lock:
            for d, lst in self.samples.items():
                if lst:
                    scores.append((max(float((v * s).sum()) for s in lst), d))
        if not scores:
            return None, 0.0
        scores.sort(reverse=True)
        best, d = scores[0]
        second = scores[1][0] if len(scores) > 1 else -1.0
        if noise >= 0.9 and noise > best + MIN_MARGIN:
            return -1, noise
        if best < MIN_SCORE or best - second < MIN_MARGIN:
            return None, best
        return d, best

    def split_classify(self, glyph: np.ndarray, text_h: float,
                       depth: int = 0) -> Optional[List[Tuple[int, float]]]:
        """Chiffres COLLÉS (ex. « 77 » sur le prix surligné) : essaie les coupes aux
        colonnes les moins encrées (hors bords), garde la plus sûre. None si pas sûr."""
        h, w = glyph.shape
        if depth > 2 or w < 0.75 * text_h:
            return None
        ink = glyph.sum(axis=0)
        lo, hi = int(w * 0.25), int(w * 0.75)
        if hi <= lo:
            return None
        m = int(ink[lo:hi].min())
        best = None
        for cut in range(lo, hi + 1):
            if ink[min(cut, w - 1)] > m + 1 and ink[cut - 1] > m + 1:
                continue
            res = []
            for part in (glyph[:, :cut], glyph[:, cut:]):
                cols = np.where(part.any(axis=0))[0]
                rows = np.where(part.any(axis=1))[0]
                if len(cols) == 0 or rows[-1] - rows[0] + 1 < 0.8 * text_h:
                    res = None
                    break
                part = part[rows[0]:rows[-1] + 1, cols[0]:cols[-1] + 1]
                d, sc = self.classify(part)
                if d is None or d == -1:
                    sub = self.split_classify(part, text_h, depth + 1)
                    if sub is None:
                        res = None
                        break
                    res.extend(sub)
                else:
                    res.append((d, sc))
            if res and (best is None or min(x[1] for x in res) > min(x[1] for x in best)):
                best = res
        return best

    def read_data(self, binary: np.ndarray,
                  bounds: Optional[List[Tuple[int, int]]] = None) -> Optional[Dict[str, list]]:
        """Image binaire (comme pour Tesseract) -> dict format image_to_data, ou None si
        un chiffre n'est pas reconnu de façon sûre (-> Tesseract).
        `bounds` = bandes verticales de l'image composite (tableau, quantité…) : la taille
        du texte est estimée par bande."""
        if not self.ready:
            return None
        comps = components(binary)
        out = _empty()
        segs = bounds or [(0, binary.shape[0])]
        line_no = 0
        for y0, y1 in segs:
            seg = [c for c in comps if y0 <= c[1] + c[3] / 2 < y1]
            tall = [c for c in seg if c[3] >= 8]
            if not tall:
                continue
            text_h = float(np.median([c[3] for c in tall]))
            # Les chiffres Dofus ont tous la même hauteur. Plus petit = reste d'icône,
            # flèche, séparateur : ignoré. Une tache de bonne hauteur non reconnue
            # (chiffres collés…) -> Tesseract.
            glyphs = [c for c in seg if 0.8 * text_h <= c[3] <= 1.3 * text_h]
            glyphs.sort(key=lambda c: (c[1] + c[3] / 2, c[0]))
            lines: List[List[Box]] = []
            for c in glyphs:
                cy = c[1] + c[3] / 2
                if lines and abs(cy - _center(lines[-1])) <= 0.5 * text_h:
                    lines[-1].append(c)
                else:
                    lines.append([c])
            for line in lines:
                line_no += 1
                if not self._read_line(binary, sorted(line), text_h, line_no, out):
                    return None
        return out

    def _read_line(self, binary, line: List[Box], text_h: float, ln: int, out) -> bool:
        words: List[List[Box]] = [[line[0]]]
        for c in line[1:]:
            prev = words[-1][-1]
            if c[0] - (prev[0] + prev[2]) > 0.45 * text_h:  # « 1 499 » ou colonne suivante
                words.append([c])
            else:
                words[-1].append(c)
        for wn, word in enumerate(words, start=1):
            digits, scores = [], []
            for (x, y, w, h) in word:
                glyph = binary[y:y + h, x:x + w] < 128
                d, s = self.classify(glyph)
                if d is None:
                    split = self.split_classify(glyph, text_h)
                    if split is None:
                        return False      # inconnu : Tesseract
                    digits.extend(str(dd) for dd, _ in split)
                    scores.extend(sc for _, sc in split)
                    continue
                if d == -1:
                    if len(word) > 1:
                        return False      # bruit collé à des chiffres : prudence
                    break                 # bruit connu isolé : ignoré
                digits.append(str(d))
                scores.append(s)
            if not digits:
                continue
            x0 = min(c[0] for c in word)
            y0 = min(c[1] for c in word)
            x1 = max(c[0] + c[2] for c in word)
            y1 = max(c[1] + c[3] for c in word)
            out["text"].append("".join(digits))
            out["left"].append(x0)
            out["top"].append(y0)
            out["width"].append(x1 - x0)
            out["height"].append(y1 - y0)
            out["conf"].append(round(100 * min(scores), 1))
            out["block_num"].append(1)
            out["par_num"].append(1)
            out["line_num"].append(ln)
            out["word_num"].append(wn)
        return True


def _center(line: List[Box]) -> float:
    return float(np.mean([c[1] + c[3] / 2 for c in line]))


def _empty() -> Dict[str, list]:
    return {k: [] for k in ("text", "left", "top", "width", "height", "conf",
                            "block_num", "par_num", "line_num", "word_num")}
