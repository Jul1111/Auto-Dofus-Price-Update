#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Icônes de l'interface, dessinées par le code (PIL) dans un style unique : trait fin et arrondi,
une seule couleur. Elles remplacent les emojis (✨ ■ 📌 💾…), dont le rendu change d'un PC à
l'autre et ne suit pas les couleurs du thème.

Chaque icône est dessinée sur une grille de 24 × 24, en grand puis réduite (bords lisses).
"""
from __future__ import annotations

import math
from functools import lru_cache

GRID = 24.0
SS = 4            # suréchantillonnage


def _rgba(color: str, alpha: int = 255) -> tuple:
    c = color.lstrip("#")
    return int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16), alpha


class _Pen:
    """Dessin en coordonnées de grille (0..24), trait arrondi d'épaisseur `w` (en unités de grille)."""

    def __init__(self, draw, px: int, color: tuple, w: float = 2.0):
        self.d, self.k, self.c, self.w = draw, px / GRID, color, w

    def p(self, x, y):
        return x * self.k, y * self.k

    def line(self, *pts, w=None):
        w = (w or self.w) * self.k
        xy = [self.p(x, y) for x, y in pts]
        self.d.line(xy, fill=self.c, width=max(1, round(w)), joint="curve")
        r = w / 2
        for x, y in xy:                          # extrémités arrondies
            self.d.ellipse((x - r, y - r, x + r, y + r), fill=self.c)

    def poly(self, *pts, fill=True, w=None):
        xy = [self.p(x, y) for x, y in pts]
        if fill:
            self.d.polygon(xy, fill=self.c)
        else:
            self.line(*(list(pts) + [pts[0]]), w=w)

    def rrect(self, x0, y0, x1, y1, r=2.5, fill=False, w=None):
        w = (w or self.w) * self.k
        box = (*self.p(x0, y0), *self.p(x1, y1))
        if fill:
            self.d.rounded_rectangle(box, radius=r * self.k, fill=self.c)
        else:
            self.d.rounded_rectangle(box, radius=r * self.k, outline=self.c, width=max(1, round(w)))

    def circle(self, cx, cy, r, fill=False, w=None):
        w = (w or self.w) * self.k
        box = (*self.p(cx - r, cy - r), *self.p(cx + r, cy + r))
        if fill:
            self.d.ellipse(box, fill=self.c)
        else:
            self.d.ellipse(box, outline=self.c, width=max(1, round(w)))

    def arc(self, cx, cy, r, start, end, w=None):
        w = (w or self.w) * self.k
        box = (*self.p(cx - r, cy - r), *self.p(cx + r, cy + r))
        self.d.arc(box, start, end, fill=self.c, width=max(1, round(w)))
        rr = w / 2
        for a in (start, end):
            x, y = self.p(cx + r * math.cos(math.radians(a)), cy + r * math.sin(math.radians(a)))
            self.d.ellipse((x - rr, y - rr, x + rr, y + rr), fill=self.c)


def _star(cx, cy, r, inner=0.28):
    pts = []
    for i in range(8):
        a = math.radians(-90 + i * 45)
        rr = r if i % 2 == 0 else r * inner
        pts.append((cx + rr * math.cos(a), cy + rr * math.sin(a)))
    return pts


def _rot(pts, cx, cy, deg):
    a = math.radians(deg)
    return [(cx + (x - cx) * math.cos(a) - (y - cy) * math.sin(a),
             cy + (x - cx) * math.sin(a) + (y - cy) * math.cos(a)) for x, y in pts]


