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

# ------------------------------------------------------------------ palettes
DARK = {
    "bg": "#101216",          # fond de la fenêtre
    "card": "#181b21",        # cartes / sections
    "card2": "#20242b",       # éléments dans une carte (champs, lignes)
    "border": "#2a2f38",      # bordure fine des cartes
    "text": "#e8eaed",
    "muted": "#8b929c",
    "accent": "#5b7cfa",      # actions principales (remplacé par la couleur d'accent choisie)
    "accent_hover": "#4a69e3",
    "on_accent": "#ffffff",   # texte sur un bouton d'accent
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
    "log_time": "#5f6670",
    "log_info": "#b8bec7",
    "track": "#3a404b",       # rail des interrupteurs / curseurs, barres de défilement
    "track_hover": "#4a515e",
    "knob": "#e8eaed",
    "knob_hover": "#ffffff",
    "check_border": "#4a505b",
    "menu_hover": "#3d4350",
    "red_hover": "#5a2730",   # survol des boutons « danger » (fond CHIP rouge)
    "green_hover": "#1c4535",
    "popup_head": "#ffffff",  # titre des popups / bandeau
}
LIGHT = {
    "bg": "#f2f3f6",
    "card": "#ffffff",
    "card2": "#eef0f4",
    "border": "#d8dce3",
    "text": "#1b1f26",
    "muted": "#5f6773",
    "accent": "#5b7cfa",
    "accent_hover": "#4a69e3",
    "on_accent": "#ffffff",
    "gold": "#a36a00",
    "green": "#14885a",
    "orange": "#b46300",
    "red": "#cc2c3b",
    "cyan": "#0e7a93",
    "violet": "#7346cc",
    "btn2": "#e4e7ec",
    "btn2_hover": "#d6dae1",
    "input": "#ffffff",
    "log_bg": "#fafbfc",
    "log_time": "#9aa1ab",
    "log_info": "#3c434d",
    "track": "#c3c8d1",
    "track_hover": "#b2b8c3",
    "knob": "#ffffff",
    "knob_hover": "#f4f5f7",
    "check_border": "#9aa1ad",
    "menu_hover": "#c9ced7",
    "red_hover": "#f4c4c9",
    "green_hover": "#bfe8d4",
    "popup_head": "#1b1f26",
}
# couleur d'accent au choix : clé -> (libellé, couleur, survol). Texte blanc lisible sur chacune.
ACCENTS = {
    "blue": ("Bleu", "#5b7cfa", "#4a69e3"),
    "violet": ("Violet", "#7c5ce6", "#6a4bd3"),
    "green": ("Vert", "#258a5e", "#1f7650"),
    "amber": ("Ambre", "#b86e0e", "#a1600b"),
    "pink": ("Rose", "#c94482", "#b33872"),
    "cyan": ("Cyan", "#16819a", "#126f85"),
}
THEMES = {"dark": "Sombre", "light": "Clair", "system": "Comme Windows"}
# ambiances du thème sombre : fonds, cartes, bordures et rails teintés (texte et couleurs vives inchangés)
AMBIENCES = {
    "night": ("Nuit", {}),
    "amber": ("Ambre", {"bg": "#15110c", "card": "#1e1812", "card2": "#272017", "border": "#3a2f22",
                        "input": "#181309", "log_bg": "#100c08", "btn2": "#2e261b", "btn2_hover": "#3a3022",
                        "track": "#4a3d2c", "track_hover": "#5a4a36", "menu_hover": "#44392a",
                        "check_border": "#5c4d3a", "log_time": "#74685a"}),
    "forest": ("Forêt", {"bg": "#0d1411", "card": "#141d18", "card2": "#1b2620", "border": "#26362d",
                         "input": "#0f1713", "log_bg": "#0a100d", "btn2": "#212d26", "btn2_hover": "#2a3a31",
                         "track": "#34463b", "track_hover": "#415649", "menu_hover": "#364a3e",
                         "check_border": "#4a5f52", "log_time": "#5c6e63"}),
    "ocean": ("Océan", {"bg": "#0b1219", "card": "#111b25", "card2": "#17232f", "border": "#22313f",
                        "input": "#0d1620", "log_bg": "#080e14", "btn2": "#1c2a37", "btn2_hover": "#253545",
                        "track": "#2f4255", "track_hover": "#3b5167", "menu_hover": "#32475c",
                        "check_border": "#475d72", "log_time": "#5b6c7c"}),
}
# couleur par profil (multi-compte) : vives, avec du texte sombre dessus, lisibles dans les 2 thèmes
PROFILE_COLORS = {"blue": ("Bleu", "#6b8cff"), "green": ("Vert", "#3ecf8e"), "gold": ("Or", "#f2b134"),
                  "red": ("Rouge", "#f0616d"), "violet": ("Violet", "#b392f0"), "cyan": ("Cyan", "#5ccfe6"),
                  "pink": ("Rose", "#f08cc0"), "orange": ("Orange", "#f0a03c")}
