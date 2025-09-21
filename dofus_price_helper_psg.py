#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Dofus Price Helper — CustomTkinter + Hotkeys + Optimizer (no CSV, no item name)
-------------------------------------------------------------------------------
- UI moderne (CustomTkinter) : log temps réel coloré, réglages.
- Hotkeys globaux :
    F1  -> lire lot 1   -> undercut -> (auto) coller
    F2  -> lire lot 10  -> undercut -> (auto) coller
    F3  -> lire lot 100 -> undercut -> (auto) coller
    F4  -> optimiser (lit 1/10/100, choisit le meilleur lot), undercut, (auto) coller
    Ctrl+Alt+F1/F2/F3 -> calibrer la zone prix (place la souris au CENTRE du prix)
- Collage automatique Ctrl+V (via 'keyboard') désactivable.
- OCR via Tesseract + mss (plein écran OK).
- Config JSON persistée (zones, paramètres).
- Logs colorés: Lot1 (cyan), Lot10 (vert), Lot100 (orange), OPT (violet), INFO (gris), ERROR (rouge).

Dépendances (dans venv) :
  pip install customtkinter mss pyautogui pytesseract opencv-python numpy pyperclip pillow keyboard

+ Installer Tesseract (Windows : https://github.com/UB-Mannheim/tesseract/wiki)
  et ajuster TESSERACT_CMD ci-dessous si nécessaire.
"""

import os, re, json, time, threading, queue
from typing import Optional, Tuple, Dict

import numpy as np
import cv2
import mss
import pyautogui
import pytesseract
import pyperclip
from PIL import Image

# UI
import customtkinter as ctk
import tkinter as tk  # pour Text + tags couleurs

# Hotkeys globaux + Ctrl+V auto
try:
    import keyboard
    KEYBOARD_AVAILABLE = True
except Exception:
    KEYBOARD_AVAILABLE = False

# ---------------- CONFIG / DEFAULTS ----------------
TESSERACT_CMD = r"C:\Program Files\Tesseract-OCR\tesseract.exe"  # adapte si besoin
CONFIG_FILE   = "dofus_price_helper_config.json"

# Taille de la zone capturée autour du centre du prix
PRICE_W = 150
ROW_H   = 40

# OCR
TESSERACT_CONFIG = r"--psm 6 -c tessedit_char_whitelist=0123456789"
SCALE = 2  # upscaling OCR

# Undercut
UNDERCUT_MODE  = "fixed"    # "fixed" | "percent"
UNDERCUT_VALUE = 1          # int (fixed) ou float (percent)
MIN_PRICE      = 1

# Arrondi: "none" | "down_10" | "down_100" | "end_9"
ROUNDING       = "none"

# Zones par lot: { "1": (x,y,w,h) , "10": (...), "100": (...) }
PRICE_REGIONS: Dict[str, Optional[Tuple[int,int,int,int]]] = {"1": None, "10": None, "100": None}

# Coller automatiquement (Ctrl+V)
AUTO_PASTE = True
# ---------------------------------------------------


# ---------------- OCR & PRICE UTILS ----------------
def ensure_tesseract():
    if TESSERACT_CMD:
        pytesseract.pytesseract.tesseract_cmd = TESSERACT_CMD

def grab_screen(region: Tuple[int,int,int,int]) -> np.ndarray:
    x, y, w, h = region
    with mss.mss() as sct:
        img = np.array(sct.grab({"left": x, "top": y, "width": w, "height": h}))
    return img[:, :, :3]  # BGR

def preprocess_for_ocr(img_bgr: np.ndarray) -> np.ndarray:
    gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
    up   = cv2.resize(gray, (gray.shape[1]*SCALE, gray.shape[0]*SCALE), interpolation=cv2.INTER_CUBIC)
    up   = cv2.bilateralFilter(up, d=7, sigmaColor=55, sigmaSpace=55)
    # Si UI claire sur fond sombre lit mal, essayer THRESH_BINARY_INV
    _, th = cv2.threshold(up, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    return th

def ocr_number_from_image(img_bgr: np.ndarray) -> Optional[int]:
    pre = preprocess_for_ocr(img_bgr)
    txt = pytesseract.image_to_string(pre, config=TESSERACT_CONFIG)
    digits = re.sub(r"[^0-9]", "", txt)
    return int(digits) if digits else None

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

def read_price_from_region(region: Optional[Tuple[int,int,int,int]]) -> Optional[int]:
    if not region:
        return None
    img = grab_screen(region)
    return ocr_number_from_image(img)

def pick_best_lot(p1: Optional[int], p10: Optional[int], p100: Optional[int]) -> Optional[str]:
    cand = []
    if p1   is not None:  cand.append(("1",   p1/1.0))
    if p10  is not None:  cand.append(("10",  p10/10.0))
    if p100 is not None:  cand.append(("100", p100/100.0))
    if not cand:
        return None
    # ex aequo ±1% -> privilégie le plus petit lot (meilleur turnover)
    priority = {"1":3, "10":2, "100":1}
    cand.sort(key=lambda t: (t[1], priority[t[0]]), reverse=True)
    return cand[0][0]

def paste_value(val: int, auto: bool) -> bool:
    pyperclip.copy(str(val))
    time.sleep(0.05)
    if auto and KEYBOARD_AVAILABLE:
        try:
            keyboard.press_and_release("ctrl+v")
            return True
        except Exception:
            return False
    return False
# ---------------------------------------------------


# ---------------- CONFIG (JSON) --------------------
def load_config():
    global PRICE_REGIONS, PRICE_W, ROW_H, UNDERCUT_MODE, UNDERCUT_VALUE, MIN_PRICE, ROUNDING, AUTO_PASTE
    if not os.path.exists(CONFIG_FILE):
        return
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            data = json.load(f) or {}
        if "PRICE_REGIONS" in data:
            PRICE_REGIONS = {k: (tuple(v) if v else None) for k, v in data["PRICE_REGIONS"].items()}
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
    except Exception as e:
        print("[Config] save failed:", e)
# ---------------------------------------------------


# -------------------- UI APP -----------------------
class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("Dofus Price Helper — CustomTkinter (Hotkeys + Optimizer)")
        self.geometry("980x640")
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")

        ensure_tesseract()
        load_config()

        # state vars
        self.mode_var  = ctk.StringVar(value=str(UNDERCUT_MODE))
        self.value_var = ctk.StringVar(value=str(UNDERCUT_VALUE))
        self.round_var = ctk.StringVar(value=str(ROUNDING))
        self.min_var   = ctk.StringVar(value=str(MIN_PRICE))
        self.w_var     = ctk.StringVar(value=str(PRICE_W))
        self.h_var     = ctk.StringVar(value=str(ROW_H))
        self.auto_var  = ctk.BooleanVar(value=bool(AUTO_PASTE))
        self.reco_var  = ctk.StringVar(value="-")

        # thread-safe event queue from hotkeys
        self.ev_queue = queue.Queue()

        self._build_ui()
        self._setup_log_tags()
        self._start_hotkeys_thread()
        self._poll_events()  # start periodic poll

        self._log("Prêt. Hotkeys: F1/F2/F3/F4, Ctrl+Alt+F1/F2/F3", tag="INFO")

    # ---------- UI ----------
    def _build_ui(self):
        # Top controls
        top = ctk.CTkFrame(self)
        top.pack(fill="x", padx=12, pady=(12,6))

        ctk.CTkLabel(top, text="Undercut:").pack(side="left", padx=(6,4))
        ctk.CTkOptionMenu(top, values=["fixed","percent"], variable=self.mode_var, width=110).pack(side="left", padx=(0,8))
        ctk.CTkLabel(top, text="Valeur:").pack(side="left", padx=(6,4))
        ctk.CTkEntry(top, textvariable=self.value_var, width=80).pack(side="left", padx=(0,12))

        ctk.CTkLabel(top, text="Arrondi:").pack(side="left", padx=(6,4))
        ctk.CTkOptionMenu(top, values=["none","down_10","down_100","end_9"], variable=self.round_var, width=120).pack(side="left", padx=(0,8))
        ctk.CTkLabel(top, text="Min:").pack(side="left", padx=(6,4))
        ctk.CTkEntry(top, textvariable=self.min_var, width=80).pack(side="left", padx=(0,12))

        ctk.CTkSwitch(top, text="Coller automatiquement (Ctrl+V)", variable=self.auto_var).pack(side="left", padx=8)

        # Secondary controls
        sec = ctk.CTkFrame(self)
        sec.pack(fill="x", padx=12, pady=(6,6))

        ctk.CTkLabel(sec, text="Taille zone (prix)").pack(side="left", padx=(6,10))
        ctk.CTkLabel(sec, text="Largeur").pack(side="left", padx=(0,4))
        ctk.CTkEntry(sec, textvariable=self.w_var, width=70).pack(side="left", padx=(0,10))
        ctk.CTkLabel(sec, text="Hauteur").pack(side="left", padx=(0,4))
        ctk.CTkEntry(sec, textvariable=self.h_var, width=70).pack(side="left", padx=(0,10))
        ctk.CTkButton(sec, text="Sauver paramètres", command=self._on_save_params, width=170).pack(side="left", padx=(10,6))

        # Calibration buttons (optionnels, hotkeys existent aussi)
        cal = ctk.CTkFrame(self)
        cal.pack(fill="x", padx=12, pady=(6,6))
        ctk.CTkLabel(cal, text="Calibration : place la souris au CENTRE du prix, puis :").pack(side="left", padx=(6,8))
        ctk.CTkButton(cal, text="Set zone Lot 1",  command=lambda: self._calibrate_click("1"), width=130).pack(side="left", padx=4)
        ctk.CTkButton(cal, text="Set zone Lot 10", command=lambda: self._calibrate_click("10"), width=130).pack(side="left", padx=4)
        ctk.CTkButton(cal, text="Set zone Lot 100",command=lambda: self._calibrate_click("100"), width=130).pack(side="left", padx=4)

        # Recommendation
        reco = ctk.CTkFrame(self)
        reco.pack(fill="x", padx=12, pady=(6,6))
        ctk.CTkLabel(reco, text="Lot recommandé :").pack(side="left", padx=(6,8))
        ctk.CTkLabel(reco, textvariable=self.reco_var, font=ctk.CTkFont(size=16, weight="bold")).pack(side="left")

        # Log box (tk.Text pour tags couleur) + CTkScrollbar
        log_frame = ctk.CTkFrame(self)
        log_frame.pack(fill="both", expand=True, padx=12, pady=(6,12))

        self.log_text = tk.Text(log_frame, wrap="word", height=18, bg="#111418", fg="#EDEDED", insertbackground="#EDEDED")
        self.log_text.configure(state="disabled")
        self.log_text.pack(side="left", fill="both", expand=True, padx=(6,0), pady=6)

        scrollbar = ctk.CTkScrollbar(log_frame, command=self.log_text.yview)
        scrollbar.pack(side="right", fill="y", padx=(0,6), pady=6)
        self.log_text.configure(yscrollcommand=scrollbar.set)

        # Help footer
        help_text = (
            "Raccourcis :  F1=lot 1  |  F2=lot 10  |  F3=lot 100  |  F4=Optimiser  |  "
            "Ctrl+Alt+F1/F2/F3=Calibrer zones"
        )
        ctk.CTkLabel(self, text=help_text, text_color="#AFAFAF").pack(pady=(0,8))

    def _setup_log_tags(self):
        # couleurs
        self.log_text.tag_configure("TIME", foreground="#7f8c8d")
        self.log_text.tag_configure("INFO", foreground="#bdc3c7")
        self.log_text.tag_configure("ERROR", foreground="#ff6b6b")
        self.log_text.tag_configure("LOT1", foreground="#66d9ef")    # cyan
        self.log_text.tag_configure("LOT10", foreground="#a6e22e")   # vert
        self.log_text.tag_configure("LOT100", foreground="#fd971f")  # orange
        self.log_text.tag_configure("OPT", foreground="#ae81ff")     # violet

    # ---------- Thread-safe log ----------
    def _log(self, msg: str, tag: str = "INFO"):
        ts = time.strftime("%H:%M:%S")
        self.log_text.configure(state="normal")
        self.log_text.insert("end", f"{ts}  ", ("TIME",))
        self.log_text.insert("end", msg + "\n", (tag,))
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

    # ---------- Params ----------
    def _on_save_params(self):
        global PRICE_W, ROW_H, UNDERCUT_MODE, UNDERCUT_VALUE, MIN_PRICE, ROUNDING, AUTO_PASTE
        try:
            PRICE_W = int(self.w_var.get())
            ROW_H   = int(self.h_var.get())
        except:
            self._log("[Param] Largeur/hauteur invalides.", tag="ERROR")
            return
        UNDERCUT_MODE  = self.mode_var.get()
        try:
            UNDERCUT_VALUE = float(self.value_var.get()) if UNDERCUT_MODE=="percent" else int(self.value_var.get())
        except:
            self._log("[Param] Valeur d’undercut invalide, fallback 1.", tag="ERROR")
            UNDERCUT_VALUE = 1 if UNDERCUT_MODE=="fixed" else 1.0
        try:
            MIN_PRICE = int(self.min_var.get())
        except:
            MIN_PRICE = 1
        ROUNDING   = self.round_var.get()
        AUTO_PASTE = bool(self.auto_var.get())
        save_config()
        self._log("[Param] Paramètres sauvegardés.", tag="INFO")

    # ---------- Calibration ----------
    def _calibrate_click(self, lot: str):
        try:
            w = int(self.w_var.get()); h = int(self.h_var.get())
        except:
            self._log("[Calib] Largeur/hauteur invalides.", tag="ERROR")
            return
        x, y = pyautogui.position()
        region = (x - w//2, y - h//2, w, h)
        PRICE_REGIONS[lot] = region
        save_config()
        self._log(f"[Calib] Zone {lot} = {region}", tag=self._lot_tag(lot))

    # ---------- Hotkeys ----------
    def _start_hotkeys_thread(self):
        if not KEYBOARD_AVAILABLE:
            self._log("[Hotkeys] Le module 'keyboard' n'est pas disponible. Les hotkeys ne fonctionneront pas.", tag="ERROR")
            return
        th = threading.Thread(target=self._register_hotkeys, daemon=True)
        th.start()
        self._log("[Hotkeys] Enregistrés : F1/F2/F3/F4, Ctrl+Alt+F1/F2/F3", tag="INFO")

    def _register_hotkeys(self):
        # poster des événements vers la queue, consommés par le thread UI
        def post(name, payload=None):
            self.ev_queue.put((name, payload or {}))
        # lecture+collage
        keyboard.add_hotkey("f1",  lambda: post("READ_PASTE", {"lot":"1"}))
        keyboard.add_hotkey("f2",  lambda: post("READ_PASTE", {"lot":"10"}))
        keyboard.add_hotkey("f3",  lambda: post("READ_PASTE", {"lot":"100"}))
        # optimiser
        keyboard.add_hotkey("f4",  lambda: post("OPTIMIZE", {}))
        # calibration
        keyboard.add_hotkey("ctrl+alt+f1", lambda: post("CAL", {"lot":"1"}))
        keyboard.add_hotkey("ctrl+alt+f2", lambda: post("CAL", {"lot":"10"}))
        keyboard.add_hotkey("ctrl+alt+f3", lambda: post("CAL", {"lot":"100"}))

    def _poll_events(self):
        # appelé périodiquement sur le thread UI
        try:
            while True:
                name, payload = self.ev_queue.get_nowait()
                if name == "READ_PASTE":
                    self._handle_read_paste(payload.get("lot"))
                elif name == "OPTIMIZE":
                    self._handle_optimize()
                elif name == "CAL":
                    self._handle_cal_hotkey(payload.get("lot"))
        except queue.Empty:
            pass
        # re-planifier
        self.after(40, self._poll_events)

    # ---------- Helpers ----------
    def _current_settings(self) -> dict:
        return {
            "mode": self.mode_var.get(),
            "value": self.value_var.get(),
            "rounding": self.round_var.get(),
            "min_price": self.min_var.get(),
            "auto_paste": bool(self.auto_var.get()),
        }

    def _lot_tag(self, lot: Optional[str]) -> str:
        if lot == "1": return "LOT1"
        if lot == "10": return "LOT10"
        if lot == "100": return "LOT100"
        return "INFO"

    # ---------- Actions ----------
    def _handle_cal_hotkey(self, lot: str):
        try:
            w = int(self.w_var.get()); h = int(self.h_var.get())
        except:
            self._log("[Calib] Largeur/hauteur invalides.", tag="ERROR")
            return
        x, y = pyautogui.position()
        region = (x - w//2, y - h//2, w, h)
        PRICE_REGIONS[lot] = region
        save_config()
        self._log(f"[Calib] (Hotkey) Zone {lot} = {region}", tag=self._lot_tag(lot))

    def _handle_read_paste(self, lot: str):
        settings = self._current_settings()
        p = read_price_from_region(PRICE_REGIONS.get(lot))
        if p is None:
            self._log(f"[{lot}] Aucun prix détecté. (zone non calibrée ou OCR)", tag=self._lot_tag(lot))
            return
        try:
            minp = int(settings["min_price"])
        except:
            minp = 1
        up = compute_undercut(p, settings["mode"], settings["value"], settings["rounding"], minp)
        pasted = paste_value(up, auto=settings["auto_paste"])
        self._log(
            f"[{lot}] Lu: {p}  ->  Undercut: {up}  |  {'Collé auto (Ctrl+V)' if pasted else 'Copié (Ctrl+V man.)'}",
            tag=self._lot_tag(lot)
        )

    def _handle_optimize(self):
        settings = self._current_settings()
        p1   = read_price_from_region(PRICE_REGIONS.get("1"))
        p10  = read_price_from_region(PRICE_REGIONS.get("10"))
        p100 = read_price_from_region(PRICE_REGIONS.get("100"))
        self._log(
            f"[OPT] Lu → 1:{'-' if p1 is None else p1} | 10:{'-' if p10 is None else p10} | 100:{'-' if p100 is None else p100}",
            tag="OPT"
        )

        best = pick_best_lot(p1, p10, p100)
        if best is None:
            self.reco_var.set("-")
            self._log("[OPT] Aucune zone valide (calibrez 1/10/100).", tag="ERROR")
            return

        self.reco_var.set(best)
        p = {"1": p1, "10": p10, "100": p100}[best]
        try:
            minp = int(settings["min_price"])
        except:
            minp = 1
        up = compute_undercut(p, settings["mode"], settings["value"], settings["rounding"], minp)
        pasted = paste_value(up, auto=settings["auto_paste"])
        self._log(
            f"[OPT] Lot recommandé: {best}  |  Lu: {p} -> Undercut: {up}  |  {'Collé auto' if pasted else 'Copié'}",
            tag="OPT"
        )


# ----------------- MAIN -----------------
if __name__ == "__main__":
    try:
        app = App()
        app.mainloop()
    except Exception as e:
        print("Error:", e)
