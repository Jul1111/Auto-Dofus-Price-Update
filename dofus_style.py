#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Apparence de l'interface : palette, thème CustomTkinter et effet « verre » (Windows).

Le verre floute ce qui est derrière la fenêtre (le jeu) avec une teinte sombre réglable.
Il passe par SetWindowCompositionAttribute (Windows 10 1803+ et Windows 11) : contrairement
au fond « Acrylic » système de Windows 11, il reste flouté quand l'outil n'a pas le focus,
c'est-à-dire pendant que tu joues. Les pixels noirs de la fenêtre deviennent du verre ; les
couleurs sombres restent translucides, les couleurs vives (texte, boutons) restent nettes.
"""
from __future__ import annotations

import sys

# ------------------------------------------------------------------ palette (thème sombre)
P = {
    "bg": "#101216",          # fond de la fenêtre
    "card": "#181b21",        # cartes / sections
    "card2": "#20242b",       # éléments dans une carte (champs, lignes)
    "border": "#2a2f38",      # bordure fine des cartes
    "text": "#e8eaed",
    "muted": "#8b929c",
    "accent": "#5b7cfa",      # actions principales
    "accent_hover": "#4a69e3",
    "gold": "#f2b134",        # kamas, chiffres importants
    "green": "#3ecf8e",
    "orange": "#f0a03c",
    "red": "#f0616d",
    "cyan": "#5ccfe6",
    "violet": "#b392f0",
    "btn2": "#272b33",        # boutons secondaires
    "btn2_hover": "#323743",
    "input": "#13161b",
    "log_bg": "#0c0e11",
}
GLASS_BG = "#000000"          # noir = verre (laisse voir le flou)
FONT = "Segoe UI" if sys.platform == "win32" else "Roboto"
MONO = "Consolas" if sys.platform == "win32" else "Courier"

# pastilles de la barre d'état : (fond, texte)
CHIP = {
    "green": ("#143326", "#3ecf8e"),
    "orange": ("#3a2b12", "#f0a03c"),
    "red": ("#3d1b21", "#f0616d"),
    "grey": ("#22262d", "#aab1bb"),
}


def apply_theme(ctk) -> None:
    """Remplace les couleurs par défaut de CustomTkinter (avant de créer les widgets)."""
    ctk.set_appearance_mode("dark")
    ctk.set_default_color_theme("blue")
    t = ctk.ThemeManager.theme

    def s(widget: str, **kw):
        for k, v in kw.items():
            t[widget][k] = [v, v] if isinstance(v, str) and v != "transparent" else v

    s("CTk", fg_color=P["bg"])
    s("CTkToplevel", fg_color=P["bg"])
    s("CTkFrame", fg_color=P["card"], top_fg_color=P["card2"], border_color=P["border"], corner_radius=10)
    s("CTkButton", fg_color=P["accent"], hover_color=P["accent_hover"], text_color="#ffffff",
      border_color=P["border"], corner_radius=8)
    s("CTkLabel", text_color=P["text"])
    s("CTkEntry", fg_color=P["input"], border_color=P["border"], text_color=P["text"], border_width=1,
      corner_radius=8)
    s("CTkCheckBox", fg_color=P["accent"], hover_color=P["accent_hover"], border_color="#4a505b",
      text_color=P["text"], border_width=2)
    s("CTkSwitch", fg_color="#3a404b", progress_color=P["accent"], button_color="#e8eaed",
      button_hover_color="#ffffff", text_color=P["text"])
    s("CTkSlider", fg_color="#3a404b", progress_color=P["accent"], button_color="#e8eaed",
      button_hover_color="#ffffff")
    s("CTkOptionMenu", fg_color=P["btn2"], button_color=P["btn2_hover"], button_hover_color="#3d4350",
      text_color=P["text"], corner_radius=8)
    s("CTkSegmentedButton", fg_color=P["btn2"], selected_color=P["accent"], selected_hover_color=P["accent_hover"],
      unselected_color=P["btn2"], unselected_hover_color=P["btn2_hover"], text_color=P["text"], corner_radius=8)
    s("CTkScrollbar", button_color="#3a404b", button_hover_color="#4a515e")
    s("CTkTextbox", fg_color=P["log_bg"], border_color=P["border"], text_color=P["text"],
      scrollbar_button_color="#3a404b", scrollbar_button_hover_color="#4a515e")
    s("DropdownMenu", fg_color=P["card2"], hover_color=P["btn2_hover"], text_color=P["text"])
    t["CTkFont"] = {"family": FONT, "size": 13, "weight": "normal"}


# ------------------------------------------------------------------ effet verre
def glass_supported() -> bool:
    """Flou « acrylic » par composition : Windows 10 1803 (build 17134) et plus récent."""
    if sys.platform != "win32":
        return False
    try:
        return sys.getwindowsversion().build >= 17134
    except AttributeError:
        return False


def tint_color(opacity: float, rgb=(0x10, 0x12, 0x16)) -> int:
    """Teinte du verre au format attendu par Windows (0xAABBGGRR). opacity : 0..1."""
    a = max(0, min(255, round(opacity * 255)))
    r, g, b = rgb
    return (a << 24) | (b << 16) | (g << 8) | r


def _hwnd(window) -> int:
    import ctypes
    window.update_idletasks()
    return ctypes.windll.user32.GetParent(window.winfo_id())


def set_glass(window, on: bool, opacity: float = 0.6) -> bool:
    """Active / coupe le flou derrière `window` (fenêtre Tk). True si Windows l'a accepté."""
    if not glass_supported():
        return False
    import ctypes
    from ctypes import POINTER, Structure, byref, sizeof, wintypes

    class ACCENT_POLICY(Structure):
        _fields_ = [("AccentState", wintypes.DWORD), ("AccentFlags", wintypes.DWORD),
                    ("GradientColor", wintypes.DWORD), ("AnimationId", wintypes.DWORD)]

    class WINCOMPATTRDATA(Structure):
        _fields_ = [("Attribute", wintypes.DWORD), ("Data", POINTER(ACCENT_POLICY)),
                    ("SizeOfData", wintypes.ULONG)]

    ACCENT_DISABLED, ACCENT_ENABLE_ACRYLICBLURBEHIND, WCA_ACCENT_POLICY = 0, 4, 19
    try:
        hwnd = _hwnd(window)
        policy = ACCENT_POLICY(ACCENT_ENABLE_ACRYLICBLURBEHIND if on else ACCENT_DISABLED, 2,
                               tint_color(opacity) if on else 0, 0)
        data = WINCOMPATTRDATA(WCA_ACCENT_POLICY, ctypes.pointer(policy), sizeof(policy))
        return bool(ctypes.windll.user32.SetWindowCompositionAttribute(hwnd, byref(data)))
    except Exception:
        return False