ON_PROFILE = "#101216"         # texte sur une couleur de profil


def profile_color(name: str, chosen: dict) -> str:
    """Couleur du profil : celle choisie, sinon une couleur stable déduite du nom."""
    import zlib
    key = chosen.get(name)
    if key not in PROFILE_COLORS:
        keys = list(PROFILE_COLORS)
        key = keys[zlib.crc32(name.encode("utf-8")) % len(keys)]
    return PROFILE_COLORS[key][1]

# pastilles de la barre d'état : (fond, texte)
CHIP_DARK = {
    "green": ("#143326", "#3ecf8e"),
    "orange": ("#3a2b12", "#f0a03c"),
    "red": ("#3d1b21", "#f0616d"),
    "grey": ("#22262d", "#aab1bb"),
}
CHIP_LIGHT = {
    "green": ("#d8f3e6", "#0f6e47"),
    "orange": ("#fbe9cf", "#8a4f00"),
    "red": ("#fadadd", "#b01f2e"),
    "grey": ("#e6e8ed", "#4b525c"),
}

P = dict(DARK)                # palette ACTIVE (modifiée en place par configure)
CHIP = dict(CHIP_DARK)
CURRENT = {"theme": "dark", "accent": "blue", "ambience": "night"}
GLASS_BG = "#000000"          # noir = verre (laisse voir le flou)
FONT = "Segoe UI" if sys.platform == "win32" else "Roboto"
MONO = "Consolas" if sys.platform == "win32" else "Courier"


def windows_light_theme() -> bool:
    """Windows est-il réglé en mode clair pour les applications ? (False hors Windows)."""
    if sys.platform != "win32":
        return False
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                            r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize") as k:
            return bool(winreg.QueryValueEx(k, "AppsUseLightTheme")[0])
    except OSError:
        return False


def resolve_theme(theme: str) -> str:
    """« system » -> « light » ou « dark » selon Windows ; valeur inconnue -> « dark »."""
    if theme == "system":
        return "light" if windows_light_theme() else "dark"
    return theme if theme in ("dark", "light") else "dark"


def palette(theme: str = "dark", accent: str = "blue", ambience: str = "night") -> dict:
    """Palette complète pour ce thème, cet accent et cette ambiance (sans rien changer : sert à l'aperçu).
    L'ambiance ne s'applique qu'au thème sombre."""
    dark = resolve_theme(theme) != "light"
    pal = dict(DARK if dark else LIGHT)
    if dark:
        pal.update(AMBIENCES.get(ambience, AMBIENCES["night"])[1])
    _, pal["accent"], pal["accent_hover"] = ACCENTS.get(accent, ACCENTS["blue"])
    return pal


def chips(theme: str = "dark") -> dict:
    return dict(CHIP_LIGHT if resolve_theme(theme) == "light" else CHIP_DARK)


def configure(theme: str = "dark", accent: str = "blue", ambience: str = "night") -> None:
    """Choisit la palette ACTIVE (avant de créer les widgets et avant apply_theme)."""
    P.clear()
    P.update(palette(theme, accent, ambience))
    CHIP.clear()
    CHIP.update(chips(theme))
    CURRENT.update(theme=resolve_theme(theme), accent=accent if accent in ACCENTS else "blue",
                   ambience=ambience if ambience in AMBIENCES else "night")


def is_dark() -> bool:
    return CURRENT["theme"] == "dark"


def saved_look(path) -> tuple:
    """(thème, accent) enregistrés dans la config, lus avant la création de l'interface."""
    import json
    try:
        with open(path, encoding="utf-8") as f:
            data = json.loads(f.read()) or {}
    except (OSError, ValueError):
        data = {}
    theme, accent = data.get("THEME", "dark"), data.get("ACCENT", "blue")
    return (theme if theme in THEMES else "dark", accent if accent in ACCENTS else "blue")


