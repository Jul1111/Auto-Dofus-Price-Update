#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Dofus Price Helper — logique partagée (GUI + CLI)
-------------------------------------------------
Lecture de l'Hôtel de Vente (onglet Vente) :
- Tableau « ACTUELLEMENT EN VENTE » : colonnes Lot + Prix, lues en entier.
  Chaque ligne est associée à son lot (1 / 10 / 100 / 1000) grâce à la colonne Lot,
  donc une ligne absente (personne ne vend ce lot) ne décale rien.
- Menu « Quantité » : on lit la quantité sélectionnée pour ne JAMAIS coller
  le prix d'un lot dans une autre quantité.
- Un seul appel Tesseract pour le tableau + la quantité.

Saisie : clic sur « Prix du lot » (option), vidage du champ (le jeu le pré-remplit),
collage Ctrl+V, puis option « Mettre en vente » (clic sur le bouton, sinon Entrée).

Les dépendances lourdes (mss, pytesseract, keyboard, pyautogui, pyperclip)
sont importées à la demande : les fonctions pures restent testables partout.
"""
from __future__ import annotations

import csv
import json
import os
import re
import shutil
import statistics
import string
import sys
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np

Region = Tuple[int, int, int, int]  # x, y, w, h
Point = Tuple[int, int]

BASE_DIR = Path(__file__).resolve().parent
CONFIG_PATH = BASE_DIR / "dofus_price_helper_config.json"
HISTORY_PATH = BASE_DIR / "dofus_price_history.csv"
DIGITS_PATH = BASE_DIR / "digit_templates.npz"   # modèles de chiffres appris (lecture rapide)
ANCHOR_PATH = BASE_DIR / "hdv_anchor.png"        # image du titre « Hôtel de vente » (repère)
HISTORY_HEADER = ["ts", "datetime", "action", "lot", "selected_qty", "read_price", "confidence",
                  "new_price", "status", "mode", "value", "rounding"]
CONFIG_VERSION = 5

IS_WINDOWS = sys.platform == "win32"


# --------------------------------------------------------------------------
# DPI : sans ça, pyautogui et mss n'ont pas le même repère sous Windows
# quand l'affichage est à 125 % / 150 %. Doit être appelé avant Tk.
# --------------------------------------------------------------------------
def enable_dpi_awareness() -> None:
    if not IS_WINDOWS:
        return
    import ctypes
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)  # per-monitor
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass


enable_dpi_awareness()


# --------------------------------------------------------------------------
# Config
# --------------------------------------------------------------------------
DEFAULT_HOTKEYS = {
    "sell": "f1",                    # vendre à la quantité affichée dans le jeu
    "sell_all": "f2",                # vendre tout le stock de ce lot au même prix (Entrée répétée)
    "optimize": "f4",                # meilleur lot (demande de changer la quantité si besoin)
    "calibrate_table": "ctrl+alt+f1",  # 2 appuis : coin haut-gauche puis bas-droit
    "calibrate_qty": "ctrl+alt+f2",    # 2 appuis
    "calibrate_field": "ctrl+alt+f3",  # 1 appui sur « Prix du lot »
    "calibrate_button": "ctrl+alt+f4", # 1 appui sur « Mettre en vente »
    "calibrate_avg": "ctrl+alt+f5",    # 2 appuis : valeur du « Prix moyen » (optionnel)
    "calibrate_count": "ctrl+alt+f6",  # 2 appuis : compteur « 21/100 lots en vente » (optionnel)
    "relist": "f3",                  # mes ventes : remettre la ligne sélectionnée sous le moins cher
    "relist_all": "ctrl+f3",         # mes ventes : toutes les lignes (RELIST_AUTO doit être activé)
    "calibrate_mine": "ctrl+alt+f7",   # 2 appuis : texte du champ « Prix du lot » (ton prix actuel)
    "calibrate_modify": "ctrl+alt+f8", # 1 appui sur « Modifier »
    "calibrate_rows": "ctrl+alt+f9",   # 2 appuis : 1re ligne puis 2e ligne de la liste de tes ventes
    "calibrate_anchor": "ctrl+alt+f10",  # 2 appuis : titre « Hôtel de vente » (les zones suivent l'HDV)
    "show_zones": "ctrl+alt+v",
    "pause": "ctrl+alt+p",
    "quit": "ctrl+alt+q",
}


def _copy(obj):
    return json.loads(json.dumps(obj))


@dataclass
class Config:
    # Les noms en MAJUSCULES dans le JSON = nom du champ en majuscules.
    config_version: int = CONFIG_VERSION
    tesseract_cmd: str = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
    lots: List[int] = field(default_factory=lambda: [1, 10, 100, 1000])

    # Zones (coordonnées écran)
    table_region: Optional[List[int]] = None  # colonnes Lot + Prix, SANS icônes objet/kamas
    qty_region: Optional[List[int]] = None    # texte du menu Quantité, SANS la flèche
    price_field: Optional[List[int]] = None   # (x, y) champ « Prix du lot »
    sell_button: Optional[List[int]] = None   # (x, y) bouton « Mettre en vente »
    avg_region: Optional[List[int]] = None    # chiffres sous « PRIX MOYEN » (optionnel)
    count_region: Optional[List[int]] = None  # texte « 21/100 lots en vente » (optionnel)
    anchor_region: Optional[List[int]] = None # repère : titre « Hôtel de vente » (zones suivent l'HDV)
    mine_region: Optional[List[int]] = None   # mes ventes : texte du champ « Prix du lot »
    modify_button: Optional[List[int]] = None # mes ventes : (x, y) bouton « Modifier »
    relist_row: Optional[List[int]] = None    # mes ventes : (x, y) centre de la 1re ligne visible
    relist_step: int = 0                      # mes ventes : hauteur d'une ligne (px)
    table_split: float = 0.45  # séparation colonne Lot / colonne Prix (fraction de largeur)
    scale: int = 2
    fast_digits: bool = True          # lecture rapide des chiffres (apprise), Tesseract en secours

    # Prix
    undercut_mode: str = "fixed"      # "fixed" | "percent"
    undercut_value: float = 1.0       # kamas (fixed) ou % (percent)
    min_price: int = 1
    rounding: str = "none"            # "none" | "down_10" | "down_100" | "end_9"
    tie_tolerance: float = 0.01       # ex aequo (prix unitaire) -> plus petit lot

    # Garde-fous
    min_confidence: float = 60.0      # confiance OCR mini (0-100) pour coller auto
    max_ratio: float = 5.0            # écart max de prix unitaire entre lots
    confirm_window: float = 3.0       # ré-appuyer dans ce délai = forcer
    own_price_ttl: float = 1800.0     # s : prix en tête = ton dernier prix -> pas d'undercut
    min_avg_ratio: float = 0.5        # FLOOR_MODE "stop" : prix unitaire < 50 % du prix moyen = suspect
    floor_mode: str = "floor"         # concurrent sous le plancher : "floor" (se mettre au plancher)
                                      # | "keep" (garder ton prix en F3) | "stop" (suspect, arrêt)
    floor_ratio: float = 0.7          # plancher = 70 % du « Prix moyen » (par objet) ; 0 = off

    # « Tout vendre » (F2)
    sell_all_max: int = 20            # nombre max de mises en vente par appui
    sell_all_delay: float = 0.6       # s entre deux mises en vente (laisser le jeu se mettre à jour)
    verify_count: bool = True         # F2 : vérifier chaque vente avec le compteur « x/100 lots »

    # « Mettre à jour mes ventes » (F3 / Ctrl+F3)
    relist_auto: bool = False         # Ctrl+F3 : parcourir toute la liste seul (risque CGU : à toi de voir)
    relist_rows: int = 10             # lignes entièrement visibles dans la liste
    relist_scroll_max: int = 40       # crans de molette max pour passer une page
    relist_scroll_page: float = 0.5   # défilement visé : 0.5 = une demi-page entre deux lectures
    relist_max: int = 400             # garde-fou : lignes lues max par appui (boucle infinie impossible)
    relist_delay: float = 0.5         # s après un clic sur une ligne / une modification
    relist_confirm_enter: bool = True # « Modifier » : Entrée si une fenêtre de confirmation reste ouverte

    # Saisie
    auto_paste: bool = False          # coller automatiquement (sinon copie seule)
    click_field: bool = False         # cliquer sur « Prix du lot » avant de coller
    input_method: str = "paste"       # "paste" (Ctrl+V, marche en jeu) | "type" (touches : faux en AZERTY)
    clear_method: str = "backspace"   # "backspace" (Fin + effacer) | "ctrl_a" ; le champ est pré-rempli
    auto_validate: bool = False       # mettre en vente automatiquement après collage
    validate_method: str = "enter"    # "enter" (rapide, souris immobile) | "click" (bouton calibré)
    restore_clipboard: bool = True

    # Confort
    # Hotkeys actifs seulement si la fenêtre active est le jeu :
    # nom de l'exe contient WINDOW_PROCESS, ou titre contient WINDOW_TITLE.
    window_process: str = "dofus"     # Dofus.exe
    window_title: str = " - Release"  # titre : « Perso - Classe - version - Release »
    require_focus: bool = True
    sound: bool = True
    toast: bool = True
    calib_countdown: int = 3          # secondes avant calibration via bouton UI

    hotkeys: Dict = field(default_factory=lambda: _copy(DEFAULT_HOTKEYS))

    # ---------- I/O ----------
    @classmethod
    def load(cls, path: Path = CONFIG_PATH) -> "Config":
        cfg = cls()
        if not path.exists():
            return cfg
        try:
            data = json.loads(path.read_text(encoding="utf-8")) or {}
        except (OSError, json.JSONDecodeError) as e:
            print(f"[Config] Lecture impossible ({e}), valeurs par défaut.")
            return cfg
        old = int(data.get("CONFIG_VERSION", 1)) < 2  # v1 seulement : raccourcis incompatibles
        for name in cfg.__dataclass_fields__:
            key = name.upper()
            if key not in data or name == "config_version":
                continue
            if old and name == "hotkeys":
                continue  # v1 : raccourcis par lot, incompatibles -> défauts v2
            default = getattr(cfg, name)
            value = data[key]
            try:
                if isinstance(default, bool):
                    value = bool(value)
                elif isinstance(default, int) and not isinstance(default, bool):
                    value = int(value)
                elif isinstance(default, float):
                    value = float(value)
            except (TypeError, ValueError):
                print(f"[Config] Valeur invalide pour {key}: {value!r}, ignorée.")
                continue
            setattr(cfg, name, value)
        hk = _copy(DEFAULT_HOTKEYS)
        hk.update({k: v for k, v in (cfg.hotkeys or {}).items() if isinstance(v, str)})
        cfg.hotkeys = hk
        cfg.lots = sorted({int(l) for l in cfg.lots})
        if "WINDOW_PROCESS" not in data and cfg.window_title == "Dofus":
            cfg.window_title = cls.window_title  # ancien défaut v1, faux
        if int(data.get("CONFIG_VERSION", 1)) < 4:
            # v4 : la frappe chiffre par chiffre ne marche pas en AZERTY (touche "6" = "-")
            # -> collage Ctrl+V (validé en jeu) ; le champ est vidé par Fin + Retour arrière.
            cfg.input_method, cfg.clear_method = "paste", "backspace"
        if int(data.get("CONFIG_VERSION", 1)) < 5 and cfg.relist_max == 120:
            cfg.relist_max = cls.relist_max  # v5 : 120 était trop bas pour une liste de 100+ lots
        cfg.config_version = CONFIG_VERSION
        return cfg

    def save(self, path: Path = CONFIG_PATH) -> None:
        data = {name.upper(): getattr(self, name) for name in self.__dataclass_fields__}
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, path)  # écriture atomique


# --------------------------------------------------------------------------
# Repère HDV : les zones suivent la fenêtre de l'Hôtel de vente
# --------------------------------------------------------------------------
ANCHOR_OK = 0.90      # score au même endroit : pas bougé
ANCHOR_FOUND = 0.80   # score mini pour accepter une nouvelle position
REGION_FIELDS = ("table_region", "qty_region", "avg_region", "count_region", "mine_region", "anchor_region")
POINT_FIELDS = ("price_field", "sell_button", "modify_button", "relist_row")


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


def rect_from_points(p1: Point, p2: Point) -> Region:
    x1, x2 = sorted((p1[0], p2[0]))
    y1, y2 = sorted((p1[1], p2[1]))
    return x1, y1, max(1, x2 - x1), max(1, y2 - y1)


# --------------------------------------------------------------------------
# Calcul du prix (pur, testé)
# --------------------------------------------------------------------------
def floor_price(lot: int, avg: Optional[int], ratio: float) -> Optional[int]:
    """Prix plancher du lot = ratio × prix moyen (par objet) × lot, arrondi au-dessus."""
    if not avg or ratio <= 0:
        return None
    return max(1, int(-(-avg * ratio * lot // 1)))


def smart_round(p: int, mode: str) -> int:
    """Arrondi toujours VERS LE BAS (ne doit jamais remonter le prix)."""
    if mode == "down_10":
        return (p // 10) * 10
    if mode == "down_100":
        return (p // 100) * 100
    if mode == "end_9":
        return p if p % 10 == 9 else p - (p % 10) - 1
    return p


def compute_price(price: Optional[int], mode: str, value, rounding: str,
                  min_price: int) -> Optional[int]:
    """Prix d'undercut. Garantit new < price (sauf si on bute sur min_price)."""
    if price is None:
        return None
    if mode == "percent":
        try:
            v = float(value)
        except (TypeError, ValueError):
            v = 1.0
        new_p = int(price * (1 - v / 100.0))  # floor
    else:
        try:
            v = int(float(value))
        except (TypeError, ValueError):
            v = 1
        new_p = price - v
    new_p = smart_round(new_p, rounding)
    if new_p >= price:
        new_p = price - 1
    return max(int(min_price), new_p)


