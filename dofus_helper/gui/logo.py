#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Logo de l'outil : une pièce d'or (clin d'œil aux kamas) avec une étiquette de prix gravée et
une flèche vers le bas (« juste sous le moins cher »). Dessin original, généré par le code :
aucune image du jeu n'est utilisée.

Sert à l'icône de la fenêtre, de la zone de notification, de l'en-tête et du .exe.
"""
from __future__ import annotations

import math
from functools import lru_cache

# couleurs de la pièce
RIM_DARK = (150, 88, 6)
RIM = (236, 170, 30)
RIM_LIGHT = (255, 214, 92)
FACE_IN = (255, 220, 96)      # centre de la face (lumière)
FACE_OUT = (226, 152, 20)     # bord de la face
ENGRAVE = (168, 96, 4)        # gravure (étiquette, flèche)
ENGRAVE_LIGHT = (255, 236, 160)


def _mix(a, b, t):
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


def _radial(draw, cx, cy, r, inner, outer, steps=90, shift=(0.0, 0.0)):
    """Disque en dégradé radial (lumière décalée vers `shift`, en fraction de r)."""
    for i in range(steps, 0, -1):
        t = i / steps
        rr = r * t
        ox, oy = shift[0] * r * (1 - t), shift[1] * r * (1 - t)
        draw.ellipse((cx - rr + ox, cy - rr + oy, cx + rr + ox, cy + rr + oy), fill=_mix(inner, outer, t))


def _tag_polygon(cx, cy, s, angle=-45):
    """Étiquette de prix (rectangle + pointe) centrée en (cx, cy), taille s, tournée."""
    w, h = 1.0 * s, 0.56 * s
    pts = [(-w / 2, -h / 2), (w / 2 - h / 2, -h / 2), (w / 2, 0), (w / 2 - h / 2, h / 2), (-w / 2, h / 2)]
    a = math.radians(angle)
    return [(cx + x * math.cos(a) - y * math.sin(a), cy + x * math.sin(a) + y * math.cos(a)) for x, y in pts]


@lru_cache(maxsize=16)
def logo_image(size: int = 256, glow: bool = False):
    """Le logo en image PIL RGBA (carré de `size` px). glow : halo doré autour (grandes tailles)."""
    from PIL import Image, ImageDraw, ImageFilter
    S = 4 * max(size, 64)                       # dessiné en grand puis réduit (bords lisses)
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    c = S / 2
    R = S * (0.40 if glow else 0.48)
    if glow:
        halo = Image.new("RGBA", (S, S), (0, 0, 0, 0))
        hd = ImageDraw.Draw(halo)
        hd.ellipse((c - R * 1.18, c - R * 1.18, c + R * 1.18, c + R * 1.18), fill=(255, 190, 40, 170))
        img = Image.alpha_composite(img, halo.filter(ImageFilter.GaussianBlur(S * 0.06)))
    coin = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(coin)
    # tranche + bord
    d.ellipse((c - R, c - R, c + R, c + R), fill=RIM_DARK)
    _radial(d, c, c - R * 0.02, R * 0.965, RIM_LIGHT, RIM, steps=60, shift=(-0.35, -0.45))
    # deux reflets sur le bord (haut-droite, bas-gauche)
    for start in (300, 120):
        d.arc((c - R * 0.9, c - R * 0.9, c + R * 0.9, c + R * 0.9), start, start + 28,
              fill=(255, 246, 190), width=max(2, int(R * 0.07)))
    # face, un peu creusée
    rf = R * 0.76
    d.ellipse((c - rf - R * 0.03, c - rf - R * 0.03, c + rf + R * 0.03, c + rf + R * 0.03), fill=RIM_DARK)
    _radial(d, c, c, rf, FACE_IN, FACE_OUT, steps=80, shift=(-0.4, -0.5))
    # étiquette de prix gravée : ombre claire décalée puis gravure
    s = R * 1.0
    tx, ty = c - R * 0.04, c - R * 0.06
    off = R * 0.025
    d.polygon(_tag_polygon(tx + off, ty + off, s), fill=ENGRAVE_LIGHT)
    d.polygon(_tag_polygon(tx, ty, s), fill=ENGRAVE)
    # trou de l'étiquette
    hx, hy = _tag_polygon(tx, ty, s)[2]
    hx, hy = tx + (hx - tx) * 0.62, ty + (hy - ty) * 0.62
    hr = R * 0.075
    d.ellipse((hx - hr, hy - hr, hx + hr, hy + hr), fill=FACE_IN)
    # flèche vers le bas dans l'étiquette (le prix descend juste sous le moins cher)
    ax, ay, aw = tx - R * 0.12, ty + R * 0.10, R * 0.16
    d.rectangle((ax - aw * 0.32, ay - aw * 1.35, ax + aw * 0.32, ay + aw * 0.05), fill=FACE_IN)
    d.polygon([(ax - aw, ay - aw * 0.15), (ax + aw, ay - aw * 0.15), (ax, ay + aw * 0.95)], fill=FACE_IN)
    img = Image.alpha_composite(img, coin)
    return img.resize((size, size), Image.LANCZOS)


def logo_with_dot(color: str, size: int = 64, ring: str = None):
    """Logo + pastille d'état en bas à droite (icône de la zone de notification).
    ring : couleur d'un anneau autour de la pièce (couleur du profil actif)."""
    from PIL import Image, ImageDraw
    if ring:
        img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        w = max(2, round(size * 0.10))
        d.ellipse((0, 0, size - 1, size - 1), fill=ring)
        inner = size - 2 * w
        img.alpha_composite(logo_image(inner), (w, w))
    else:
        img = logo_image(size).copy()
    d = ImageDraw.Draw(img)
    dr = size * 0.19
    x1, y1 = size - 1, size - 1
    d.ellipse((x1 - 2 * dr, y1 - 2 * dr, x1, y1), fill=color, outline=(24, 27, 33), width=max(1, size // 20))
    return img


def write_ico(path) -> None:
    """Fichier .ico multi-tailles (fenêtres, .exe)."""
    sizes = [16, 24, 32, 48, 64, 128, 256]
    logo_image(256).save(path, format="ICO", sizes=[(n, n) for n in sizes])


if __name__ == "__main__":       # aperçu : python dofus_logo.py  -> logo.png, logo_halo.png, logo.ico
    logo_image(512).save("logo.png")
    logo_image(512, glow=True).save("logo_halo.png")
    write_ico("logo.ico")