def _draw(name: str, pen: _Pen) -> None:
    if name == "spark":                          # calibration automatique
        pen.poly(*_star(10, 13, 8.5))
        pen.poly(*_star(18.5, 5.5, 4))
    elif name == "stop":
        pen.rrect(6, 6, 18, 18, r=2.5, fill=True)
    elif name == "play":
        pen.poly((7.5, 5), (19, 12), (7.5, 19))
    elif name == "pin":                          # punaise : toujours au-dessus
        body = [(9, 3.5), (15, 3.5), (14, 5), (14, 10), (17.5, 13.5), (6.5, 13.5), (10, 10), (10, 5)]
        pen.poly(*_rot(body, 12, 12, 35))
        a, b = _rot([(12, 13.5), (12, 21)], 12, 12, 35)
        pen.line(a, b)
    elif name == "copy":
        pen.rrect(8.5, 8.5, 20, 20, r=2.5)
        pen.line((5, 15), (4.5, 15), (4, 14.5), (4, 5.5), (5.5, 4), (14.5, 4), (15, 4.5), (15, 5))
    elif name == "trash":
        pen.line((4, 6.5), (20, 6.5))
        pen.line((9.5, 6.5), (9.5, 4), (14.5, 4), (14.5, 6.5))
        pen.line((6, 6.5), (7, 20), (17, 20), (18, 6.5))
        pen.line((10.2, 10.5), (10.5, 16.5), w=1.6)
        pen.line((13.8, 10.5), (13.5, 16.5), w=1.6)
    elif name == "save":
        pen.rrect(4, 4, 20, 20, r=2.5)
        pen.line((8, 4.5), (8, 9), (15, 9), (15, 4.5))
        pen.rrect(8, 13.5, 16, 19.5, r=1, w=1.8)
    elif name == "package":                      # rapport de problème
        pen.poly((12, 3), (20.5, 7.5), (20.5, 16.5), (12, 21), (3.5, 16.5), (3.5, 7.5), fill=False)
        pen.line((3.8, 7.6), (12, 12), (20.2, 7.6))
        pen.line((12, 12), (12, 20.5))
    elif name == "compass":
        pen.circle(12, 12, 9)
        pen.poly((15.5, 8.5), (13.2, 13.2), (8.5, 15.5), (10.8, 10.8))
    elif name == "refresh":
        pen.arc(12, 12, 7.5, 20, 290)
        a = math.radians(290)
        px, py = 12 + 7.5 * math.cos(a), 12 + 7.5 * math.sin(a)
        tx, ty = -math.sin(a), math.cos(a)          # sens de rotation
        nx, ny = math.cos(a), math.sin(a)
        pen.poly((px + 4 * tx, py + 4 * ty), (px + 3.4 * nx, py + 3.4 * ny), (px - 3.4 * nx, py - 3.4 * ny))
    elif name == "back":
        pen.line((19, 12), (5.5, 12))
        pen.line((11, 6.5), (5.5, 12), (11, 17.5))
    elif name == "close":
        pen.line((6.5, 6.5), (17.5, 17.5))
        pen.line((17.5, 6.5), (6.5, 17.5))
    elif name == "move":
        pen.line((12, 3.5), (12, 20.5))
        pen.line((3.5, 12), (20.5, 12))
        for (x, y), deg in (((12, 3), 0), ((21, 12), 90), ((12, 21), 180), ((3, 12), 270)):
            pen.poly(*_rot([(x - 3, y + 3.2), (x, y), (x + 3, y + 3.2)], x, y, deg))
    elif name == "eye":                          # voir les zones
        pen.arc(12, 21, 13.5, 222, 318)
        pen.arc(12, 3, 13.5, 42, 138)
        pen.circle(12, 12, 3, fill=True)
    elif name == "check":
        pen.line((5, 12.5), (10, 17.5), (19, 7), w=2.6)
    elif name == "circle":
        pen.circle(12, 12, 7.5)
    elif name == "warn":
        pen.poly((12, 3.5), (21, 19.5), (3, 19.5), fill=False, w=2.0)
        pen.line((12, 9.5), (12, 14))
        pen.circle(12, 16.9, 1.25, fill=True)
    elif name == "error":
        pen.circle(12, 12, 9)
        pen.line((8.8, 8.8), (15.2, 15.2))
        pen.line((15.2, 8.8), (8.8, 15.2))
    elif name == "tag":                          # vente
        pts = [(3.5, 12), (9, 5.5), (20.5, 5.5), (20.5, 18.5), (9, 18.5)]
        pen.poly(*pts, fill=False)
        pen.circle(9.5, 12, 1.6, fill=True)
    elif name == "edit":                         # mise à jour d'un prix
        body = [(5, 19), (5.6, 15.4), (15.4, 5.6), (18.4, 8.6), (8.6, 18.4)]
        pen.poly(*body, fill=False)
        pen.line((13.2, 7.8), (16.2, 10.8))
    elif name == "target":                       # calibration
        pen.circle(12, 12, 8.5)
        pen.circle(12, 12, 3.2, fill=True)
        for a, b in (((12, 1.5), (12, 5)), ((12, 19), (12, 22.5)), ((1.5, 12), (5, 12)), ((19, 12), (22.5, 12))):
            pen.line(a, b)
    elif name == "dot":
        pen.circle(12, 12, 2.6, fill=True)
    elif name == "info":
        pen.circle(12, 12, 9)
        pen.line((12, 11), (12, 16.5))
        pen.circle(12, 7.6, 1.25, fill=True)
    else:
        raise KeyError(name)


NAMES = ("spark", "stop", "play", "pin", "copy", "trash", "save", "package", "compass", "refresh", "back",
         "close", "move", "eye", "check", "circle", "warn", "error", "tag", "edit", "target", "dot", "info")


@lru_cache(maxsize=256)
def icon_image(name: str, color: str, size: int = 16):
    """L'icône `name` en image PIL RGBA de `size` px (× 2 pour les écrans à grande échelle)."""
    from PIL import Image, ImageDraw
    out = size * 2
    big = out * SS
    img = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    _draw(name, _Pen(ImageDraw.Draw(img), big, _rgba(color)))
    return img.resize((out, out), Image.LANCZOS)


_CTK_CACHE: dict = {}


def ctk_icon(name: str, color: str, size: int = 16):
    """CTkImage prête à poser sur un bouton ou un label (mise en cache)."""
    key = (name, color, size)
    if key not in _CTK_CACHE:
        import customtkinter as ctk
        img = icon_image(name, color, size)
        _CTK_CACHE[key] = ctk.CTkImage(light_image=img, dark_image=img, size=(size, size))
    return _CTK_CACHE[key]