def pick_best_lot(prices: Dict[int, Optional[int]], tolerance: float = 0.01) -> Optional[int]:
    """Lot au meilleur prix unitaire. Ex aequo (± tolerance) -> plus petit lot."""
    unit = {lot: p / lot for lot, p in prices.items() if p}
    if not unit:
        return None
    best = max(unit.values())
    return min(lot for lot, u in unit.items() if u >= best * (1 - tolerance))


def check_coherence(lot: int, prices: Dict[int, Optional[int]], max_ratio: float) -> Optional[str]:
    """Écart du prix unitaire du lot vs les autres lots (chiffre perdu/ajouté)."""
    p = prices.get(lot)
    if not p:
        return None
    others = [q / l for l, q in prices.items() if l != lot and q]
    if not others:
        return None
    u, ref = p / lot, statistics.median(others)
    if ref <= 0:
        return None
    ratio = u / ref
    if ratio > max_ratio or ratio < 1 / max_ratio:
        return f"prix unitaire {u:.0f} vs {ref:.0f} pour les autres lots (x{ratio:.1f})"
    return None


def derive_price(lot: int, prices: Dict[int, Optional[int]]) -> Optional[int]:
    """Personne ne vend ce lot : estimation = plus bas prix unitaire des autres lots × lot."""
    units = [p / l for l, p in prices.items() if p and l != lot]
    if not units:
        return None
    return max(1, int(min(units) * lot))


# --------------------------------------------------------------------------
# OCR
# --------------------------------------------------------------------------
@dataclass
class Reading:
    value: Optional[int]
    confidence: float  # 0-100, -1 si rien lu
    raw: str = ""


@dataclass
class ScreenRead:
    prices: Dict[int, Reading] = field(default_factory=dict)
    selected: Optional[int] = None       # quantité sélectionnée (None = non lue)
    selected_raw: str = ""
    avg: Optional[int] = None            # « Prix moyen » (par objet), None = non lu / non calibré
    listed: Optional[Tuple[int, int]] = None  # compteur (n, max), rempli par le test de lecture
    mine: Optional[int] = None                # ton prix (mes ventes), rempli par le test de lecture
    mine_r: Optional["Reading"] = None        # ton prix lu dans le même appel OCR (mes ventes)
    engine: str = ""                          # "chiffres" (rapide) | "tesseract"

    @property
    def values(self) -> Dict[int, Optional[int]]:
        return {l: r.value for l, r in self.prices.items()}


_tls = threading.local()
BORDER = 10
# Chiffres seulement, via une LISTE NOIRE (lettres + ponctuation) :
# - une whitelist "0123456789" sans espace colle "1 789" en un mot et la confiance tombe à ~0 ;
# - une whitelist avec espace demande des guillemets, que pytesseract sous Windows
#   (shlex non-POSIX) refuse : « No closing quotation ».
# Aucun guillemet, espace ni antislash ne doit donc apparaître dans cette config.
_BLACKLIST = "".join(c for c in string.ascii_letters + string.punctuation if c not in "\"'\\")
OCR_CONFIG = f"--psm 6 -c tessedit_char_blacklist={_BLACKLIST}"
# Compteur « 21/100 lots en vente » : même liste noire SANS « / » (séparateur), une ligne.
# Appel séparé : autoriser « / » dans le tableau ferait lire des « 1 » comme « / ».
_COUNT_BLACKLIST = _BLACKLIST.replace("/", "")
COUNT_CONFIG = f"--psm 7 -c tessedit_char_blacklist={_COUNT_BLACKLIST}"
_COUNT_RE = re.compile(r"(\d+)\s*/\s*(\d+)")


def setup_tesseract(cfg: Config) -> Optional[str]:
    """Configure le binaire Tesseract. Retourne un message d'erreur ou None."""
    import pytesseract
    if cfg.tesseract_cmd and Path(cfg.tesseract_cmd).exists():
        pytesseract.pytesseract.tesseract_cmd = cfg.tesseract_cmd
        return None
    found = shutil.which("tesseract")
    if found:
        pytesseract.pytesseract.tesseract_cmd = found
        return None
    return ("Tesseract introuvable. Installe-le ou corrige TESSERACT_CMD "
            "dans dofus_price_helper_config.json.")


def grab_screen(region: Region) -> np.ndarray:
    import mss
    sct = getattr(_tls, "sct", None)
    if sct is None:  # une instance mss par thread (non thread-safe)
        sct = _tls.sct = mss.mss()
    x, y, w, h = region
    img = np.array(sct.grab({"left": x, "top": y, "width": w, "height": h}))
    return img[:, :, :3]  # BGR