def saved_ambience(path) -> str:
    """Ambiance enregistrée dans la config (« night » par défaut)."""
    import json
    try:
        with open(path, encoding="utf-8") as f:
            data = json.loads(f.read()) or {}
    except (OSError, ValueError):
        data = {}
    amb = data.get("AMBIENCE", "night")
    return amb if amb in AMBIENCES else "night"


def apply_theme(ctk) -> None:
    """Remplace les couleurs par défaut de CustomTkinter (avant de créer les widgets)."""
    ctk.set_appearance_mode("dark" if is_dark() else "light")
    ctk.set_default_color_theme("blue")
    t = ctk.ThemeManager.theme

    def s(widget: str, **kw):
        for k, v in kw.items():
            t[widget][k] = [v, v] if isinstance(v, str) and v != "transparent" else v

    s("CTk", fg_color=P["bg"])
    s("CTkToplevel", fg_color=P["bg"])
    s("CTkFrame", fg_color=P["card"], top_fg_color=P["card2"], border_color=P["border"], corner_radius=10)
    s("CTkButton", fg_color=P["accent"], hover_color=P["accent_hover"], text_color=P["on_accent"],
      border_color=P["border"], corner_radius=8)
    s("CTkLabel", text_color=P["text"])
    s("CTkEntry", fg_color=P["input"], border_color=P["border"], text_color=P["text"], border_width=1,
      corner_radius=8)
    s("CTkCheckBox", fg_color=P["accent"], hover_color=P["accent_hover"], border_color=P["check_border"],
      text_color=P["text"], border_width=2, checkmark_color=P["on_accent"])
    s("CTkSwitch", fg_color=P["track"], progress_color=P["accent"], button_color=P["knob"],
      button_hover_color=P["knob_hover"], text_color=P["text"])
    s("CTkSlider", fg_color=P["track"], progress_color=P["accent"], button_color=P["knob"],
      button_hover_color=P["knob_hover"])
    s("CTkProgressBar", fg_color=P["track"], progress_color=P["accent"], border_color=P["border"])
    s("CTkOptionMenu", fg_color=P["btn2"], button_color=P["btn2_hover"], button_hover_color=P["menu_hover"],
      text_color=P["text"], corner_radius=8)
    s("CTkSegmentedButton", fg_color=P["btn2"], selected_color=P["accent"], selected_hover_color=P["accent_hover"],
      unselected_color=P["btn2"], unselected_hover_color=P["btn2_hover"], text_color=P["text"], corner_radius=8)
    s("CTkScrollbar", button_color=P["track"], button_hover_color=P["track_hover"])
    s("CTkTextbox", fg_color=P["log_bg"], border_color=P["border"], text_color=P["text"],
      scrollbar_button_color=P["track"], scrollbar_button_hover_color=P["track_hover"])
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


def set_click_through(window, on: bool, activate: bool = True) -> bool:
    """Les clics traversent la fenêtre (HUD par-dessus le jeu). Windows seulement.
    on=False, activate=False : cliquable, mais un clic ne lui donne pas le focus (le jeu le garde)."""
    if sys.platform != "win32":
        return False
    import ctypes
    GWL_EXSTYLE, WS_EX_LAYERED, WS_EX_TRANSPARENT, WS_EX_NOACTIVATE = -20, 0x80000, 0x20, 0x08000000
    try:
        user32 = ctypes.windll.user32
        hwnd = _hwnd(window)
        ex = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
        flags = WS_EX_LAYERED | WS_EX_TRANSPARENT | WS_EX_NOACTIVATE
        if on:
            ex |= flags
        elif activate:
            ex &= ~(WS_EX_TRANSPARENT | WS_EX_NOACTIVATE)
        else:
            ex = (ex & ~WS_EX_TRANSPARENT) | WS_EX_LAYERED | WS_EX_NOACTIVATE
        user32.SetWindowLongW(hwnd, GWL_EXSTYLE, ex)
        return True
    except Exception:
        return False


def colorref(color: str) -> int:
    """#rrggbb -> COLORREF Windows (0x00BBGGRR)."""
    c = color.lstrip("#")
    r, g, b = int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16)
    return (b << 16) | (g << 8) | r


