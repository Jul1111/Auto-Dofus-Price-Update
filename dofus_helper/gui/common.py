"""Couleurs, libellés et petites fonctions communes à toute l'interface."""
from __future__ import annotations

from typing import Optional

from dofus_helper import core
from dofus_helper.gui import icons as dofus_icons
from dofus_helper.gui import style
from dofus_helper.gui.style import P

style.configure(*style.saved_look(core.CONFIG_PATH), style.saved_ambience(core.CONFIG_PATH))   # thème et accent : avant les couleurs ci-dessous

try:
    import keyboard
    KEYBOARD_AVAILABLE = True
except Exception:  # pas installé / pas les droits
    keyboard = None
    KEYBOARD_AVAILABLE = False

try:
    import pystray
    TRAY_AVAILABLE = True
except Exception:  # pas installé : pas d'icône dans la zone de notification
    pystray = None
    TRAY_AVAILABLE = False


TAG_COLORS = {
    "TIME": P["log_time"], "INFO": P["log_info"], "ERROR": P["red"], "WARN": P["orange"],
    "OK": P["green"], "OPT": P["violet"], "CAL": P["cyan"],
}
STALE_JOB_S = 1.5   # s : un raccourci de jeu qui a attendu plus longtemps dans la file est ignoré
LEVEL_COLORS = {"ok": P["green"], "warn": P["orange"], "error": P["red"]}
ZONE_COLORS = {"table": "#66d9ef", "qty": "#ae81ff", "avg": "#a6e22e", "count": "#fd971f",
               "mine": "#f92672", "anchor": "#ffffff", "name": "#e6db74"}
ZONE_LABELS = {"table": "Tableau", "qty": "Quantité", "avg": "Prix moyen", "count": "Compteur",
               "mine": "Ton prix", "anchor": "Repère HDV", "name": "Nom"}
FLOOR_LABELS = {"floor": "au plancher", "keep": "garder mon prix", "stop": "arrêt (suspect)"}
UNDERCUT_LABELS = {"fixed": "kamas", "percent": "%"}
ROUNDING_LABELS = {"none": "aucun", "down_10": "dizaine inférieure", "down_100": "centaine inférieure",
                   "end_9": "finit par 9"}
CARD = P["card"]
MUTED = P["muted"]
BTN2 = P["btn2"]
BTN2_HOVER = P["btn2_hover"]
ORANGE = P["orange"]
HOTKEY_LABELS = {
    "sell": "Vendre (objet de l'inventaire) OU mettre à jour (une de tes ventes)",
    "sell_all": "Tout vendre : répète la mise en vente (Entrée) tant que c'est sûr",
    "optimize": "Meilleur lot (prix par objet le plus haut)",
    "relist": "Remettre la vente sélectionnée sous le moins cher",
    "relist_all": "Toute la liste (interrupteur dans « Mes ventes »)",
    "pause": "Arrêter le parcours en cours (Tout vendre, Toute la liste)",
    "show_zones": "Afficher les zones calibrées",
    "cheatsheet": "Aide-mémoire des touches par-dessus le jeu",
    "hud": "HUD discret par-dessus le jeu (afficher / cacher)",
    "toggle_window": "Afficher / cacher la fenêtre de l'outil",
    "calibrate_auto": "Calibration automatique (HDV ouvert, onglet Vente)",
    "calibrate_anchor": "Repère : titre « Hôtel de vente » (×2)",
    "calibrate_table": "Tableau « Actuellement en vente » (×2)",
    "calibrate_qty": "Menu « Quantité » (×2)",
    "calibrate_field": "Champ « Prix du lot »",
    "calibrate_avg": "Prix moyen (×2)",
    "calibrate_count": "Compteur « x/100 lots » (×2)",
    "calibrate_modify": "Bouton « Modifier »",
    "calibrate_rows": "Lignes de « mes ventes » (×2)",
    "calibrate_button": "Bouton « Mettre en vente »",
    "calibrate_name": "Nom de l'objet (×2)",
    "calibrate_mine": "Ton prix (secours) (×2)",
}
CALIB_HOTKEYS = [k for k in HOTKEY_LABELS if k.startswith("calibrate_")]
# Touches seules autorisées (sans Ctrl/Alt/Maj) : elles ne servent pas à écrire dans le chat du jeu.
_SOLO_KEYS = {f"f{i}" for i in range(1, 25)} | {"insert", "home", "page up", "page down",
                                                 "pause", "scroll lock"}


def hotkey_problem(name: str, combo: str, hotkeys: dict) -> Optional[str]:
    """Pourquoi `combo` ne peut pas devenir le raccourci `name` (None = accepté)."""
    if not combo or combo.startswith("!"):
        return "lecture du clavier impossible" + (f" ({combo[1:]})" if combo else "")
    if combo == "esc":
        return None
    try:
        core.parse_combo(combo)
    except ValueError as e:
        return str(e)
    parts = combo.split("+")
    if parts[-1] in ("enter", "backspace", "esc", "end") or combo in ("ctrl+v", "ctrl+a"):
        return "touche utilisée par l'outil pour saisir les prix (Entrée, Fin, Retour arrière, Ctrl+V)"
    if len(parts) == 1 and combo not in _SOLO_KEYS:
        return "touche seule trop courante (elle se déclencherait en écrivant) : ajoute Ctrl, Alt ou Maj"
    for other, value in hotkeys.items():
        if other != name and value == combo:
            return f"déjà utilisé par « {HOTKEY_LABELS.get(other, other)} »"
    return None


POINT_COLORS = {"price_field": "#e74c3c", "sell_button": "#2ecc71", "modify_button": "#3498db"}
POINT_LABELS = {"price_field": "Champ « Prix du lot »", "sell_button": "Bouton « Mettre en vente »",
                "modify_button": "Bouton « Modifier »"}


def fmt(n: Optional[int]) -> str:
    return "-" if n is None else f"{n:,}".replace(",", " ")


def ico(name: str, color: Optional[str] = None, size: int = 16):
    """Icône du jeu d'icônes de l'outil (gui/icons.py), de la couleur du texte par défaut."""
    return dofus_icons.ctk_icon(name, color or P["text"], size)


def mix_color(a: str, b: str, t: float) -> str:
    """Mélange de deux couleurs #rrggbb (t = 0 -> a, 1 -> b)."""
    ca = [int(a[i:i + 2], 16) for i in (1, 3, 5)]
    cb = [int(b[i:i + 2], 16) for i in (1, 3, 5)]
    return "#" + "".join(f"{round(x + (y - x) * t):02x}" for x, y in zip(ca, cb))


def faded(img, alpha: float):
    """Image PIL RGBA rendue plus transparente (états vides)."""
    out = img.copy()
    out.putalpha(out.getchannel("A").point(lambda v: int(v * alpha)))
    return out


def price_delta(old: Optional[int], new: Optional[int]) -> Optional[tuple]:
    """Écart entre l'ancien et le nouveau prix : (texte « ▼ 4 % », "down" | "up"), None sans écart."""
    if not old or new is None or old == new:
        return None
    pct = (new - old) / old * 100
    shown = f"{abs(pct):.0f}" if abs(pct) >= 1 else "<1"
    return (f"▼ {shown} %" if pct < 0 else f"▲ {shown} %"), ("down" if pct < 0 else "up")