def preprocess(img_bgr: np.ndarray, scale: int = 2) -> np.ndarray:
    """Niveaux de gris, agrandissement, binarisation Otsu, texte NOIR sur BLANC."""
    import cv2
    gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
    # Texte Dofus = blanc/gris (peu saturé). Icônes kamas (jaune) et objets (couleurs) :
    # saturées -> remplacées par le fond, sinon l'icône kamas est lue comme un "4".
    hsv = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2HSV)
    colored = ((hsv[:, :, 1] > 80) & (hsv[:, :, 2] > 60)).astype(np.uint8)
    # + contour gris des icônes (anticrénelage) : sans ça, les restes d'une icône d'objet
    # se collent au « 1 » de la colonne Lot et la ligne du lot 1 disparaît.
    colored = cv2.dilate(colored, np.ones((3, 3), np.uint8)).astype(bool)
    if colored.any() and (~colored).any():
        gray = gray.copy()
        gray[colored] = int(np.median(gray[~colored]))
    up = cv2.resize(gray, (gray.shape[1] * scale, gray.shape[0] * scale),
                    interpolation=cv2.INTER_CUBIC)
    t, th = cv2.threshold(up, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    if np.mean(th) > 255 * 0.3:
        # Trop de pixels « clairs » : Otsu a séparé le fond d'un CADRE gris (menu Quantité
        # grisé, champ) au lieu du texte. 2e seuil, parmi les pixels clairs seulement.
        bright = up[up > t]
        t2, _ = cv2.threshold(bright.reshape(-1, 1), 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        th2 = np.where(up > t2, 255, 0).astype(np.uint8)
        if 0.002 < np.mean(th2) / 255 < 0.3:
            th = th2
    if np.mean(th) < 127:  # fond sombre majoritaire -> inverser
        th = cv2.bitwise_not(th)
    th = _drop_big_blobs(th, scale)
    return cv2.copyMakeBorder(th, BORDER, BORDER, BORDER, BORDER, cv2.BORDER_CONSTANT, value=255)


def _drop_big_blobs(th: np.ndarray, scale: int) -> np.ndarray:
    """Efface les taches noires trop grandes pour être un chiffre : icônes d'objet
    PÂLES (laine céleste, plumes : pas assez colorées pour le masque de couleur),
    traits de séparation. Un chiffre Dofus fait ~10 px de haut à l'échelle 1."""
    import cv2
    ink = (th == 0).astype(np.uint8)
    n, lab, stats, _ = cv2.connectedComponentsWithStats(ink, connectivity=8)
    if n <= 1:
        return th
    h, w = stats[1:, cv2.CC_STAT_HEIGHT], stats[1:, cv2.CC_STAT_WIDTH]
    big = (h > 16 * scale) | (w > 24 * scale)
    if not big.any():
        return th
    out = th.copy()
    out[np.isin(lab, np.where(big)[0] + 1)] = 255
    return out


def stack_images(imgs: List[np.ndarray], gap: int = 30) -> Tuple[np.ndarray, List[Tuple[int, int]]]:
    """Empile verticalement des images binaires. Retourne l'image et les bornes y de chaque segment."""
    width = max(i.shape[1] for i in imgs)
    parts, bounds, y = [], [], 0
    for i, img in enumerate(imgs):
        if img.shape[1] < width:
            pad = np.full((img.shape[0], width - img.shape[1]), 255, dtype=img.dtype)
            img = np.hstack([img, pad])
        parts.append(img)
        bounds.append((y, y + img.shape[0]))
        y += img.shape[0]
        if i < len(imgs) - 1:
            parts.append(np.full((gap, width), 255, dtype=img.dtype))
            y += gap
    return np.vstack(parts), bounds


def _words(data: Dict[str, list], y0: int, y1: int):
    """Mots contenant des chiffres dont le centre vertical est dans [y0, y1)."""
    n = len(data["text"])
    for i in range(n):
        digits = "".join(c for c in str(data["text"][i]) if c.isdigit())
        if not digits:
            continue
        cy = int(data["top"][i]) + int(data["height"][i]) / 2
        if y0 <= cy < y1:
            yield i, digits


def parse_table(data: Dict[str, list], bounds: Tuple[int, int], inner_width: int,
                split: float, lots: List[int]) -> Dict[int, Reading]:
    """Lignes du tableau -> {lot: Reading}. Colonne Lot à gauche de `split`, Prix à droite.
    Un lot illisible est déduit de l'ordre des lignes (lots croissants de haut en bas)
    quand un seul lot est possible entre la ligne du dessus et celle du dessous."""
    rows: Dict[tuple, List[Tuple[int, str, float, bool, int]]] = {}
    for i, digits in _words(data, *bounds):
        key = (data["block_num"][i], data["par_num"][i], data["line_num"][i])
        cx = (int(data["left"][i]) + int(data["width"][i]) / 2 - BORDER) / max(1, inner_width)
        rows.setdefault(key, []).append((int(data["left"][i]), digits, float(data["conf"][i]),
                                         cx < split, int(data["top"][i])))
    parsed: List[Tuple[int, Optional[int], Reading]] = []  # (y, lot ou None, prix)
    for words in rows.values():
        words.sort()
        price_w = [w for w in words if not w[3]]
        if not price_w:
            continue
        lot_txt = "".join(w[1] for w in words if w[3])
        if lot_txt and int(lot_txt) not in lots:
            continue  # lot lu mais impossible (ex. « 7 ») : ligne ignorée, jamais déduite
        lot = int(lot_txt) if lot_txt else None  # None = illisible -> déduit de l'ordre
        reading = Reading(int("".join(w[1] for w in price_w)), min(w[2] for w in price_w),
                          " ".join(w[1] for w in price_w))
        parsed.append((min(w[4] for w in words), lot, reading))
    parsed.sort(key=lambda t: t[0])
    known = [lot for _, lot, _ in parsed if lot is not None]
    out: Dict[int, Reading] = {}
    i = 0
    while i < len(parsed):
        _, lot, reading = parsed[i]
        if lot is not None:
            out.setdefault(lot, reading)
            i += 1
            continue
        # bloc de lignes consécutives au lot illisible, entre deux lots connus
        j = i
        while j < len(parsed) and parsed[j][1] is None:
            j += 1
        lo = next((l for _, l, _ in reversed(parsed[:i]) if l is not None), 0)
        hi = parsed[j][1] if j < len(parsed) else float("inf")
        cands = [l for l in lots if lo < l < hi and l not in known]
        if len(cands) == j - i:          # autant de lots possibles que de lignes : sans ambiguïté
            for (_, _, rd), l in zip(parsed[i:j], cands):
                out.setdefault(l, rd)
        i = j
    return out


def parse_number(data: Dict[str, list], bounds: Tuple[int, int]) -> Reading:
    ws = sorted((int(data["left"][i]), d, float(data["conf"][i])) for i, d in _words(data, *bounds))
    if not ws:
        return Reading(None, -1.0, "")
    return Reading(int("".join(w[1] for w in ws)), min(w[2] for w in ws), " ".join(w[1] for w in ws))


def read_screen(cfg: Config, debug_dir: Optional[Path] = None, with_mine: bool = False) -> ScreenRead:
    """Tableau + quantité (+ prix moyen, + ton prix) en UN appel Tesseract."""
    import pytesseract
    if not cfg.table_region:
        return ScreenRead()
    regions = [tuple(cfg.table_region)]
    if cfg.qty_region:
        regions.append(tuple(cfg.qty_region))
    if cfg.avg_region:
        regions.append(tuple(cfg.avg_region))
    imgs = [preprocess(grab_screen(r), cfg.scale) for r in regions]
    mine_img = None
    if with_mine:
        # même échelle que le reste : à ×4 le texte est trop grand pour cet appel groupé
        mine_img = mine_field_image(cfg, cfg.scale)
        if mine_img is not None:
            imgs.append(mine_img)
    comp, bounds = stack_images(imgs)
    if debug_dir:
        import cv2
        debug_dir.mkdir(exist_ok=True)
        cv2.imwrite(str(debug_dir / f"ocr_{int(time.time() * 1000)}.png"), comp)
    data, engine = _ocr(comp, bounds, cfg)
    inner_w = imgs[0].shape[1] - 2 * BORDER
    res = _parse_screen(data, bounds, inner_w, cfg, len(regions), mine_img is not None)
    if engine == "chiffres" and (not res.prices or (cfg.qty_region and res.selected is None)):
        # Lecture rapide incomplète (tableau vide, quantité manquante) : Tesseract tranche.
        data, engine = _ocr(comp, bounds, cfg, force_tesseract=True)
        res = _parse_screen(data, bounds, inner_w, cfg, len(regions), mine_img is not None)
    res.engine = engine
    ENGINE_STATS[engine] = ENGINE_STATS.get(engine, 0) + 1
    return res


ENGINE_STATS: Dict[str, int] = {}   # nombre de lectures par moteur (« chiffres » / « tesseract »)


def _parse_screen(data, bounds, inner_w: int, cfg: Config, n_regions: int, with_mine: bool) -> ScreenRead:
    res = ScreenRead(prices=parse_table(data, bounds[0], inner_w, cfg.table_split, cfg.lots))
    if cfg.qty_region:
        q = parse_number(data, bounds[1])
        res.selected_raw = q.raw
        res.selected = q.value if q.value in cfg.lots else None
    if cfg.avg_region:
        a = parse_number(data, bounds[n_regions - 1])
        res.avg = a.value if a.value and a.confidence >= cfg.min_confidence else None
    if with_mine:
        res.mine_r = parse_number(data, bounds[-1])
    return res


RELIST_READ_TRIES = 8   # F3 : relectures max si le tableau n'est pas encore chargé (~1 s)

_digits = None
_digits_lock = threading.Lock()
_fast_count = 0
CROSS_CHECK_EVERY = 25   # 1 lecture rapide sur 25 est recontrôlée par Tesseract


def digit_reader():
    global _digits
    with _digits_lock:
        if _digits is None:
            from dofus_digits import DigitReader
            _digits = DigitReader(DIGITS_PATH)
        return _digits


def _ocr(comp: np.ndarray, bounds, cfg: Config, force_tesseract: bool = False):
    """Lecture rapide si les chiffres sont appris et tous reconnus avec certitude ;
    sinon Tesseract (qui sert aussi à apprendre). Contrôle croisé régulier."""
    import pytesseract
    global _fast_count
    dr = digit_reader() if cfg.fast_digits else None
    fast = dr.read_data(comp, bounds) if dr and not force_tesseract else None
    if fast is not None:
        _fast_count += 1
        if _fast_count % CROSS_CHECK_EVERY:
            return fast, "chiffres"
    data = pytesseract.image_to_data(comp, config=OCR_CONFIG, output_type=pytesseract.Output.DICT)
    if fast is not None and _digits_disagree(fast, data, bounds, cfg):
        print("[Chiffres] Contrôle : désaccord avec Tesseract, modèles réinitialisés.")
        dr.reset()
    if dr:
        dr.learn(comp, data, bounds)
    return data, "tesseract"


def _digits_disagree(a, b, bounds, cfg: Config) -> bool:
    for y0, y1 in bounds:
        ra, rb = parse_number(a, (y0, y1)), parse_number(b, (y0, y1))
        if rb.confidence >= 90 and ra.value != rb.value:
            return True
    return False


def detect_rows(strip_bgr: np.ndarray, top: int, step: int) -> List[int]:
    """Centres (y écran) des lignes ENTIÈREMENT visibles de la liste « mes ventes ».
    Les lignes (fond ~54, ~74 au survol) sont séparées par des bandes plus sombres (~32) :
    on les retrouve sur le profil vertical, quel que soit le défilement."""
    import cv2
    if strip_bgr.size == 0:
        return []
    gray = cv2.cvtColor(strip_bgr, cv2.COLOR_BGR2GRAY) if strip_bgr.ndim == 3 else strip_bgr
    prof = np.median(gray, axis=1)
    level = float(np.percentile(prof, 75))
    is_row = prof > level - 12
    out, start = [], None
    for i, r in enumerate(list(is_row) + [False]):
        if r and start is None:
            start = i
        elif not r and start is not None:
            n = i - start
            # ligne complète : ni coupée en haut/bas de la zone, ni fusionnée avec la voisine
            if 0.6 * step <= n <= 1.3 * step and start > 0 and i < len(prof):
                out.append(top + (start + i - 1) // 2)
            start = None
    return out


def _same_row(a: np.ndarray, b: np.ndarray) -> bool:
    """Deux lignes de la liste STRICTEMENT identiques (même objet, même prix, même durée).
    On compte les pixels vraiment différents : une moyenne globale ne voyait pas un seul
    chiffre de prix changé (76 vs 75 -> ligne sautée à tort)."""
    import cv2
    if a.shape != b.shape:
        return False
    ga = cv2.cvtColor(a, cv2.COLOR_BGR2GRAY) if a.ndim == 3 else a
    gb = cv2.cvtColor(b, cv2.COLOR_BGR2GRAY) if b.ndim == 3 else b
    return int((np.abs(ga.astype(np.int16) - gb.astype(np.int16)) > 40).sum()) <= 6


def wait_change(region: Optional[Region], before: Optional[np.ndarray], timeout: float,
                min_wait: float = 0.05) -> None:
    """Attend que la zone change à l'écran (panneau mis à jour), au plus `timeout` s.
    Remplace une pause fixe : le jeu répond souvent en ~0,1 s."""
    time.sleep(min_wait)
    if region is None or before is None:
        time.sleep(max(0.0, timeout - min_wait))
        return
    end = time.time() + timeout - min_wait
    while time.time() < end:
        if not np.array_equal(grab_screen(region), before):
            time.sleep(0.03)  # laisser finir l'affichage
            return
        time.sleep(0.03)


def _find_field(img_bgr: np.ndarray) -> Optional[np.ndarray]:
    """Dans une zone trop large, isole le champ « Prix du lot » : rectangle presque NOIR
    (bien plus sombre que le panneau), large et peu haut."""
    import cv2
    if img_bgr.size == 0:
        return None
    if img_bgr.shape[1] < 220 and img_bgr.shape[0] < 60:
        return img_bgr  # zone déjà ajustée au champ
    best = None
    # champ sélectionné : ~8 ; champ non sélectionné : ~27 (panneau ~40)
    for limit in (20, 33):
        dark = (img_bgr.max(axis=2) < limit).astype(np.uint8)
        n, _, stats, _ = cv2.connectedComponentsWithStats(dark)
        for k in range(1, n):
            x, y, w, h, area = (int(v) for v in stats[k])
            if 60 <= w <= 400 and 12 <= h <= 60 and w >= 3 * h and area >= 0.6 * w * h:
                if best is None or area > best[4]:
                    best = (x, y, w, h, area)
        if best is not None:
            break
    if best is None:
        return None  # pas de champ (vente désélectionnée) : ne pas lire toute la zone
    x, y, w, h, _ = best
    return img_bgr[y:y + h, x:x + w]


def preprocess_field(img_bgr: np.ndarray, scale: int = 4) -> Optional[np.ndarray]:
    """Champ « Prix du lot ». Zone trop large -> on y retrouve le champ (rectangle noir).
    Texte souvent SÉLECTIONNÉ (fond bleu) : le masque des couleurs effacerait tout ->
    recadrage sur le surlignage puis Otsu ; sinon traitement normal du champ seul."""
    import cv2
    img_bgr = _find_field(img_bgr)
    if img_bgr is None:
        return None
    c = img_bgr.astype(int)
    hl = (c[:, :, 0] > 110) & (c[:, :, 0] > c[:, :, 2] + 40)
    if hl.sum() < 20:
        return preprocess(img_bgr, max(2, scale // 2))
    # plus grande tache bleue = le surlignage (pas une icône bleue voisine)
    n, _, stats, _ = cv2.connectedComponentsWithStats(hl.astype(np.uint8))
    k = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
    x, y, w, h = (int(v) for v in stats[k, :4])
    sub = img_bgr[y:y + h, x:x + w]
    gray = cv2.cvtColor(sub, cv2.COLOR_BGR2GRAY)
    up = cv2.resize(gray, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
    _, th = cv2.threshold(up, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    if np.mean(th) < 127:
        th = cv2.bitwise_not(th)
    return cv2.copyMakeBorder(th, BORDER, BORDER, BORDER, BORDER, cv2.BORDER_CONSTANT, value=255)


def mine_regions(cfg: Config) -> List[Region]:
    """Où chercher le champ « Prix du lot » : autour du point calibré du champ
    (Ctrl+Alt+F3, le plus fiable), puis la zone « Ton prix » (Ctrl+Alt+F7)."""
    out = []
    if cfg.price_field:
        x, y = cfg.price_field
        out.append((max(0, x - 140), max(0, y - 30), 280, 60))
    if cfg.mine_region:
        out.append(tuple(cfg.mine_region))
    return out


def mine_field_image(cfg: Config, scale: int = 4) -> Optional[np.ndarray]:
    for region in mine_regions(cfg):
        img = preprocess_field(grab_screen(region), scale)
        if img is not None:
            return img
    return None


def read_mine(cfg: Config) -> Reading:
    """Ton prix actuel (champ « Prix du lot » de la vente sélectionnée)."""
    import pytesseract
    img = mine_field_image(cfg)
    if img is None:
        return Reading(None, -1.0, "")
    data = pytesseract.image_to_data(img, config=OCR_CONFIG, output_type=pytesseract.Output.DICT)
    return parse_number(data, (0, img.shape[0]))


def parse_counter(text: str) -> Optional[Tuple[int, int]]:
    """« 21/100 lots en vente » -> (21, 100). None si illisible ou incohérent."""
    m = _COUNT_RE.search(text or "")
    if not m:
        return None
    n, mx = int(m.group(1)), int(m.group(2))
    return (n, mx) if 0 <= n <= mx and mx > 0 else None


def read_counter(cfg: Config) -> Optional[Tuple[int, int]]:
    """Compteur de lots en vente (n, max). None si non calibré ou illisible."""
    import pytesseract
    if not cfg.count_region:
        return None
    img = preprocess(grab_screen(tuple(cfg.count_region)), cfg.scale)
    return parse_counter(pytesseract.image_to_string(img, config=COUNT_CONFIG))


# --------------------------------------------------------------------------
# Fenêtre active / saisie / son
# --------------------------------------------------------------------------
def foreground_info() -> Optional[Tuple[str, str]]:
    """(titre, nom de l'exe) de la fenêtre active. None hors Windows."""
    if not IS_WINDOWS:
        return None
    import ctypes
    from ctypes import wintypes
    user32, kernel32 = ctypes.windll.user32, ctypes.windll.kernel32
    hwnd = user32.GetForegroundWindow()
    n = user32.GetWindowTextLengthW(hwnd)
    buf = ctypes.create_unicode_buffer(n + 1)
    user32.GetWindowTextW(hwnd, buf, n + 1)
    title = buf.value

    exe = ""
    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    h = kernel32.OpenProcess(0x1000, False, pid.value)  # PROCESS_QUERY_LIMITED_INFORMATION
    if h:
        try:
            size = wintypes.DWORD(1024)
            pbuf = ctypes.create_unicode_buffer(size.value)
            if kernel32.QueryFullProcessImageNameW(h, 0, pbuf, ctypes.byref(size)):
                exe = Path(pbuf.value).name
        finally:
            kernel32.CloseHandle(h)
    return title, exe


def is_game_window(title: str, exe: str, cfg: Config) -> bool:
    """Fenêtre du jeu si le nom de l'exe OU le titre correspond.
    Titre Dofus : « Perso - Classe - version - Release » -> pas de « Dofus » dedans."""
    if cfg.window_process and cfg.window_process.lower() in exe.lower():
        return True
    if cfg.window_title and cfg.window_title.lower() in title.lower():
        return True
    return False


def game_has_focus(cfg: Config) -> bool:
    if not cfg.require_focus or not (cfg.window_process or cfg.window_title):
        return True
    info = foreground_info()
    if info is None:  # hors Windows : pas de vérification possible
        return True
    return is_game_window(*info, cfg)


def mouse_position() -> Point:
    import pyautogui
    p = pyautogui.position()
    return int(p[0]), int(p[1])


# Presse-papier : une seule restauration en attente à la fois. Sans ça, avec « Tout vendre »,
# la restauration de la vente précédente écrasait le prix juste avant le Ctrl+V suivant
# (le texte de l'utilisateur était collé dans « Prix du lot »).
_clip_lock = threading.Lock()
_clip_timer: Optional[threading.Timer] = None
_clip_saved: Optional[str] = None  # presse-papier de l'utilisateur, à remettre


def _take_clipboard(pyperclip, cfg: Config) -> None:
    """Annule la restauration en attente ; mémorise le presse-papier de l'utilisateur."""
    global _clip_timer, _clip_saved
    with _clip_lock:
        if _clip_timer is not None:      # restauration en attente : le presse-papier
            _clip_timer.cancel()         # contient encore NOTRE prix, garder l'ancien texte
            _clip_timer = None
        elif cfg.restore_clipboard:
            try:
                _clip_saved = pyperclip.paste()
            except Exception:
                _clip_saved = None


def _schedule_restore(pyperclip, delay: float = 1.0) -> None:
    global _clip_timer, _clip_saved

    def _restore():
        global _clip_timer, _clip_saved
        with _clip_lock:
            if _clip_saved is not None:
                try:
                    pyperclip.copy(_clip_saved)
                except Exception:
                    pass
            _clip_timer, _clip_saved = None, None

    with _clip_lock:
        if _clip_saved is None:
            return
        _clip_timer = threading.Timer(delay, _restore)
        _clip_timer.daemon = True
        _clip_timer.start()


def _set_clipboard(pyperclip, text: str, tries: int = 3) -> bool:
    """Vide le presse-papier, y met `text`, puis vérifie qu'il contient bien `text`."""
    for _ in range(tries):
        try:
            pyperclip.copy("")
            pyperclip.copy(text)
            if pyperclip.paste() == text:
                return True
        except Exception:
            pass
        time.sleep(0.05)
    return False


def input_price(value: int, cfg: Config, paste: bool = True, validate: bool = False) -> str:
    """paste=False : copie seulement le prix dans le presse-papier.
    paste=True  : clic sur « Prix du lot » (option) -> vidage -> saisie -> (mise en vente)."""
    import pyperclip
    if not paste:
        _take_clipboard(pyperclip, Config(restore_clipboard=False))
        _set_clipboard(pyperclip, str(value))
        return "copié"

    import keyboard
    import pyautogui
    use_clip = cfg.input_method == "paste"
    if use_clip:
        _take_clipboard(pyperclip, cfg)
        if not _set_clipboard(pyperclip, str(value)):
            _schedule_restore(pyperclip, 0.0)
            raise RuntimeError("presse-papier inaccessible : rien n'a été collé")

    restore_mouse = None
    if cfg.click_field and cfg.price_field:
        restore_mouse = mouse_position()
        pyautogui.click(*cfg.price_field)
        time.sleep(0.08)

    # Le jeu pré-remplit « Prix du lot » : sans vidage, on obtiendrait "353" + "34".
    if cfg.clear_method == "ctrl_a":
        keyboard.press_and_release("ctrl+a")
    else:  # "backspace" : fin du champ puis effacement, sans combinaison Ctrl
        keyboard.press_and_release("end")
        for _ in range(12):
            keyboard.press_and_release("backspace")
            time.sleep(0.005)
    time.sleep(0.04)

    if use_clip:
        keyboard.press_and_release("ctrl+v")
    else:  # "type" : chiffre par chiffre. Attention : faux en AZERTY (chiffres = Maj + touche)
        for ch in str(value):
            keyboard.press_and_release(ch)
            time.sleep(0.01)
    done = "saisi"

    if validate:
        time.sleep(0.15)
        if cfg.validate_method == "click" and cfg.sell_button:
            restore_mouse = restore_mouse or mouse_position()
            pyautogui.click(*cfg.sell_button)
        else:
            keyboard.press_and_release("enter")
        done = "saisi + mis en vente"
    if restore_mouse:
        pyautogui.moveTo(*restore_mouse)

    if use_clip:
        _schedule_restore(pyperclip, 1.0)  # laisser le jeu lire le presse-papier
    return done


def press_validate(cfg: Config) -> None:
    """Remet en vente au prix déjà affiché dans « Prix du lot » (le jeu le garde après une vente)."""
    import keyboard
    if cfg.validate_method == "click" and cfg.sell_button:
        import pyautogui
        back = mouse_position()
        pyautogui.click(*cfg.sell_button)
        pyautogui.moveTo(*back)
    else:
        keyboard.press_and_release("enter")


def press_modify(cfg: Config) -> None:
    """Valide la modification : clic sur « Modifier » si calibré, sinon Entrée."""
    import keyboard
    if cfg.modify_button:
        import pyautogui
        back = mouse_position()
        pyautogui.click(*cfg.modify_button)
        pyautogui.moveTo(*back)
    else:
        keyboard.press_and_release("enter")


def press_enter() -> None:
    import keyboard
    keyboard.press_and_release("enter")


def click_at(p: Point) -> None:
    import pyautogui
    pyautogui.click(*p)


WHEEL_DELTA = 120  # un cran de molette sous Windows


def scroll_at(p: Point, notches: int) -> None:
    """Molette vers le bas de `notches` crans. Sous Windows, pyautogui.scroll(n) envoie n
    BRUT (1 = 1/120 de cran) : il faut multiplier par 120, sinon la liste bouge à peine."""
    import pyautogui
    pyautogui.moveTo(*p)
    pyautogui.scroll(-abs(notches) * (WHEEL_DELTA if IS_WINDOWS else 1))


def measure_shift(before: np.ndarray, after: np.ndarray, step: int,
                  expected: Optional[int] = None) -> Optional[int]:
    """Déplacement vers le haut (px) du contenu de la liste entre deux captures.
    Bande de 2 lignes de `after` recherchée dans `before`. Lignes identiques (même objet,
    même prix) = plusieurs positions possibles : on garde la plus proche du déplacement
    précédent (un cran de molette défile toujours pareil), sinon la plus petite.
    None = introuvable (défilé de plus de ~6 lignes d'un coup)."""
    import cv2
    a = cv2.cvtColor(before, cv2.COLOR_BGR2GRAY) if before.ndim == 3 else before
    b = cv2.cvtColor(after, cv2.COLOR_BGR2GRAY) if after.ndim == 3 else after
    if a.shape != b.shape:
        return None
    if np.abs(a.astype(int) - b.astype(int)).mean() < 0.5:
        return 0
    h = a.shape[0]
    band_y, band_h = step, min(2 * step, h - step - 1)
    if band_h < step // 2:
        return None
    band = b[band_y:band_y + band_h]
    res = cv2.matchTemplate(a[band_y:], band, cv2.TM_CCOEFF_NORMED)[:, 0]
    best = float(res.max())
    if best < 0.8:
        return None
    cands = [int(i) for i in np.where(res >= best - 0.03)[0]]
    # positions voisines = même pic : garder le centre de chaque pic
    peaks, cur = [], [cands[0]]
    for c in cands[1:]:
        if c - cur[-1] <= 2:
            cur.append(c)
        else:
            peaks.append(cur)
            cur = [c]
    peaks.append(cur)
    ds = [max(p, key=lambda i: res[i]) for p in peaks]
    if expected:
        return min(ds, key=lambda d: (abs(d - expected), d))
    return min(ds)


def beep(kind: str, cfg: Config) -> None:
    if not cfg.sound or not IS_WINDOWS:
        return
    import winsound
    freq, dur = {"ok": (1200, 60), "warn": (600, 160), "error": (300, 250)}.get(kind, (800, 80))
    threading.Thread(target=winsound.Beep, args=(freq, dur), daemon=True).start()


# --------------------------------------------------------------------------
# Historique
# --------------------------------------------------------------------------
_hist_lock = threading.Lock()


def log_history(action: str, lot: Optional[int], selected: Optional[int],
                reading: Optional[Reading], new_price: Optional[int],
                status: str, cfg: Config, path: Optional[Path] = None) -> None:
    path = path or HISTORY_PATH
    with _hist_lock:
        try:
            if path.exists():
                with path.open("r", encoding="utf-8", newline="") as f:
                    header = next(csv.reader(f), None)
                if header != HISTORY_HEADER:  # ancien format -> archivé
                    path.replace(path.with_name(path.stem + f"_old_{int(time.time())}.csv"))
            new_file = not path.exists()
            with path.open("a", encoding="utf-8", newline="") as f:
                w = csv.writer(f)
                if new_file:
                    w.writerow(HISTORY_HEADER)
                now = time.time()
                w.writerow([int(now), time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(now)),
                            action, lot if lot else "", selected if selected else "",
                            reading.value if reading and reading.value is not None else "",
                            f"{reading.confidence:.0f}" if reading else "",
                            new_price if new_price is not None else "",
                            status, cfg.undercut_mode, cfg.undercut_value, cfg.rounding])
        except OSError as e:
            print(f"[Historique] Écriture impossible: {e}")


# --------------------------------------------------------------------------
# Moteur : lecture -> contrôles -> saisie
# --------------------------------------------------------------------------
@dataclass
class Result:
    lot: Optional[int]
    level: str              # "ok" | "warn" | "error"
    message: str
    screen: ScreenRead = field(default_factory=ScreenRead)
    new_price: Optional[int] = None
    hint: str = ""          # texte court pour la popup
    floored_top: Optional[int] = None  # prix concurrent ignoré car sous le plancher


class PriceEngine:
    """Utilisé par la GUI et la CLI. Thread-safe (un seul traitement à la fois)."""

    def __init__(self, cfg: Config, debug_dir: Optional[Path] = None):
        self.cfg = cfg
        self.debug_dir = debug_dir
        self.paused = False
        self._lock = threading.Lock()
        self._pending: Optional[Tuple[int, int, float]] = None  # (lot, prix, t) à confirmer
        self._first_point: Dict[str, Tuple[Point, float]] = {}
        self._my_last: Dict[int, Tuple[int, float]] = {}  # lot -> (prix mis en vente, t)
        self.last_anchor_msg = ""  # dernier message du repère HDV (lu puis vidé par l'interface)

    # ---- calibration ----
    def calibrate_rect(self, name: str, pos: Optional[Point] = None) -> Tuple[str, object]:
        """Zone en 2 appuis. name = "table" | "qty" | "avg" | "count".
        Retourne ("first", point) puis ("done", region)."""
        p = pos or mouse_position()
        first = self._first_point.get(name)
        if first is None or time.time() - first[1] > 30:
            self._first_point[name] = (p, time.time())
            return "first", p
        del self._first_point[name]
        region = rect_from_points(first[0], p)
        setattr(self.cfg, f"{name}_region", list(region))
        if name == "anchor":
            save_anchor(grab_screen(region))
        self.cfg.save()
        return "done", region

    # ---- repère : l'HDV a bougé -> toutes les zones suivent
    def _reanchor(self) -> Optional[Tuple[int, int]]:
        """Si le titre « Hôtel de vente » n'est plus à sa place, le retrouve à l'écran et
        décale TOUTES les zones et tous les points d'autant. Retourne le décalage (dx, dy)
        appliqué, ou None (pas de repère, pas bougé, ou introuvable)."""
        cfg = self.cfg
        if not cfg.anchor_region:
            return None
        tpl = load_anchor()
        if tpl is None:
            return None
        x, y, w, h = cfg.anchor_region
        try:
            if anchor_score(grab_screen((x, y, w, h)), tpl) >= ANCHOR_OK:
                return None                       # pas bougé (cas normal, ~1 ms)
            found = find_anchor(tpl)
        except Exception as e:
            self.last_anchor_msg = f"Repère HDV : erreur ({e})"
            return None
        if found is None:
            self.last_anchor_msg = "Repère HDV introuvable : HDV fermé ou caché ? Zones inchangées."
            return None
        dx, dy = found[0] - x, found[1] - y
        if dx == 0 and dy == 0:
            return None
        shift_zones(cfg, dx, dy)
        cfg.save()
        self.last_anchor_msg = f"HDV déplacé de ({dx:+d}, {dy:+d}) px : zones recalées."
        return dx, dy

    def calibrate_point(self, name: str, pos: Optional[Point] = None) -> Point:
        """name = "price_field" | "sell_button" | "modify_button"."""
        x, y = pos or mouse_position()
        setattr(self.cfg, name, [x, y])
        if name == "price_field":
            self.cfg.click_field = True
        self.cfg.save()
        return x, y

    def calibrate_rows(self, pos: Optional[Point] = None) -> Tuple[str, object]:
        """2 appuis : centre de la 1re ligne visible, puis de la 2e -> position + hauteur de ligne."""
        p = pos or mouse_position()
        first = self._first_point.get("rows")
        if first is None or time.time() - first[1] > 30:
            self._first_point["rows"] = (p, time.time())
            return "first", p
        del self._first_point["rows"]
        step = abs(p[1] - first[0][1])
        if step < 10:
            return "error", "les 2 lignes sont trop proches : clique sur la 1re puis la 2e ligne"
        self.cfg.relist_row, self.cfg.relist_step = list(first[0]), int(step)
        self.cfg.save()
        return "done", (tuple(first[0]), step)

    # ---- mes ventes : mise à jour des prix ----
    def relist(self) -> Result:
        """Vente sélectionnée dans « mes ventes » : si quelqu'un est moins cher, nouveau prix
        + « Modifier ». Si le moins cher, c'est toi : rien."""
        if not self._lock.acquire(blocking=False):
            return Result(None, "warn", "Lecture déjà en cours, ignoré.")
        try:
            self._reanchor()
            return self._relist()
        except Exception as e:
            return Result(None, "error", f"Erreur: {e}", hint="Erreur")
        finally:
            self._lock.release()

    def relist_all(self) -> Result:
        if not self._lock.acquire(blocking=False):
            return Result(None, "warn", "Lecture déjà en cours, ignoré.")
        try:
            self._reanchor()
            return self._relist_all()
        except Exception as e:
            return Result(None, "error", f"Erreur: {e}", hint="Erreur")
        finally:
            self._lock.release()

    def _relist(self, auto: bool = False) -> Result:
        """auto=True (boucle) : jamais de forçage, une lecture suspecte arrête la boucle."""
        cfg = self.cfg
        tag = "MAJ"
        if not cfg.table_region or not cfg.qty_region:
            return Result(None, "error", f"[{tag}] Calibre d'abord le tableau et la quantité.",
                          hint="Calibration manquante")
        if not mine_regions(cfg):
            return Result(None, "error",
                          f"[{tag}] Champ « Prix du lot » non calibré ({cfg.hotkeys['calibrate_field']}).",
                          hint="Calibre Prix du lot")
        # Après un clic sur une vente, le panneau s'affiche tout de suite mais le tableau
        # « Actuellement en vente » arrive du serveur un peu après (vide entre-temps) :
        # on relit jusqu'à ~1 s tant que quantité ou prix du lot manquent.
        for attempt in range(RELIST_READ_TRIES):
            sr = read_screen(cfg, self.debug_dir, with_mine=True)
            if sr.selected is not None and sr.prices.get(sr.selected) is not None:
                break
            if attempt < RELIST_READ_TRIES - 1:
                time.sleep(0.12)
        mine = sr.mine_r
        if mine is None or mine.value is None or mine.confidence < cfg.min_confidence:
            alone = read_mine(cfg)  # 2e lecture seule, plus grande : garder la plus sûre
            if mine is None or alone.confidence > mine.confidence:
                mine = alone
        lot = sr.selected
        if lot is None:
            return Result(None, "error", f"[{tag}] Quantité illisible (lu : {sr.selected_raw!r}).", sr,
                          hint="Quantité illisible")
        if mine.value is None:
            return Result(lot, "error", f"[{tag}] Ton prix illisible (zone {cfg.hotkeys['calibrate_mine']}).",
                          sr, hint="Ton prix illisible")
        top = sr.prices.get(lot)
        if top is None or top.value is None:
            return Result(lot, "error", f"[{tag}] Lot {lot} : aucun prix lu dans le tableau.", sr,
                          hint="Aucun prix lu")
        head = f"[{tag}] Lot {lot} | ton prix {mine.value} | moins cher {top.value}"
        if top.value >= mine.value:
            msg = "déjà le moins cher" if top.value == mine.value else "ton prix est déjà plus bas"
            return Result(lot, "ok", f"{head} | {msg}, rien à faire", sr, mine.value, hint="Déjà le moins cher")

        last = self._my_last.get(lot)
        own = last is not None and top.value == last[0] and time.time() - last[1] <= cfg.own_price_ttl
        new_p = top.value if own else compute_price(top.value, cfg.undercut_mode, cfg.undercut_value,
                                                    cfg.rounding, cfg.min_price)
        # ---- plancher : un concurrent qui brade ne fait pas baisser sous FLOOR_RATIO × prix moyen
        fp = floor_price(lot, sr.avg, cfg.floor_ratio) if cfg.floor_mode != "stop" else None
        floored = fp is not None and new_p < fp
        if floored:
            if cfg.floor_mode == "keep":
                return Result(lot, "ok", f"{head} | sous le plancher ({fp}) : ton prix gardé, rien à faire",
                              sr, mine.value, hint="Plancher : prix gardé", floored_top=top.value)
            new_p = fp
            if mine.value <= new_p:
                return Result(lot, "ok", f"{head} | déjà au plancher ({fp}), rien à faire", sr,
                              mine.value, hint="Déjà au plancher", floored_top=top.value)
        problems = []
        for name, r in (("tableau", top), ("ton prix", mine)):
            if r.confidence < cfg.min_confidence:
                problems.append(f"confiance OCR {name} {r.confidence:.0f} < {cfg.min_confidence:.0f}")
        incoh = check_coherence(lot, sr.values, cfg.max_ratio)
        if incoh:
            problems.append(incoh)
        unit = new_p / lot
        if (cfg.floor_mode == "stop" and cfg.min_avg_ratio > 0 and sr.avg
                and unit < sr.avg * cfg.min_avg_ratio):
            problems.append(f"{unit:.0f}/u < {cfg.min_avg_ratio:.0%} du prix moyen ({sr.avg}/u)")
        if new_p < mine.value / cfg.max_ratio:
            problems.append(f"baisse énorme : {mine.value} -> {new_p}")
        if floored:  # le concurrent brade : son prix ne sert pas, la cohérence entre lots non plus
            problems = [p for p in problems if not p.startswith("prix unitaire")]

        prefix = (f"{head} -> {new_p}{' (aligné sur ton autre vente)' if own else ''}"
                  f"{f' (plancher {cfg.floor_ratio:.0%} du prix moyen {sr.avg})' if floored else ''}")
        now = time.time()
        forced = (not auto and self._pending is not None and self._pending[:2] == (-lot, new_p)
                  and now - self._pending[2] <= cfg.confirm_window)
        if problems and not forced:
            self._pending = (-lot, new_p, now)   # lot négatif : ne pas confondre avec F1
            input_price(new_p, cfg, paste=False)
            log_history("read", lot, lot, top, new_p, "relist_suspect", cfg)
            return Result(lot, "warn", f"{prefix} | SUSPECT ({'; '.join(problems)}). Copié seulement."
                          + ("" if auto else f" Ré-appuie dans {cfg.confirm_window:.0f}s pour forcer."),
                          sr, new_p, hint="Suspect")
        self._pending = None
        input_price(new_p, cfg, paste=True, validate=False)
        time.sleep(0.1)
        mine_box = mine_regions(cfg)[0]
        before = grab_screen(mine_box)
        press_modify(cfg)
        self._my_last[lot] = (new_p, time.time())
        wait_change(mine_box, before, cfg.relist_delay)
        # Après « Modifier », le jeu désélectionne la vente : panneau vide (« Veuillez
        # sélectionner un objet ») = modification acceptée. Ancien prix encore affiché = échec.
        check = read_mine(cfg)
        confirmed = ""
        if check.value is not None and check.confidence >= cfg.min_confidence and cfg.relist_confirm_enter:
            # Panneau pas vidé : souvent la fenêtre de confirmation du changement de prix.
            # Entrée la valide (sans elle, la vente reste sélectionnée).
            before = grab_screen(mine_box)
            press_enter()
            wait_change(mine_box, before, cfg.relist_delay)
            check = read_mine(cfg)
            confirmed = " (confirmation validée)"
        if check.value is None or check.confidence < cfg.min_confidence:
            log_history("relist", lot, lot, top, new_p, "forced" if forced else "modified", cfg)
            return Result(lot, "ok", f"{prefix} | modifié{' (forcé)' if forced else ''}{confirmed}",
                          sr, new_p, hint=f"Modifié : {new_p}")
            return Result(lot, "ok", f"{prefix} | modifié{' (forcé)' if forced else ''}", sr, new_p,
                          hint=f"Modifié : {new_p}")
        if check.value != new_p:
            log_history("relist", lot, lot, top, new_p, "unconfirmed", cfg)
            return Result(lot, "warn", f"{prefix} | modification NON confirmée (lu ensuite : "
                          f"{check.value if check.value is not None else '?'})", sr, new_p,
                          hint="Modif. non confirmée")
        log_history("relist", lot, lot, top, new_p, "forced" if forced else "modified", cfg)
        return Result(lot, "ok", f"{prefix} | modifié{' (forcé)' if forced else ''}{confirmed}",
                      sr, new_p, hint=f"Modifié : {new_p}")

    def _page_rows(self, shift: int, base: int) -> List[Tuple[int, int]]:
        """Lignes à cliquer : détectées à l'écran (centres exacts) si possible, sinon
        calculées depuis le défilement mesuré. Numéro global = position depuis `base`
        (centre de la 1re ligne au départ) + défilement cumulé."""
        cfg = self.cfg
        x0, y0 = cfg.relist_row
        step = cfg.relist_step
        top = y0 - step // 2 - step // 3
        strip = grab_screen((x0 - 60, top, 240, step * cfg.relist_rows + 2 * (step // 3)))
        ys = detect_rows(strip, top, step)
        if len(ys) >= 2 and all(abs((b - a) - step) <= 0.25 * step for a, b in zip(ys, ys[1:])):
            return [(y, int(round((y - base + shift) / step))) for y in ys]
        return self._visible_rows(shift + (y0 - base))

    def _visible_rows(self, shift: int) -> List[Tuple[int, int]]:
        """Lignes cliquables après un défilement de `shift` px depuis le haut :
        [(y écran du centre, numéro global de la ligne)]. Le jeu défile au pixel près :
        une ligne trop coupée en haut est ignorée (elle a déjà été traitée)."""
        cfg = self.cfg
        x0, y0 = cfg.relist_row
        step = cfg.relist_step
        offset = shift % step
        y = y0 - offset
        if offset > 0.35 * step:
            y += step
        y_max = y0 + (cfg.relist_rows - 1) * step + 0.3 * step
        rows = []
        while y <= y_max:
            rows.append((int(y), int(round((y - y0 + shift) / step))))
            y += step
        return rows

    def _scroll_page(self, box: Region, target: int) -> Tuple[int, Optional[str]]:
        """Molette cran par cran en MESURANT le déplacement réel de la liste, jusqu'à
        `target` px (≈ une page moins une ligne). Retourne (px défilés, erreur).
        0 px après 2 crans = bas de la liste."""
        cfg = self.cfg
        x0, y0 = cfg.relist_row
        anchor = (x0, y0 + cfg.relist_step)
        prev = grab_screen(box)
        total, zeros, per_notch, notches = 0, 0, None, 0
        max_jump = 5 * cfg.relist_step     # au-delà, la mesure ne retrouve plus la liste
        while notches < cfg.relist_scroll_max:
            # 1er essai : 1 cran pour mesurer ; ensuite autant de crans que nécessaire d'un coup
            n = 1
            if per_notch:
                n = max(1, min(int((target - total) // per_notch), int(max_jump // per_notch)))
            scroll_at(anchor, n)
            notches += n
            time.sleep(0.12)
            img = grab_screen(box)
            d = measure_shift(prev, img, cfg.relist_step, per_notch * n if per_notch else None)
            if d is None:
                return total, "défilement non suivi (liste méconnaissable entre deux crans)"
            prev = img
            if d == 0:
                zeros += 1
                if zeros >= 2:
                    break
                continue
            zeros, total = 0, total + d
            per_notch = per_notch or d / n
            if total >= target:
                break
        time.sleep(cfg.relist_delay)       # fin d'une éventuelle animation
        img = grab_screen(box)
        d = measure_shift(prev, img, cfg.relist_step, None)
        if d is None:
            return total, "défilement non suivi (animation)"
        return total + d, None

    def _relist_all(self) -> Result:
        """Parcourt la liste « mes ventes » : clic sur chaque ligne visible, mise à jour,
        puis défilement mesuré et lignes suivantes. Arrêt : bas de la liste, lecture
        suspecte, modification non confirmée, pause, RELIST_MAX lignes."""
        cfg = self.cfg
        if not cfg.relist_auto:
            return Result(None, "warn", "[MAJ] Mode boucle désactivé (interrupteur « toute la liste » "
                          f"ou RELIST_AUTO). Utilise {cfg.hotkeys['relist']} ligne par ligne.",
                          hint="Boucle désactivée")
        if not cfg.relist_row or cfg.relist_step <= 0:
            return Result(None, "error", f"[MAJ] Lignes non calibrées ({cfg.hotkeys['calibrate_rows']} ×2).",
                          hint="Calibre les lignes")
        x0, y0 = cfg.relist_row
        step = cfg.relist_step
        # bande de la liste (noms, durée, lot, prix ; sans la barre de défilement)
        box = (x0 - 80, y0 - step // 2, 260, step * cfg.relist_rows)
        back = mouse_position()
        done = changed = same = pages = shift = 0
        seen = -1                     # plus grand numéro global de ligne déjà traité
        # Origine = 1re ligne visible MAINTENANT (la liste a pu être défilée à la main).
        first = self._page_rows(0, y0)
        base = first[0][0] if first else y0
        rows0 = self._page_rows(0, base)
        # Souris posée sur une ligne de la liste : on commence à cette ligne (reprise).
        mx, my = back
        start_note = ""
        if rows0 and x0 - 150 <= mx <= x0 + 420 and rows0[0][0] - step // 2 <= my <= rows0[-1][0] + step // 2:
            y_s, g_s = min(rows0, key=lambda r: abs(r[0] - my))
            seen = g_s - 1
            start_note = f", départ ligne sous la souris"
        last_click = None
        ok_rows: List[np.ndarray] = []  # images de lignes déjà au bon prix (même objet, même prix)
        bad: List[str] = []           # lignes douteuses laissées telles quelles
        fails = 0                     # lignes douteuses consécutives
        skipped = 0
        mine_box = (mine_regions(cfg) or [None])[0]
        stats0 = dict(ENGINE_STATS)
        stop = "fin de la liste"
        try:
            while True:
                restart = True
                while restart:
                    restart = False
                    rows = self._page_rows(shift, base)   # relu à chaque fois : la liste a pu bouger
                    for y, g in rows:
                        if g <= seen:
                            continue
                        if self.paused:
                            stop = "pause"
                            raise StopIteration
                        if done >= cfg.relist_max:
                            stop = f"limite {cfg.relist_max} lignes"
                            raise StopIteration
                        # Ligne identique (même objet, même prix) à une ligne déjà au bon prix :
                        # même résultat garanti -> pas de clic ni de lecture.
                        row_img = grab_screen((x0 - 90, y - step // 2 + 4, 430, step - 8))
                        if any(_same_row(row_img, r) for r in ok_rows):
                            same += 1
                            skipped += 1
                            seen = max(seen, g)
                            continue
                        before = grab_screen(mine_box) if mine_box else None
                        click_at((x0, y))
                        last_click = (x0, y)
                        wait_change(mine_box, before, cfg.relist_delay)
                        res = self._relist(auto=True)
                        if res.level != "ok" and "NON confirmée" not in res.message:
                            time.sleep(0.15)          # lecture douteuse : on relit une fois
                            res = self._relist(auto=True)
                        done += 1
                        if res.level != "ok":
                            if "NON confirmée" in res.message:
                                stop = f"ligne {g + 1} : {res.message}"  # sécurité : arrêt
                                raise StopIteration
                            # ligne douteuse : on n'y touche pas et on passe à la suivante
                            bad.append(f"ligne {g + 1} : {res.message}")
                            fails += 1
                            seen = max(seen, g)
                            if fails >= 3:
                                stop = f"3 lignes douteuses de suite (calibration ?) : {res.message}"
                                raise StopIteration
                            continue
                        fails = 0
                        if "modifié" in res.message:
                            # La ligne modifiée change de place : la liste se décale. On reprend
                            # À CETTE POSITION (relue), lignes repérées à nouveau à l'écran.
                            changed += 1
                            seen = g - 1
                            restart = True
                            break
                        same += 1
                        seen = max(seen, g)
                        if len(ok_rows) < 200:
                            ok_rows.append(row_img)
                # Défilement d'une demi-page (RELIST_SCROLL_PAGE) et relecture de la dernière
                # ligne traitée : une erreur de mesure d'une ligne ne fait jamais sauter
                # d'objet ; les lignes déjà vues ne sont pas recliquées (numéro global).
                target = max(step, int(len(rows) * cfg.relist_scroll_page) * step)
                moved, err = self._scroll_page(box, target)
                if err:
                    stop = err
                    break
                if moved <= 0:
                    break  # la liste ne bouge plus : en bas
                shift += moved
                seen -= 1
                pages += 1
        except StopIteration:
            pass
        finally:
            try:
                import pyautogui
                # Arrêt en cours de route : souris laissée sur la dernière ligne traitée,
                # Ctrl+F3 reprendra là. Fin de liste : souris remise à sa place.
                if stop == "fin de la liste" or last_click is None:
                    pyautogui.moveTo(*back)
                else:
                    pyautogui.moveTo(*last_click)
            except Exception:
                pass
        level = "ok" if stop == "fin de la liste" and not bad else "warn"
        fast_n = ENGINE_STATS.get("chiffres", 0) - stats0.get("chiffres", 0)
        tess_n = ENGINE_STATS.get("tesseract", 0) - stats0.get("tesseract", 0)
        detail = f" | lecture rapide {fast_n}/{fast_n + tess_n}" if fast_n + tess_n else ""
        if bad:
            detail += f" | {len(bad)} ligne(s) douteuse(s) NON modifiée(s), à faire avec F3 : " + " / ".join(bad[:5])
        return Result(None, level, f"[MAJ TOUT] {done + skipped} lignes vues ({pages + 1} pages, "
                      f"{skipped} identiques sautées{start_note}) : "
                      f"{changed} modifiées, {same} déjà au bon prix | arrêt : {stop}{detail}",
                      hint=f"{changed} modifiées")

    # ---- actions ----
    def sell(self, optimize: bool = False) -> Result:
        if not self._lock.acquire(blocking=False):
            return Result(None, "warn", "Lecture déjà en cours, ignoré.")
        try:
            self._reanchor()
            return self._sell(optimize)
        except Exception as e:  # ne jamais tuer le thread des hotkeys
            return Result(None, "error", f"Erreur: {e}", hint="Erreur")
        finally:
            self._lock.release()

    def sell_all(self) -> Result:
        """Met en vente la quantité affichée, puis recommence au MÊME prix tant que :
        - la quantité affichée ne change pas (sinon stock épuisé / passé sous le lot) ;
        - le prix en tête du tableau pour ce lot est le tien (sinon autre objet ou concurrent) ;
        - pas de pause (Ctrl+Alt+P) et moins de SELL_ALL_MAX ventes."""
        if not self._lock.acquire(blocking=False):
            return Result(None, "warn", "Lecture déjà en cours, ignoré.")
        try:
            self._reanchor()
            return self._sell_all()
        except Exception as e:
            return Result(None, "error", f"Erreur: {e}", hint="Erreur")
        finally:
            self._lock.release()

    def _sell_all(self) -> Result:
        cfg = self.cfg
        check = cfg.verify_count and bool(cfg.count_region)
        base = read_counter(cfg) if check else None
        if base and base[0] >= base[1]:
            return Result(None, "error", f"[TOUT] Plus de place : {base[0]}/{base[1]} lots en vente.",
                          hint="HDV plein")
        first = self._sell(False, force_validate=True)
        if first.level != "ok" or "mis en vente" not in first.message:
            return first  # lecture suspecte / erreur : on ne boucle pas
        lot, price = first.lot, first.new_price
        dumper = first.floored_top  # prix au plancher : en tête, ce sera toujours le brader
        segments = [[lot, price, 1]]          # [lot, prix, nombre] — ex. 4×10 puis 2×1
        n, stop = 1, "limite atteinte"
        sr = first.screen
        unverified = False
        while True:
            time.sleep(cfg.sell_all_delay)
            if base:
                err, full = self._check_counter(base, n)
                if err:
                    stop = err
                    break
                if full:
                    stop = f"plus de place ({base[0] + n}/{base[1]} lots)"
                    break
            elif check:
                unverified = True
            if n >= cfg.sell_all_max:
                break
            if self.paused:
                stop = "pause"
                break
            sr = read_screen(cfg, self.debug_dir)
            if sr.selected is None:
                stop = "stock épuisé"
                break
            top = sr.prices.get(lot)
            if top is None or top.value not in (price, dumper):
                # ta dernière vente n'est plus en tête de son lot : autre objet ou concurrent
                stop = f"prix en tête du lot {lot} : {top.value if top else '?'} ≠ {price}"
                break
            if sr.selected == lot:
                press_validate(cfg)  # même lot, même prix : le prix est encore affiché -> Entrée
                self._my_last[lot] = (price, time.time())
                log_history("sell", lot, sr.selected, top, price, "sell_all", cfg)
                segments[-1][2] += 1
                n += 1
                continue
            if sr.selected > lot:
                stop = f"quantité passée à {sr.selected}"  # jamais vers un lot plus grand
                break
            # Quantité plus petite (ex. 42 objets : 4×10 vendus, il en reste 2 -> lot 1).
            # Même objet confirmé (notre prix est en tête de l'ancien lot) : nouveau prix, mêmes garde-fous.
            res = self._sell(False, force_validate=True, screen=sr)
            if res.level != "ok" or "mis en vente" not in res.message:
                stop = f"lot {sr.selected} non vendu ({res.message})"
                break
            lot, price, dumper = res.lot, res.new_price, res.floored_top
            segments.append([lot, price, 1])
            n += 1
        detail = " + ".join(f"{c}×{l} à {p}" for l, p, c in segments)
        if base:
            detail += f" | compteur {base[0]}→{base[0] + n} ✓" if "non confirmée" not in stop else ""
        elif unverified:
            detail += " | compteur illisible, ventes non vérifiées"
        level = "warn" if "non confirmée" in stop else "ok"
        return Result(lot, level, f"[TOUT] {detail} | arrêt : {stop}", sr, price,
                      hint=f"{n} lot{'s' if n > 1 else ''} mis en vente")

    def _check_counter(self, base: Tuple[int, int], n: int) -> Tuple[Optional[str], bool]:
        """Après n ventes, le compteur doit valoir EXACTEMENT base + n (une valeur plus haute
        = chiffre mal lu ; plus basse = vente ratée ou un de tes lots vendu entre-temps).
        Une 2e lecture si le jeu est lent. Retourne (erreur, plein)."""
        expected = base[0] + n
        for attempt in range(2):
            c = read_counter(self.cfg)
            if c and c[0] == expected and c[1] == base[1]:
                return None, c[0] >= c[1]
            if attempt == 0:
                time.sleep(max(0.3, self.cfg.sell_all_delay))
        got = f"{c[0]}/{c[1]}" if c else "illisible"
        return f"vente non confirmée (compteur {got}, attendu {expected}/{base[1]})", False

    def read_only(self) -> ScreenRead:
        with self._lock:
            self._reanchor()
            sr = read_screen(self.cfg, self.debug_dir)
            sr.listed = read_counter(self.cfg)
            sr.mine = read_mine(self.cfg).value if mine_regions(self.cfg) else None
            return sr

    def _sell(self, optimize: bool, force_validate: bool = False,
              screen: Optional[ScreenRead] = None) -> Result:
        cfg = self.cfg
        tag = "OPT" if optimize else "VENTE"
        if not cfg.table_region:
            return Result(None, "error", f"Tableau non calibré ({cfg.hotkeys['calibrate_table']} ×2).",
                          hint="Calibre le tableau")
        sr = screen if screen is not None else read_screen(cfg, self.debug_dir)
        prices = sr.values
        sel = sr.selected

        # ---- lot visé
        if optimize:
            # Le jeu affiche par défaut le plus grand lot possible avec ton stock
            # (moins de 10 objets -> 1, 10 à 99 -> 10, ...) : les lots plus grands sont impossibles.
            possible = {l: p for l, p in prices.items() if sel is None or l <= sel}
            lot = pick_best_lot(possible, cfg.tie_tolerance)
            if lot is None and sel is not None:
                lot = sel  # personne ne vend les lots possibles : prix estimé plus bas
            if lot is None:
                return Result(None, "error", f"[{tag}] Aucun prix lu dans le tableau.", sr,
                              hint="Aucun prix lu")
            if sel is not None and sel != lot:
                p = prices.get(lot)
                new_p = compute_price(p, cfg.undercut_mode, cfg.undercut_value, cfg.rounding, cfg.min_price)
                return Result(lot, "warn",
                              f"[{tag}] Meilleur lot : {lot} (quantité affichée : {sel}). "
                              f"Change la quantité puis ré-appuie.", sr, new_p,
                              hint=f"Choisis quantité {lot}")
        else:
            if not cfg.qty_region:
                return Result(None, "error",
                              f"Zone Quantité non calibrée ({cfg.hotkeys['calibrate_qty']} ×2).", sr,
                              hint="Calibre la quantité")
            if sel is None:
                return Result(None, "error",
                              f"[{tag}] Quantité illisible (lu : {sr.selected_raw!r}).", sr,
                              hint="Quantité illisible")
            lot = sel

        # ---- prix de référence
        problems = []
        r = sr.prices.get(lot)
        if r is None or r.value is None:
            est = derive_price(lot, prices)
            if est is None:
                log_history("read", lot, sel, None, None, "no_price", cfg)
                return Result(lot, "error", f"[{tag}] Aucun prix en vente.", sr, hint="Aucun prix")
            conf = min((x.confidence for x in sr.prices.values()), default=-1)
            r = Reading(est, conf, "estimé")
            problems.append(f"personne ne vend le lot {lot}, prix estimé depuis les autres lots")
        mine = self._my_last.get(lot)
        own = (r.raw != "estimé" and mine is not None and r.value == mine[0]
               and time.time() - mine[1] <= cfg.own_price_ttl)
        if own:  # le moins cher, c'est toi : on garde ton prix, pas d'undercut
            new_p = r.value
        else:
            new_p = compute_price(r.value, cfg.undercut_mode, cfg.undercut_value, cfg.rounding,
                                  cfg.min_price)

        # ---- garde-fous
        if r.confidence < cfg.min_confidence:
            problems.append(f"confiance OCR {r.confidence:.0f} < {cfg.min_confidence:.0f}")
        if r.raw != "estimé":
            incoh = check_coherence(lot, prices, cfg.max_ratio)
            if incoh:
                problems.append(incoh)
        if sel is None:
            problems.append("quantité non vérifiée")
        fp = floor_price(lot, sr.avg, cfg.floor_ratio) if cfg.floor_mode != "stop" else None
        floored = fp is not None and new_p < fp
        if floored:  # concurrent qui brade : on vend au plancher, pas sous son prix
            new_p = fp
            problems = [p for p in problems if not p.startswith("prix unitaire")]
        unit = new_p / lot
        if (cfg.floor_mode == "stop" and cfg.min_avg_ratio > 0 and sr.avg
                and unit < sr.avg * cfg.min_avg_ratio):
            problems.append(f"{unit:.0f}/u < {cfg.min_avg_ratio:.0%} du prix moyen ({sr.avg}/u)")

        prefix = (f"[{tag}] Lot {lot} | Lu: {r.value} -> {new_p}{' (ton prix)' if own else ''}"
                  f"{f' (plancher {cfg.floor_ratio:.0%} du prix moyen {sr.avg})' if floored else ''}")
        now = time.time()
        forced = (self._pending is not None and self._pending[:2] == (lot, new_p)
                  and now - self._pending[2] <= cfg.confirm_window)

        if problems and not forced:
            self._pending = (lot, new_p, now)
            input_price(new_p, cfg, paste=False)
            log_history("read", lot, sel, r, new_p, "suspect", cfg)
            return Result(lot, "warn",
                          f"{prefix} | SUSPECT ({'; '.join(problems)}). Copié seulement. "
                          f"Ré-appuie dans {cfg.confirm_window:.0f}s pour forcer.",
                          sr, new_p, hint="Suspect — ré-appuie pour forcer")

        self._pending = None
        paste = cfg.auto_paste or forced or force_validate
        validate = (cfg.auto_validate or force_validate) and not forced and not problems
        done = input_price(new_p, cfg, paste=paste, validate=validate)
        if paste:
            self._my_last[lot] = (new_p, time.time())
        log_history("sell" if paste else "copy", lot, sel, r, new_p,
                    "forced" if forced else done, cfg)
        return Result(lot, "ok", f"{prefix} | {done}{' (forcé)' if forced else ''}",
                      sr, new_p, hint=done.capitalize(), floored_top=r.value if floored else None)