def set_titlebar(window, caption: str, text: str, border: str) -> bool:
    """Barre de titre et bordure de la fenêtre aux couleurs du thème, coins arrondis.
    Windows 11 seulement (build 22000+) ; ailleurs, rien ne change."""
    if sys.platform != "win32":
        return False
    try:
        if sys.getwindowsversion().build < 22000:
            return False
        import ctypes
        from ctypes import byref, c_int, sizeof
        hwnd = _hwnd(window)
        dwm = ctypes.windll.dwmapi
        ok = True
        for attr, value in ((33, 2),                                  # DWMWA_WINDOW_CORNER_PREFERENCE : arrondi
                            (34, colorref(border)), (35, colorref(caption)), (36, colorref(text))):
            v = c_int(value)
            ok = dwm.DwmSetWindowAttribute(hwnd, attr, byref(v), sizeof(v)) == 0 and ok
        return ok
    except Exception:
        return False


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


# ------------------------------------------------------------------ micro-animations
def ease_out(t: float) -> float:
    """Courbe douce : rapide au début, lente à la fin (0 -> 0, 1 -> 1)."""
    t = max(0.0, min(1.0, t))
    return 1 - (1 - t) ** 3


def _rgb(widget, color: str) -> tuple:
    r, g, b = widget.winfo_rgb(color)
    return r // 257, g // 257, b // 257


def blend(widget, a: str, b: str, t: float) -> str:
    """Couleur entre a et b (noms Tk ou #rrggbb acceptés)."""
    ca, cb = _rgb(widget, a), _rgb(widget, b)
    return "#" + "".join(f"{round(x + (y - x) * t):02x}" for x, y in zip(ca, cb))


def smooth_hover(ctk, enabled, ms: int = 120) -> None:
    """Survol des boutons CustomTkinter en fondu (au lieu d'un changement sec de couleur).
    Le clic garde son petit effet « enfoncé ». enabled() : option Animations."""
    B = ctk.CTkButton
    if getattr(B, "_smooth_hover", False):
        return
    enter0, leave0 = B._on_enter, B._on_leave
    steps = max(1, ms // 16)

    def paint(btn, color):
        btn._canvas.itemconfig("inner_parts", outline=color, fill=color)
        for lab in (btn._text_label, btn._image_label):
            if lab is not None:
                lab.configure(bg=color)

    def current(btn):
        items = btn._canvas.find_withtag("inner_parts")
        return btn._canvas.itemcget(items[0], "fill") if items else None

    def run(btn, target, final):
        start = current(btn)
        if not start or start == target:
            final()
            return
        token = object()
        btn._hover_tween = token

        def tick(i=1):
            try:
                if getattr(btn, "_hover_tween", None) is not token or not btn.winfo_exists():
                    return
                if i >= steps:
                    btn._hover_tween = None
                    final()
                    return
                paint(btn, blend(btn, start, target, ease_out(i / steps)))
                btn.after(16, lambda: tick(i + 1))
            except Exception:
                btn._hover_tween = None
        tick()

    def on_enter(self, event=None):
        if not enabled() or not (self._hover is True and self._state == "normal"):
            self._hover_tween = None
            return enter0(self, event)
        self._mouse_inside = True
        color = self._fg_color if self._hover_color is None else self._hover_color
        run(self, self._apply_appearance_mode(color), lambda: enter0(self))

    def on_leave(self, event=None):
        if not enabled():
            self._hover_tween = None
            return leave0(self, event)
        self._mouse_inside = False
        self._click_animation_running = False
        color = self._bg_color if self._fg_color == "transparent" else self._fg_color
        run(self, self._apply_appearance_mode(color), lambda: leave0(self))

    B._on_enter, B._on_leave, B._smooth_hover = on_enter, on_leave, True


# ------------------------------------------------------------------ fondus (popups, bandeau)
def fade_steps(start: float, end: float, ms: int, step_ms: int = 16) -> list:
    """Valeurs d'opacité successives pour un fondu de `ms` millisecondes (dernière = end)."""
    n = max(1, round(ms / step_ms))
    return [round(start + (end - start) * (i / n) ** 0.8, 3) for i in range(1, n + 1)]


def fade(window, start: float, end: float, ms: int = 140, then=None) -> None:
    """Fondu de l'opacité d'une fenêtre Tk (Windows), puis `then()` (ex. destroy)."""
    steps = fade_steps(start, end, ms)

    def tick(i=0):
        try:
            if not window.winfo_exists():
                return
            window.attributes("-alpha", steps[i])
        except Exception:
            return
        if i + 1 < len(steps):
            window.after(16, lambda: tick(i + 1))
        elif then is not None:
            then()
    try:
        window.attributes("-alpha", start)
    except Exception:
        if then is not None:
            then()
        return
    tick()
