#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Nom de l'objet (panneau de gauche de l'HDV)
-------------------------------------------
Lu par Tesseract (lettres) pour l'historique et le tableau de bord. La lecture se fait
en ARRIÈRE-PLAN (après l'action) : elle ne ralentit jamais la vente.

Fiabilité :
- deux lectures à deux échelles ; on garde celle qui ressemble à un nom déjà connu ;
- les noms proches (« Nagcoire » / « Nageoire ») sont ramenés au nom connu le plus
  fréquent (difflib, ratio >= 0.85) ;
- la ligne « NIV. 26 » sous le nom est retirée ;
- même image de nom que la fois précédente -> même nom, sans relire.
"""
from __future__ import annotations

import difflib
import re
import threading
import unicodedata
from collections import Counter
from typing import Dict, Iterable, List, Optional

import numpy as np

SNAP_RATIO = 0.85
_LEVEL_LINE = re.compile(r"^\s*N\s*[IlI1|]\s*[VvY]\b", re.IGNORECASE)
_KEEP = re.compile(r"[^A-Za-zÀ-ÖØ-öø-ÿŒœ0-9' \-]")


def clean_name(text: str) -> str:
    """Texte OCR -> nom propre (lignes jointes, niveau retiré, caractères parasites ôtés)."""
    lines = []
    for ln in (text or "").splitlines():
        ln = ln.strip()
        if not ln or _LEVEL_LINE.match(ln):
            continue
        lines.append(ln)
    name = " ".join(lines)
    name = _KEEP.sub("", name.replace("’", "'"))
    name = re.sub(r"\s+", " ", name).strip(" -'")
    return name if len(name) >= 3 and any(c.isalpha() for c in name) else ""


def key(name: str) -> str:
    """Clé de regroupement : sans accents, minuscules, espaces simples."""
    s = unicodedata.normalize("NFKD", name)
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", s.casefold()).strip()


def similarity(a: str, b: str) -> float:
    """Ressemblance de deux clés. Une seule lettre différente sur un nom court (« cuivre » /
    « cuivrc ») compte comme proche : difflib seul est trop sévère sur 6 lettres."""
    if a == b:
        return 1.0
    if len(a) == len(b) and len(a) >= 5 and sum(x != y for x, y in zip(a, b)) == 1:
        return max(SNAP_RATIO, difflib.SequenceMatcher(None, a, b).ratio())
    return difflib.SequenceMatcher(None, a, b).ratio()


class NameBook:
    """Noms déjà vus (avec leur fréquence) pour corriger les petites erreurs de lecture."""

    def __init__(self, names: Iterable[str] = ()):
        self._lock = threading.Lock()
        self.counts: Counter = Counter()
        for n in names:
            if n:
                self.counts[n] += 1

    def snap(self, name: str) -> Optional[str]:
        """Nom connu le plus proche (ratio >= SNAP_RATIO), le plus fréquent en cas d'égalité."""
        if not name:
            return None
        k = key(name)
        best, best_r = None, 0.0
        with self._lock:
            for known, cnt in self.counts.most_common():
                r = similarity(k, key(known))
                if r > best_r + 1e-9:
                    best, best_r = known, r
        return best if best_r >= SNAP_RATIO else None

    def add(self, name: str) -> None:
        if name:
            with self._lock:
                self.counts[name] += 1

    def canonical(self, name: str) -> str:
        snapped = self.snap(name)
        return snapped or name


def group_names(names: Iterable[str]) -> Dict[str, str]:
    """{nom lu: nom retenu} : les variantes proches sont regroupées sous la plus fréquente."""
    counts = Counter(n for n in names if n)
    canon: Dict[str, str] = {}
    reps: List[str] = []
    for n, _ in counts.most_common():
        k = key(n)
        target = next((r for r in reps if similarity(k, key(r)) >= SNAP_RATIO), None)
        if target is None:
            reps.append(n)
            target = n
        canon[n] = target
    return canon


class NameReader:
    def __init__(self, book: Optional[NameBook] = None, lang: Optional[str] = None):
        self.book = book or NameBook()
        self._lang = lang
        self._last: Optional[tuple] = None  # (image, nom)
        self._lock = threading.Lock()

    def lang(self) -> str:
        if self._lang is None:
            try:
                import pytesseract
                langs = set(pytesseract.get_languages(config=""))
                self._lang = "fra" if "fra" in langs else "eng"
            except Exception:
                self._lang = "eng"
        return self._lang

    @staticmethod
    def _prep(img_bgr: np.ndarray, scale: int) -> np.ndarray:
        import cv2
        g = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY) if img_bgr.ndim == 3 else img_bgr
        up = cv2.resize(g, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
        # Niveaux de gris inversés, SANS binarisation : Tesseract lit mieux les lettres
        # anticrénelées (« Nageoire » et pas « Nagcoire »).
        if up.mean() < 127:
            up = 255 - up
        return cv2.copyMakeBorder(up, 10, 10, 10, 10, cv2.BORDER_CONSTANT, value=255)

    def read(self, img_bgr: Optional[np.ndarray]) -> str:
        if img_bgr is None or img_bgr.size == 0:
            return ""
        with self._lock:
            if self._last is not None and self._last[0].shape == img_bgr.shape \
                    and np.array_equal(self._last[0], img_bgr):
                return self._last[1]
        import pytesseract

        def ocr(scale: int) -> str:
            try:
                return clean_name(pytesseract.image_to_string(self._prep(img_bgr, scale), lang=self.lang(),
                                                              config="--psm 6"))
            except Exception:
                return ""

        reads = [n for n in (ocr(3), ocr(4)) if n]
        if len(reads) == 2 and key(reads[0]) != key(reads[1]):
            extra = ocr(2)                                     # désaccord : 3e lecture, vote
            if extra:
                reads.append(extra)
        name = ""
        if reads:
            snapped = [self.book.snap(n) for n in reads]
            if any(snapped):
                name = Counter(s for s in snapped if s).most_common(1)[0][0]   # nom déjà connu
            else:
                name = Counter(reads).most_common(1)[0][0]                     # vote
            self.book.add(name)
        with self._lock:
            self._last = (img_bgr.copy(), name)
        return name
