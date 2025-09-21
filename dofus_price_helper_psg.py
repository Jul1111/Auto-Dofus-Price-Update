#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Dofus Price Helper — PySimpleGUI + Presets + Auto-Paste + Optimizer + CSV
--------------------------------------------------------------------------
- GUI moderne avec PySimpleGUI.
- Zones PRIX fixes (lots 1/10/100) calibrées à la souris.
- Undercut (fixe / %) + options d’arrondi.
- Aperçu visuel des captures (par lot).
- Système de PRÉSETS (sauver/charger/supprimer) pour gérer plusieurs profils (résos, comptes).
- Collage automatique (Ctrl+V) optionnel via 'keyboard'.
- Optimiseur: lit 1/10/100, évalue prix/unité et recommande le lot le plus rentable.
- Historique CSV des collages.

Dépendances :
  pip install PySimpleGUI mss pyautogui pytesseract opencv-python numpy pyperclip pillow keyboard
+ Installer Tesseract (Windows : https://github.com/UB-Mannheim/tesseract/wiki)
  et ajuster TESSERACT_CMD si nécessaire.
"""

import os, re, json, time, io, csv
from typing import Optional, Tuple, Dict

import numpy as np
import cv2
import mss
import pyautogui
import pytesseract
import pyperclip
from PIL import Image

import PySimpleGUI as sg

# keyboard est optionnel : on gère le fallback si non dispo
try:
    import keyboard  # pour Ctrl+V auto
    KEYBOARD_AVAILABLE = True
except Exception:
    KEYBOARD_AVAILABLE = False

# ---------------- CONFIG ----------------
TESSERACT_CMD = r"C:\Program Files\Tesseract-OCR\tesseract.exe"  # adapte si besoin
CONFIG_FILE   = "dofus_price_helper_config.json"
HISTORY_CSV   = "dofus_price_history.csv"

# taille de la zone capturée autour du centre du prix
PRICE_W = 150
ROW_H   = 40

# OCR
TESSERACT_CONFIG = r"--psm 6 -c tessedit_char_whitelist=0123456789"
SCALE = 2  # upscaling pour OCR

# Undercut
UNDERCUT_MODE  = "fixed"    # "fixed" | "percent"
UNDERCUT_VALUE = 1          # int (fixed) ou float (percent)
MIN_PRICE      = 1

# Rounding: "none" | "down_10" | "down_100" | "end_9"
ROUNDING       = "none"

# Regions par lot: { "1": (x,y,w,h) , "10": (...), "100": (...) }
PRICE_REGIONS: Dict[str, Optional[Tuple[int,int,int,int]]] = {"1": None, "10": None, "100": None}

# Préséts multi-profils : { "nom_preset": { "1":(x,y,w,h), "10":(...), "100":(...) } }
PRESETS: Dict[str, Dict[str, Optional[Tuple[int,int,int,int]]]] = {}

# Collage auto (Ctrl+V via 'keyboard')
AUTO_PASTE = True
# ---------------------------------------

def ensure_tesseract():
    if TESSERACT_CMD:
        pytesseract.pytesseract.tesseract_cmd = TESSERACT_CMD

def load_config():
    global PRICE_REGIONS, PRESETS, PRICE_W, ROW_H, UNDERCUT_MODE, UNDERCUT_VALUE, MIN_PRICE, ROUNDING, AUTO_PASTE
    if not os.path.exists(CONFIG_FILE):
        return
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            data = json.load(f) or {}
        if "PRICE_REGIONS" in data:
            PRICE_REGIONS = {k: (tuple(v) if v else None) for k, v in data["PRICE_REGIONS"].items()}
        if "PRESETS" in data:
            PRESETS = {name: {k: (tuple(v) if v else None) for k, v in pr.items()} for name, pr in data["PRESETS"].items()}
        PRICE_W        = int(data.get("PRICE_W", PRICE_W))
        ROW_H          = int(data.get("ROW_H", ROW_H))
        UNDERCUT_MODE  = data.get("UNDERCUT_MODE", UNDERCUT_MODE)
        UNDERCUT_VALUE = data.get("UNDERCUT_VALUE", UNDERCUT_VALUE)
        MIN_PRICE      = int(data.get("MIN_PRICE", MIN_PRICE))
        ROUNDING       = data.get("ROUNDING", ROUNDING)
        AUTO_PASTE     = bool(data.get("AUTO_PASTE", AUTO_PASTE))
    except Exception as e:
        print("[Config] load failed:", e)

def save_config():
    data = {
        "PRICE_REGIONS": {k: list(v) if v else None for k, v in PRICE_REGIONS.items()},
        "PRESETS": {name: {k: (list(v) if v else None) for k, v in pr.items()} for name, pr in PRESETS.items()},
        "PRICE_W": PRICE_W,
        "ROW_H": ROW_H,
        "UNDERCUT_MODE": UNDERCUT_MODE,
        "UNDERCUT_VALUE": UNDERCUT_VALUE,
        "MIN_PRICE": MIN_PRICE,
        "ROUNDING": ROUNDING,
        "AUTO_PASTE": AUTO_PASTE,
    }
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        print("[Config] saved.")
    except Exception as e:
        print("[Config] save failed:", e)

# --- capture & OCR ---
def grab_screen(region: Tuple[int,int,int,int]) -> np.ndarray:
    x, y, w, h = region
    with mss.mss() as sct:
        img = np.array(sct.grab({"left": x, "top": y, "width": w, "height": h}))
    return img[:, :, :3]  # BGR

def preprocess_for_ocr(img_bgr: np.ndarray) -> np.ndarray:
    gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
    up   = cv2.resize(gray, (gray.shape[1]*SCALE, gray.shape[0]*SCALE), interpolation=cv2.INTER_CUBIC)
    up   = cv2.bilateralFilter(up, d=7, sigmaColor=55, sigmaSpace=55)
    # Si UI claire sur fond sombre lit mal, essayer: THRESH_BINARY_INV
    _, th = cv2.threshold(up, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    return th

def ocr_number_from_image(img_bgr: np.ndarray) -> Optional[int]:
    pre = preprocess_for_ocr(img_bgr)
    txt = pytesseract.image_to_string(pre, config=TESSERACT_CONFIG)
    digits = re.sub(r"[^0-9]", "", txt)
    return int(digits) if digits else None

# --- undercut & arrondi ---
def smart_round(p: int, mode: str) -> int:
    if mode == "down_10":
        return (p // 10) * 10
    if mode == "down_100":
        return (p // 100) * 100
    if mode == "end_9":
        return max(9, (p // 10) * 10 + 9)
    return p

def compute_undercut(price: Optional[int], mode: str, value, rounding: str, min_price: int) -> Optional[int]:
    if price is None:
        return None
    if mode == "percent":
        try:
            v = float(value)
        except:
            v = 1.0
        new_p = int(round(price * (1 - v/100.0)))
    else:
        try:
            v = int(value)
        except:
            v = 1
        new_p = price - v
    new_p = smart_round(new_p, rounding)
    return max(min_price, new_p)

# --- utils GUI ---
def region_from_mouse(center_w: int, center_h: int) -> Tuple[int,int,int,int]:
    x, y = pyautogui.position()
    return (x - center_w//2, y - center_h//2, center_w, center_h)

def to_tk_image(img_bgr: np.ndarray, max_w=520) -> bytes:
    rgb = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)
    im  = Image.fromarray(rgb)
    if im.width > max_w:
        im = im.resize((max_w, int(max_w * im.height / im.width)))
    bio = io.BytesIO()
    im.save(bio, format="PNG")
    return bio.getvalue()

# --- Historique CSV ---
def log_history(action: str, lot: str, read_price: Optional[int], pasted_price: Optional[int], settings: dict):
    row = {
        "ts": int(time.time()),
        "action": action,           # "paste" | "auto_paste" | "recommend"
        "lot": lot,                 # "1" | "10" | "100" | "auto"
        "read_price": read_price if read_price is not None else "",
        "pasted_price": pasted_price if pasted_price is not None else "",
        "mode": settings.get("mode"),
        "value": settings.get("value"),
        "rounding": settings.get("rounding"),
        "min_price": settings.get("min_price"),
    }
    is_new = not os.path.exists(HISTORY_CSV)
    try:
        with open(HISTORY_CSV, "a", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=list(row.keys()))
            if is_new:
                writer.writeheader()
            writer.writerow(row)
    except Exception as e:
        print("[History] write failed:", e)

# --- Optimiseur ---
def pick_best_lot(p1: Optional[int], p10: Optional[int], p100: Optional[int]) -> Optional[str]:
    """
    Choisit le lot avec le meilleur prix/unité.
    Règles :
      - calcule u1, u10, u100 (ignore ceux non disponibles)
      - prend le max u*
      - si ex aequo (±1%), préfère le lot plus petit (1 > 10 > 100) pour turnover
    """
    units = []
    if p1   is not None:  units.append(("1",   p1/1.0))
    if p10  is not None:  units.append(("10",  p10/10.0))
    if p100 is not None:  units.append(("100", p100/100.0))
    if not units:
        return None
    # meilleur u
    best_lot, best_u = max(units, key=lambda t: t[1])

    # ex aequo ±1% → préférer plus petit lot
    def close(a,b,th=0.01):  # 1%
        return abs(a-b) <= max(a,b)*th

    # trie par u desc, puis lot priorité 1 > 10 > 100
    priority = {"1": 3, "10": 2, "100": 1}
    units_sorted = sorted(units, key=lambda t: (t[1], priority[t[0]]), reverse=True)
    top = units_sorted[0]
    if len(units_sorted) > 1 and close(units_sorted[0][1], units_sorted[1][1]):
        # si très proches, prends le plus petit (déjà géré par tri secondaire)
        return units_sorted[0][0]
    return best_lot

def read_price(lot: str) -> Optional[int]:
    region = PRICE_REGIONS.get(lot)
    if not region:
        return None
    img = grab_screen(region)
    return ocr_number_from_image(img)

def paste_value(val: int, auto: bool) -> bool:
    """Copie val dans le presse-papier et (si auto=True et keyboard dispo) envoie Ctrl+V."""
    pyperclip.copy(str(val))
    time.sleep(0.05)
    if auto and KEYBOARD_AVAILABLE:
        try:
            keyboard.press_and_release("ctrl+v")
            return True
        except Exception:
            return False
    return False

# ---------------- GUI BUILD ----------------
def make_layout():
    sg.theme("SystemDefault")

    left_col = [
        [sg.Text("Undercut"),
         sg.Combo(["fixed","percent"], default_value=UNDERCUT_MODE, key="-MODE-", size=(10,1)),
         sg.Text("Valeur"),
         sg.Input(str(UNDERCUT_VALUE), key="-VALUE-", size=(8,1))],
        [sg.Text("Arrondi"),
         sg.Combo(["none","down_10","down_100","end_9"], default_value=ROUNDING, key="-ROUND-", size=(10,1)),
         sg.Text("Min"),
         sg.Input(str(MIN_PRICE), key="-MIN-", size=(8,1))],

        [sg.Checkbox("Coller automatiquement (Ctrl+V)", key="-AUTO-", default=AUTO_PASTE, enable_events=True),
         sg.Text("(keyboard {})".format("OK" if KEYBOARD_AVAILABLE else "absent"), text_color="green" if KEYBOARD_AVAILABLE else "red")],

        [sg.Frame("Taille zone (prix)", [
            [sg.Text("Largeur"), sg.Input(str(PRICE_W), key="-W-", size=(6,1)),
             sg.Text("Hauteur"), sg.Input(str(ROW_H), key="-H-", size=(6,1))],
            [sg.Button("Sauver paramètres", key="-SAVE-PARAMS-")]
        ])],

        [sg.Frame("Calibration des zones (placez la souris au centre du prix)", [
            [sg.Button("Set zone Lot 1", key="-SET-1-")],
            [sg.Button("Set zone Lot 10", key="-SET-10-")],
            [sg.Button("Set zone Lot 100", key="-SET-100-")],
        ])],

        [sg.Frame("Préséts (multi-profils)", [
            [sg.Text("Nom"), sg.Input(key="-PRESET-NAME-", size=(18,1))],
            [sg.Button("Sauver prését", key="-PRESET-SAVE-"),
             sg.Button("Charger", key="-PRESET-LOAD-"),
             sg.Button("Supprimer", key="-PRESET-DEL-")],
            [sg.Text("Disponibles:"), sg.Combo(sorted([]), key="-PRESET-LIST-", size=(22,1))]
        ])],

        [sg.Frame("Actions", [
            [sg.Button("Lire 1", key="-READ-1-"), sg.Button("Coller 1", key="-PASTE-1-")],
            [sg.Button("Lire 10", key="-READ-10-"), sg.Button("Coller 10", key="-PASTE-10-")],
            [sg.Button("Lire 100", key="-READ-100-"), sg.Button("Coller 100", key="-PASTE-100-")],
            [sg.HSeparator()],
            [sg.Button("Optimiser (lire 1/10/100)", key="-OPTIMIZE-")],
            [sg.Button("Coller recommandé", key="-PASTE-BEST-")],
            [sg.HSeparator()],
            [sg.Button("Sauver config", key="-SAVE-CONFIG-"), sg.Button("Quitter", key="-QUIT-")],
        ])],

        [sg.StatusBar("Prêt.", key="-STATUS-")]
    ]

    right_col = [
        [sg.Text("Aperçu capture")],
        [sg.Image(key="-PREVIEW-")],
        [sg.Text("Recommandation :"), sg.Text("-", key="-RECO-")],
    ]

    layout = [
        [sg.Column(left_col, vertical_alignment="top", pad=((8,8),(8,8))),
         sg.VSeparator(),
         sg.Column(right_col, vertical_alignment="top", pad=((8,8),(8,8)))]
    ]
    return layout

def capture_preview_for(lot: str) -> Optional[np.ndarray]:
    region = PRICE_REGIONS.get(lot)
    if not region:
        return None
    return grab_screen(region)

def main():
    ensure_tesseract()
    load_config()

    window = sg.Window("Dofus Price Helper — GUI + Presets + Optimizer", make_layout(), finalize=True)

    # maj initiale de la liste des presets
    def update_preset_list():
        window["-PRESET-LIST-"].update(values=sorted(list(PRESETS.keys())))

    update_preset_list()

    # état optimiseur courant
    last_prices = {"1": None, "10": None, "100": None}
    last_best = None

    while True:
        event, values = window.read(timeout=200)
        if event in (sg.WINDOW_CLOSED, "-QUIT-"):
            break

        # toggle auto paste
        if event == "-AUTO-":
            global AUTO_PASTE
            AUTO_PASTE = bool(values["-AUTO-"])
            save_config()

        # save params
        if event == "-SAVE-PARAMS-":
            try:
                global PRICE_W, ROW_H, UNDERCUT_MODE, UNDERCUT_VALUE, MIN_PRICE, ROUNDING
                PRICE_W = int(values["-W-"])
                ROW_H   = int(values["-H-"])
                UNDERCUT_MODE  = values["-MODE-"]
                UNDERCUT_VALUE = float(values["-VALUE-"]) if UNDERCUT_MODE=="percent" else int(values["-VALUE-"])
                MIN_PRICE      = int(values["-MIN-"])
                ROUNDING       = values["-ROUND-"]
                save_config()
                window["-STATUS-"].update("Paramètres sauvegardés.")
            except Exception as e:
                window["-STATUS-"].update(f"Erreur paramètres: {e}")

        # set zones
        if event in ("-SET-1-","-SET-10-","-SET-100-"):
            lot = "1" if event=="-SET-1-" else ("10" if event=="-SET-10-" else "100")
            x, y = pyautogui.position()
            region = (x - PRICE_W//2, y - ROW_H//2, PRICE_W, ROW_H)
            PRICE_REGIONS[lot] = region
            save_config()
            window["-STATUS-"].update(f"[Calib] Zone {lot} = {region}")
            img = capture_preview_for(lot)
            if img is not None:
                window["-PREVIEW-"].update(data=to_tk_image(img))

        # read buttons
        if event in ("-READ-1-","-READ-10-","-READ-100-"):
            lot = "1" if event=="-READ-1-" else ("10" if event=="-READ-10-" else "100")
            img = capture_preview_for(lot)
            if img is not None:
                window["-PREVIEW-"].update(data=to_tk_image(img))
            p = read_price(lot)
            last_prices[lot] = p
            if p is None:
                window["-STATUS-"].update(f"[{lot}] Aucun prix détecté.")
            else:
                up = compute_undercut(p, values["-MODE-"], values["-VALUE-"], values["-ROUND-"], int(values["-MIN-"]))
                window["-STATUS-"].update(f"[{lot}] Lu: {p}  |  Undercut → {up}")

        # paste buttons
        if event in ("-PASTE-1-","-PASTE-10-","-PASTE-100-"):
            lot = "1" if event=="-PASTE-1-" else ("10" if event=="-PASTE-10-" else "100")
            p = read_price(lot)
            last_prices[lot] = p
            if p is None:
                window["-STATUS-"].update(f"[{lot}] Aucun prix à coller.")
            else:
                up = compute_undercut(p, values["-MODE-"], values["-VALUE-"], values["-ROUND-"], int(values["-MIN-"]))
                if up is None:
                    window["-STATUS-"].update(f"[{lot}] Undercut invalide.")
                else:
                    pasted = paste_value(up, auto=bool(values["-AUTO-"]))
                    window["-STATUS-"].update(f"[{lot}] {'Collé auto' if pasted else 'Copié'} : {up}  → {'(Ctrl+V auto)' if pasted else '(Ctrl+V manuel)'}")
                    log_history("auto_paste" if pasted else "paste", lot, p, up, {
                        "mode": values["-MODE-"], "value": values["-VALUE-"],
                        "rounding": values["-ROUND-"], "min_price": values["-MIN-"]
                    })

        # optimizer
        if event == "-OPTIMIZE-":
            # Lire 1/10/100 (uniquement si zones calibrées)
            p1   = read_price("1")
            p10  = read_price("10")
            p100 = read_price("100")
            last_prices.update({"1": p1, "10": p10, "100": p100})

            # Aperçu : si une zone existe, affiche celle du lot 1 par défaut
            for k in ("1","10","100"):
                img = capture_preview_for(k)
                if img is not None:
                    window["-PREVIEW-"].update(data=to_tk_image(img)); break

            best = pick_best_lot(p1, p10, p100)
            last_best = best
            # texte reco
            def fmt(p): return "-" if p is None else f"{p}"
            if best is None:
                window["-RECO-"].update("Aucune zone valide (calibrez les 3).")
                window["-STATUS-"].update(f"Lu → 1:{fmt(p1)} | 10:{fmt(p10)} | 100:{fmt(p100)}")
            else:
                u1 = None if p1   is None else p1/1.0
                u10= None if p10  is None else p10/10.0
                u100=None if p100 is None else p100/100.0
                window["-RECO-"].update(f"Lot recommandé: {best} (u1={u1}, u10={u10}, u100={u100})")
                window["-STATUS-"].update(f"Lu → 1:{fmt(p1)} | 10:{fmt(p10)} | 100:{fmt(p100)}")
                log_history("recommend", "auto", None, None, {
                    "mode": values["-MODE-"], "value": values["-VALUE-"],
                    "rounding": values["-ROUND-"], "min_price": values["-MIN-"]
                })

        if event == "-PASTE-BEST-":
            # colle sur le lot recommandé (si on a déjà optimisé)
            if last_best is None:
                window["-STATUS-"].update("Pas de recommandation. Cliquez d'abord sur 'Optimiser'.")
            else:
                lot = last_best
                p = last_prices.get(lot)
                if p is None:
                    # relire au cas où ça a changé
                    p = read_price(lot)
                    last_prices[lot] = p
                if p is None:
                    window["-STATUS-"].update(f"[{lot}] Aucun prix à coller.")
                else:
                    up = compute_undercut(p, values["-MODE-"], values["-VALUE-"], values["-ROUND-"], int(values["-MIN-"]))
                    if up is None:
                        window["-STATUS-"].update(f"[{lot}] Undercut invalide.")
                    else:
                        pasted = paste_value(up, auto=bool(values["-AUTO-"]))
                        window["-STATUS-"].update(f"[{lot}] {'Collé auto' if pasted else 'Copié'} : {up}  → {'(Ctrl+V auto)' if pasted else '(Ctrl+V manuel)'}")
                        log_history("auto_paste" if pasted else "paste", lot, p, up, {
                            "mode": values["-MODE-"], "value": values["-VALUE-"],
                            "rounding": values["-ROUND-"], "min_price": values["-MIN-"]
                        })

        # save config
        if event == "-SAVE-CONFIG-":
            save_config()
            window["-STATUS-"].update("Config sauvegardée.")

        # presets
        if event == "-PRESET-SAVE-":
            name = (values["-PRESET-NAME-"] or "").strip()
            if not name:
                window["-STATUS-"].update("Donnez un nom de prését.")
            else:
                PRESETS[name] = {k: PRICE_REGIONS.get(k) for k in ("1","10","100")}
                save_config()
                window["-STATUS-"].update(f"Prését '{name}' sauvegardé.")
                # refresh list
                window["-PRESET-LIST-"].update(values=sorted(list(PRESETS.keys())))

        if event == "-PRESET-LOAD-":
            name = (values["-PRESET-LIST-"] or "").strip()
            if not name or name not in PRESETS:
                window["-STATUS-"].update("Prését introuvable.")
            else:
                for k in ("1","10","100"):
                    PRICE_REGIONS[k] = PRESETS[name].get(k)
                save_config()
                window["-STATUS-"].update(f"Prését '{name}' chargé.")
                # rafraîchit l’aperçu sur la première zone dispo
                for k in ("1","10","100"):
                    img = capture_preview_for(k)
                    if img is not None:
                        window["-PREVIEW-"].update(data=to_tk_image(img))
                        break

        if event == "-PRESET-DEL-":
            name = (values["-PRESET-LIST-"] or "").strip()
            if not name or name not in PRESETS:
                window["-STATUS-"].update("Prését introuvable.")
            else:
                del PRESETS[name]
                save_config()
                window["-PRESET-LIST-"].update(values=sorted(list(PRESETS.keys())))
                window["-STATUS-"].update(f"Prését '{name}' supprimé.")

    window.close()

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print("Error:", e)
