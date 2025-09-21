#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Dofus Price Helper — FIXED REGIONS (Fullscreen OK)
--------------------------------------------------
- Capture écran via mss (compatible plein écran).
- 3 zones fixes pour les prix (lots 1/10/100), calibrées à la souris.
- F1/F2/F3 lisent la zone correspondante, calculent l'undercut et collent dans le champ actif.

Raccourcis:
  F1 / F2 / F3  : Lire & coller le prix (lots 1 / 10 / 100)
  Ctrl+Alt+F1   : Calibrer la zone PRIX du lot 1 (pointer le centre du prix, puis appuyer)
  Ctrl+Alt+F2   : Calibrer lot 10
  Ctrl+Alt+F3   : Calibrer lot 100
  Ctrl+Shift+P  : Afficher ce que lisent les 3 zones (debug rapide)
  Ctrl+Shift+M  : Afficher la position de la souris
  Esc           : Quitter

Installation:
  pip install mss pyautogui pytesseract opencv-python numpy keyboard pyperclip pillow
  + Tesseract OCR (Windows: https://github.com/UB-Mannheim/tesseract/wiki)
"""

import os, re, time, json
from typing import Tuple, Optional, Dict
import numpy as np
import cv2, mss, pyautogui, pytesseract, keyboard, pyperclip

# ------------- CONFIG -------------
# Chemin de Tesseract si pas dans le PATH :
TESSERACT_CMD = r"C:\Program Files\Tesseract-OCR\tesseract.exe"   # adapte si besoin

CONFIG_FILE = "dofus_price_helper_config.json"

# Taille de la boîte lue autour du pointeur lors de la calibration :
PRICE_W = 150     # largeur (px) de la zone prix
ROW_H   = 40      # hauteur (px) de la zone prix

# Méthode d'undercut: "fixed" (en kamas) ou "percent" (en %)
UNDERCUT_MODE  = "fixed"
UNDERCUT_VALUE = 1
MIN_PRICE      = 1

# Hotkeys
HOTKEY_QTY1    = "f1"
HOTKEY_QTY10   = "f2"
HOTKEY_QTY100  = "f3"
HOTKEY_CAL_1   = "ctrl+alt+f1"
HOTKEY_CAL_10  = "ctrl+alt+f2"
HOTKEY_CAL_100 = "ctrl+alt+f3"
HOTKEY_PRINT   = "ctrl+shift+p"
HOTKEY_MOUSE   = "ctrl+shift+m"
HOTKEY_QUIT    = "esc"

# OCR
TESSERACT_CONFIG = r"--psm 6 -c tessedit_char_whitelist=0123456789"
SCALE = 2  # upscaling pour améliorer l’OCR

# Debug
DEBUG = False
DEBUG_DIR = "captures"
# ------------- END CONFIG ----------

# Zones fixes (x, y, w, h). Remplies par calibration ou chargées du JSON.
PRICE_REGIONS: Dict[str, Optional[Tuple[int,int,int,int]]] = {"1": None, "10": None, "100": None}

def init():
    if TESSERACT_CMD:
        pytesseract.pytesseract.tesseract_cmd = TESSERACT_CMD
    if DEBUG:
        os.makedirs(DEBUG_DIR, exist_ok=True)
    load_config()

def load_config():
    global PRICE_REGIONS, PRICE_W, ROW_H
    if not os.path.exists(CONFIG_FILE):
        return
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        if "PRICE_REGIONS" in data:
            PRICE_REGIONS = {k: (tuple(v) if v else None) for k, v in data["PRICE_REGIONS"].items()}
            print("[Config] Loaded PRICE_REGIONS:", PRICE_REGIONS)
        PRICE_W = int(data.get("PRICE_W", PRICE_W))
        ROW_H   = int(data.get("ROW_H", ROW_H))
    except Exception as e:
        print("[Config] Failed to load:", e)

def save_config():
    data = {
        "PRICE_REGIONS": {k: list(v) if v else None for k,v in PRICE_REGIONS.items()},
        "PRICE_W": PRICE_W,
        "ROW_H": ROW_H,
    }
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        print("[Config] Saved", CONFIG_FILE)
    except Exception as e:
        print("[Config] Save failed:", e)

def grab_screen(region: Tuple[int,int,int,int]) -> np.ndarray:
    x, y, w, h = region
    with mss.mss() as sct:
        img = np.array(sct.grab({"left": x, "top": y, "width": w, "height": h}))
    return img[:, :, :3]  # BGR

def preprocess_for_ocr(img_bgr: np.ndarray) -> np.ndarray:
    gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
    up   = cv2.resize(gray, (gray.shape[1]*SCALE, gray.shape[0]*SCALE), interpolation=cv2.INTER_CUBIC)
    up   = cv2.bilateralFilter(up, d=7, sigmaColor=55, sigmaSpace=55)
    # Si besoin, inverse : THRESH_BINARY_INV
    _, th = cv2.threshold(up, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    return th

def ocr_number_from_image(img_bgr: np.ndarray) -> Optional[int]:
    pre = preprocess_for_ocr(img_bgr)
    txt = pytesseract.image_to_string(pre, config=TESSERACT_CONFIG)
    if DEBUG:
        print("[OCR raw]", repr(txt))
    digits = re.sub(r"[^0-9]", "", txt)
    return int(digits) if digits else None

def undercut(price: int) -> int:
    if price is None:
        return None
    if UNDERCUT_MODE.lower() == "percent":
        new_price = int(round(price * (1 - float(UNDERCUT_VALUE)/100.0)))
    else:
        new_price = price - int(UNDERCUT_VALUE)
    return max(MIN_PRICE, new_price)

def paste_price(p: int):
    if p is None:
        return
    pyperclip.copy(str(p))
    time.sleep(0.05)
    keyboard.press_and_release("ctrl+v")

# ---------- Calibration des zones fixes ----------
def set_price_region_for(lot: str):
    """Place le pointeur au centre du PRIX de la ligne (1/10/100) puis appuie sur le hotkey."""
    x, y = pyautogui.position()
    left = x - PRICE_W // 2
    top  = y - ROW_H // 2
    PRICE_REGIONS[lot] = (left, top, PRICE_W, ROW_H)
    save_config()
    print(f"[Calib] PRICE_REGIONS[{lot}] = {PRICE_REGIONS[lot]}")

def read_price_from_fixed_region(lot: str) -> Optional[int]:
    region = PRICE_REGIONS.get(lot)
    if not region:
        print(f"[Info] No fixed region for lot {lot}. Calibrate with Ctrl+Alt+F{1 if lot=='1' else 2 if lot=='10' else 3}.")
        return None
    img = grab_screen(region)
    if DEBUG:
        cv2.imwrite(os.path.join(DEBUG_DIR, f"price_{lot}_{int(time.time()*1000)}.png"), img)
    return ocr_number_from_image(img)

def print_all_prices():
    p1   = read_price_from_fixed_region("1")
    p10  = read_price_from_fixed_region("10")
    p100 = read_price_from_fixed_region("100")
    print(f"Lot 1:   {p1}  -> {undercut(p1) if p1 is not None else None}")
    print(f"Lot 10:  {p10} -> {undercut(p10) if p10 is not None else None}")
    print(f"Lot 100: {p100}-> {undercut(p100) if p100 is not None else None}")

def show_mouse():
    x, y = pyautogui.position()
    print(f"Mouse: x={x}, y={y}")

def main():
    init()
    print("Dofus Price Helper (FIXED).")
    print("Calibre chaque lot: place la souris AU CENTRE du prix, puis:")
    print("  Ctrl+Alt+F1 (lot 1) | Ctrl+Alt+F2 (lot 10) | Ctrl+Alt+F3 (lot 100)")
    print("Ensuite utilise F1/F2/F3 dans le champ de prix pour coller l’undercut.")
    # Hotkeys calibrage
    keyboard.add_hotkey(HOTKEY_CAL_1,   lambda: set_price_region_for("1"))
    keyboard.add_hotkey(HOTKEY_CAL_10,  lambda: set_price_region_for("10"))
    keyboard.add_hotkey(HOTKEY_CAL_100, lambda: set_price_region_for("100"))
    # Hotkeys lecture/collage
    keyboard.add_hotkey(HOTKEY_QTY1,    lambda: (lambda p=read_price_from_fixed_region("1"):   paste_price(undercut(p)) if p is not None else print("No price for 1"))())
    keyboard.add_hotkey(HOTKEY_QTY10,   lambda: (lambda p=read_price_from_fixed_region("10"):  paste_price(undercut(p)) if p is not None else print("No price for 10"))())
    keyboard.add_hotkey(HOTKEY_QTY100,  lambda: (lambda p=read_price_from_fixed_region("100"): paste_price(undercut(p)) if p is not None else print("No price for 100"))())
    # Debug
    keyboard.add_hotkey(HOTKEY_PRINT, print_all_prices)
    keyboard.add_hotkey(HOTKEY_MOUSE, show_mouse)
    # Wait
    try:
        keyboard.wait(HOTKEY_QUIT)
    except KeyboardInterrupt:
        pass
    finally:
        print("Bye!")

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print("Error:", e)
