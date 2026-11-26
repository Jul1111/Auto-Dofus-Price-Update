#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Dofus Price Helper — Interface graphique (CustomTkinter)
--------------------------------------------------------
Raccourcis par défaut (modifiables dans la config, clé HOTKEYS) :
  F1                  vendre à la quantité affichée dans le jeu (lit le tableau + la quantité)
  F2                  tout vendre : remet en vente au même prix tant que la quantité et ton prix
                      en tête du tableau ne changent pas (stock épuisé, autre objet, concurrent)
  F4                  optimiser : meilleur prix unitaire (demande de changer la quantité si besoin)
  F3                  mes ventes : remet la vente sélectionnée juste sous le moins cher (« Modifier »)
  Ctrl+F3             mes ventes : toute la liste, avec scroll (RELIST_AUTO = true requis)
  (même touche 2x)    forcer une lecture jugée suspecte
  Ctrl+Alt+F1 (x2)    calibrer le tableau « Actuellement en vente » (coin haut-gauche, puis bas-droit)
  Ctrl+Alt+F2 (x2)    calibrer le menu « Quantité » (coin haut-gauche, puis bas-droit)
  Ctrl+Alt+F3         calibrer le champ « Prix du lot »
  Ctrl+Alt+F4         calibrer le bouton « Mettre en vente »
  Ctrl+Alt+F5 (x2)    (optionnel) calibrer la valeur du « Prix moyen » -> garde-fou prix trop bas
  Ctrl+Alt+F6 (x2)    (optionnel) calibrer le compteur « 21/100 lots en vente » -> F2 vérifie chaque vente
  Ctrl+Alt+F7 (x2)    mes ventes : calibrer le texte du champ « Prix du lot » (ton prix actuel)
  Ctrl+Alt+F8         mes ventes : calibrer le bouton « Modifier » (sinon Entrée)
  Ctrl+Alt+F9 (x2)    mes ventes : 1re ligne puis 2e ligne de la liste (pour Ctrl+F3)
  Ctrl+Alt+F10 (x2)   repère : titre « Hôtel de vente » (les zones suivent l'HDV déplacé)
  Ctrl+Alt+V          afficher les zones calibrées
  Ctrl+Alt+P          pause / reprise des raccourcis
"""
from __future__ import annotations

import queue
import threading
import time
import tkinter as tk
from typing import Optional

import dofus_core as core  # active la gestion DPI avant Tk
import dofus_update  # noqa: E402

import customtkinter as ctk

import dofus_style as style
from dofus_style import P

try:
    import keyboard
    KEYBOARD_AVAILABLE = True
except Exception:  # pas installé / pas les droits
    KEYBOARD_AVAILABLE = False

TAG_COLORS = {
    "TIME": "#5f6670", "INFO": "#b8bec7", "ERROR": P["red"], "WARN": P["orange"],
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
    "pause": "Pause / reprise (arrête aussi les boucles)",
    "show_zones": "Afficher les zones calibrées",
    "cheatsheet": "Aide-mémoire des touches par-dessus le jeu",
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


# ---------------------------------------------------------------- aperçu des prix (onglet Prix)
PREVIEW_TOP = 1000     # prix d'exemple du moins cher (lot de 1)
PREVIEW_AVG = 1000     # prix moyen d'exemple (par objet)
PREVIEW_LOW = 500      # un vendeur qui brade


def price_preview(mode: str, value, rounding: str, min_price: int, floor_ratio: float,
                  floor_mode: str, min_avg_ratio: float = 0.5) -> list:
    """Exemple chiffré des réglages de prix, comme le moteur les applique (lot de 1).
    mode / rounding / floor_mode : clés de config ("fixed", "down_10", "keep"…)."""
    new = core.compute_price(PREVIEW_TOP, mode, value, rounding, min_price)
    fp = core.floor_price(1, PREVIEW_AVG, floor_ratio) if floor_mode != "stop" else None
    line = f"Moins cher {fmt(PREVIEW_TOP)} → ton prix {fmt(new)}"
    if fp:
        line += f"   (plancher {fmt(fp)})"
    out = [line]
    low = core.compute_price(PREVIEW_LOW, mode, value, rounding, min_price)
    head = f"Un vendeur brade à {fmt(PREVIEW_LOW)} (prix moyen {fmt(PREVIEW_AVG)}) → "
    if fp and low < fp:
        if floor_mode == "keep":
            out.append(head + f"vente au plancher {fmt(fp)} ; une de tes ventes garde son prix")
        else:
            out.append(head + f"ton prix {fmt(fp)} (plancher)")
    elif floor_mode == "stop" and min_avg_ratio > 0 and low < PREVIEW_AVG * min_avg_ratio:
        out.append(head + f"{fmt(low)} jugé suspect : arrêt (même touche ×2 pour forcer)")
    else:
        out.append(head + f"ton prix {fmt(low)}")
    return out


# ---------------------------------------------------------------- journal : filtres
SALE_PREFIXES = ("[VENTE]", "[OPT]", "[TOUT]", "[MAJ]", "[MAJ TOUT]")
LOG_FILTERS = {"Tout": "all", "Ventes": "sale", "Problèmes": "problem"}


def log_category(msg: str, tag: str) -> str:
    """« problem » (avertissement / erreur), « sale » (vente, mise à jour) ou « info »."""
    if tag in ("WARN", "ERROR"):
        return "problem"
    if msg.lstrip().startswith(SALE_PREFIXES):
        return "sale"
    return "info"


def log_visible(category: str, flt: str, in_block: bool = False) -> bool:
    """La ligne passe-t-elle le filtre ? Un problème est aussi une ligne de vente s'il en vient."""
    if flt == "all":
        return True
    if flt == "problem":
        return category == "problem"
    return category == "sale" or in_block


# ---------------------------------------------------------------- historique des Ctrl+F3
RUNS_PATH = core.BASE_DIR / "dofus_relist_runs.json"
MAX_RUNS = 10


def runs_to_json(runs: list) -> list:
    """Parcours -> JSON (sans les images des noms, gardées en mémoire seulement)."""
    return [{"time": r["time"], "changes": [
        {"row": c.row, "lot": c.lot, "old": c.old, "new": c.new, "modified": c.modified, "note": c.note}
        for c in r["changes"]]} for r in runs]


def runs_from_json(data) -> list:
    runs = []
    for r in data if isinstance(data, list) else []:
        try:
            runs.append({"time": float(r["time"]), "changes": [core.RowChange(
                row=int(c["row"]), lot=c.get("lot"), old=c.get("old"), new=c.get("new"),
                modified=bool(c.get("modified")), note=str(c.get("note", ""))) for c in r["changes"]]})
        except (KeyError, TypeError, ValueError):
            continue
    return runs[-MAX_RUNS:]


def load_runs(path=None) -> list:
    import json
    path = path or RUNS_PATH
    try:
        return runs_from_json(json.loads(path.read_text(encoding="utf-8")))
    except (OSError, ValueError):
        return []


def save_runs(runs: list, path=None) -> None:
    import json
    path = path or RUNS_PATH
    path.write_text(json.dumps(runs_to_json(runs[-MAX_RUNS:]), ensure_ascii=False), encoding="utf-8")


def run_title(run: dict) -> str:
    mod = sum(1 for c in run["changes"] if c.modified)
    bad = len(run["changes"]) - mod
    txt = time.strftime("%d/%m %H:%M", time.localtime(run["time"]))
    txt += f"  —  {mod} prix modifié{'s' if mod > 1 else ''}"
    if bad:
        txt += f"  ·  {bad} à revoir"
    return txt


# ---------------------------------------------------------------- fenêtre / apparence
UI_SCALES = {"90 %": 0.9, "100 %": 1.0, "110 %": 1.1, "125 %": 1.25, "150 %": 1.5}


def scale_label(scale: float) -> str:
    return min(UI_SCALES, key=lambda k: abs(UI_SCALES[k] - scale))


def geometry_on_screen(geom: str, bounds) -> bool:
    """« LxH+X+Y » enregistré : la fenêtre serait-elle (au moins en partie) visible ?
    (écran débranché depuis -> fenêtre perdue hors de l'écran)."""
    import re
    m = re.fullmatch(r"(\d+)x(\d+)\+(-?\d+)\+(-?\d+)", geom or "")
    if not m:
        return False
    w, h, x, y = map(int, m.groups())
    sx, sy, sw, sh = bounds
    return w >= 200 and h >= 120 and sx - w + 80 <= x <= sx + sw - 80 and sy <= y <= sy + sh - 40


# ---------------------------------------------------------------- fenêtres flottantes au style de l'outil
POPUP_KEY = "#010203"   # couleur rendue transparente : coins arrondis des fenêtres flottantes


def rounded_popup(master, radius: int = 12, alpha: float = 0.97, border: str = None):
    """Fenêtre flottante sans bord (popup, bandeau, bulle d'aide) : une carte arrondie avec une
    bordure fine, aux couleurs de l'outil. Retourne (fenêtre, carte) ; mettre le contenu dans la carte."""
    t = tk.Toplevel(master)
    t.overrideredirect(True)
    t.attributes("-topmost", True)
    t.configure(bg=POPUP_KEY)
    try:
        t.attributes("-transparentcolor", POPUP_KEY)   # Windows : coins vraiment arrondis
    except tk.TclError:
        t.configure(bg=P["card"])
    try:
        t.attributes("-alpha", alpha)
    except tk.TclError:
        pass
    card = ctk.CTkFrame(t, fg_color=P["card"], corner_radius=radius, border_width=1,
                        border_color=border or P["border"])
    card.pack()
    return t, card


# ---------------------------------------------------------------- panneau « Activité »
ACTION_KINDS = (("[MAJ TOUT]", "Toute la liste"), ("[TOUT]", "Tout vendre"), ("[VENTE]", "Vente"),
                ("[OPT]", "Meilleur lot"), ("[MAJ]", "Mise à jour"))


def action_entry(res, when: float = None) -> dict:
    """Une ligne du panneau Activité à partir du résultat d'une action."""
    msg = res.message.lstrip()
    kind = next((label for prefix, label in ACTION_KINDS if msg.startswith(prefix)), "Action")
    if msg.startswith("[MAJ TOUT]"):
        text = kind
    elif res.old_price and res.new_price is not None and res.old_price != res.new_price:
        text = f"{kind} · lot {res.lot or '?'} : {fmt(res.old_price)} → {fmt(res.new_price)}"
    elif res.new_price is not None:
        text = f"{kind} · lot {res.lot or '?'} → {fmt(res.new_price)}"
    else:
        text = kind + (f" · lot {res.lot}" if res.lot else "")
    return {"time": time.strftime("%H:%M", time.localtime(when or time.time())), "text": text,
            "hint": res.hint or {"ok": "ok", "warn": "à vérifier", "error": "erreur"}.get(res.level, ""),
            "level": res.level}


# ---------------------------------------------------------------- progression des boucles (F2, Ctrl+F3)
def progress_text(d: dict) -> tuple:
    """(texte, fraction 0..1 ou None si le total est inconnu) pour la barre de progression."""
    row, total = d.get("row"), d.get("total")
    parts = [f"Ligne {row}" + (f" / {total}" if total else "") if row else "Démarrage…"]
    if d.get("changed"):
        parts.append(f"{d['changed']} modifiée{'s' if d['changed'] > 1 else ''}")
    if d.get("bad"):
        parts.append(f"{d['bad']} à revoir")
    frac = min(1.0, max(0.0, row / total)) if row and total else None
    return " · ".join(parts), frac


LONG_LOOP_S = 20   # s : au-delà, une notification Windows signale la fin (outil en arrière-plan)


def windows_notify(title: str, body: str) -> bool:
    """Notification Windows (centre de notifications), sans dépendance : passe par PowerShell.
    Le texte passe par des variables d'environnement (jamais interprété comme du code)."""
    import os
    import subprocess
    import sys
    if sys.platform != "win32":
        return False
    script = (
        "$ErrorActionPreference='Stop';"
        "[Windows.UI.Notifications.ToastNotificationManager,Windows.UI.Notifications,ContentType=WindowsRuntime]>$null;"
        "[Windows.Data.Xml.Dom.XmlDocument,Windows.Data.Xml.Dom.XmlDocument,ContentType=WindowsRuntime]>$null;"
        "$t=[Security.SecurityElement]::Escape($env:DPH_TITLE);$b=[Security.SecurityElement]::Escape($env:DPH_BODY);"
        "$x=New-Object Windows.Data.Xml.Dom.XmlDocument;"
        "$x.LoadXml(\"<toast><visual><binding template='ToastGeneric'><text>$t</text><text>$b</text>"
        "</binding></visual></toast>\");"
        r"$app='{1AC14E77-02E7-4E5D-B744-2EB1AE5198B7}\WindowsPowerShell\v1.0\powershell.exe';"
        "[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier($app).Show("
        "[Windows.UI.Notifications.ToastNotification]::new($x))")
    env = dict(os.environ, DPH_TITLE=title, DPH_BODY=body)
    try:
        subprocess.Popen(["powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
                          "-Command", script], env=env, creationflags=0x08000000,   # CREATE_NO_WINDOW
                         stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True
    except OSError:
        return False


# ---------------------------------------------------------------- accueil : premiers pas
FIRST_STEPS = (("calib", "Calibrer l'HDV"), ("read", "Tester une lecture"), ("sell", "Première vente"))


class Tooltip:
    """Aide au survol : petite bulle après une demi-seconde sur le widget."""

    def __init__(self, widget, text: str, delay: int = 450):
        self.widget, self.text, self.delay = widget, text, delay
        self._after = None
        self._tip = None
        for seq, fn in (("<Enter>", self._schedule), ("<Leave>", self._hide), ("<ButtonPress>", self._hide)):
            try:
                widget.bind(seq, fn, add="+")
            except (NotImplementedError, ValueError, tk.TclError):
                pass

    def _schedule(self, _e=None):
        self._cancel()
        self._after = self.widget.after(self.delay, self._show)

    def _cancel(self):
        if self._after:
            try:
                self.widget.after_cancel(self._after)
            except tk.TclError:
                pass
            self._after = None

    def _show(self):
        self._after = None
        if self._tip is not None or not self.text:
            return
        try:
            x, y = self.widget.winfo_pointerx() + 14, self.widget.winfo_pointery() + 18
        except tk.TclError:
            return
        t, card = rounded_popup(self.widget, radius=8)
        ctk.CTkLabel(card, text=self.text, justify="left", wraplength=340, text_color=P["text"],
                     font=ctk.CTkFont(size=12)).pack(padx=10, pady=6)
        t.geometry(f"+{x}+{y}")
        self._tip = t

    def _hide(self, _e=None):
        self._cancel()
        if self._tip is not None:
            try:
                self._tip.destroy()
            except tk.TclError:
                pass
            self._tip = None


class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.cfg = core.Config.load()
        style.apply_theme(ctk)
        self.configure(fg_color=P["bg"])
        self.title(f"Dofus Price Helper {core.app_version()}")
        ctk.set_widget_scaling(self.cfg.ui_scale if 0.5 <= self.cfg.ui_scale <= 2 else 1.0)
        self.geometry("1120x800")
        self.minsize(980, 680)
        self._restore_geometry()

        self.engine = core.PriceEngine(self.cfg)
        self.engine.progress = lambda r: self.ui_events.put(
            ("log", ("   " + r.message, {"warn": "WARN", "error": "ERROR"}.get(r.level, "OK"))))
        self.engine.on_loop_progress = lambda d: self.ui_events.put(("loop_progress", d))
        self.jobs: "queue.Queue[tuple]" = queue.Queue()
        self.ui_events: "queue.Queue[tuple]" = queue.Queue()
        self._save_after: Optional[str] = None
        self.hk_labels: dict = {}      # raccourci -> [(libellé, suffixe)]
        self.hk_buttons: dict = {}     # raccourci -> bouton « Changer »
        self._capturing: Optional[str] = None
        # journal : toutes les lignes (pour les filtres) et les blocs Ctrl+F3 repliables
        self.log_entries: list = []    # dicts : t, msg, tag, cat, block, header
        self.log_blocks: dict = {}     # id -> {"title", "collapsed", "problems"}
        self._block: Optional[int] = None
        self._block_seq = 0
        self.runs = load_runs()        # derniers parcours Ctrl+F3 (onglet Mes ventes)
        self.hdv_state: Optional[str] = None   # None (pas encore lu) | "ok" | "lost"
        self.last_action = ("En attente d'une action…", "", MUTED)
        self._compact = None
        self._loop: Optional[dict] = None   # boucle en cours (F2 / Ctrl+F3) : type, début
        self.activity: list = []             # panneau Activité : dernières actions (récentes d'abord)
        self._cheat = None                   # aide-mémoire affiché par-dessus le jeu

        self._build_vars()
        self._build_ui()
        self._setup_log_tags()

        threading.Thread(target=self._worker, daemon=True).start()
        self._poll_ui()
        self._unstick_keys()

        err = core.setup_tesseract(self.cfg)
        if err:
            self._log(err, "ERROR")
        if self.cfg.check_updates:
            threading.Thread(target=lambda: self.ui_events.put(
                ("update", dofus_update.find_update(core.app_version()))), daemon=True).start()
        if core.TESSERACT_USED:
            self._log(f"[OCR] {core.TESSERACT_USED}. Réglages : {core.BASE_DIR}", "INFO")
        self._register_hotkeys()
        self._refresh_status()
        self._apply_topmost()
        self.after(300, self._apply_style)   # après la mise en place de la barre de titre par CTk
        if not self._calibrated():
            self.after(800, self._first_launch)   # 1er lancement : calibration automatique proposée
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _calibrated(self) -> bool:
        c = self.cfg
        return bool(c.table_region and c.qty_region and c.price_field)

    def _restore_geometry(self):
        g = self.cfg.window_geometry
        if g == "zoomed":
            self.after(50, lambda: self.state("zoomed"))
        elif g:
            try:
                ok = geometry_on_screen(g, core.screen_bounds())
            except Exception:
                ok = False
            if ok:
                self.geometry(g)

    def _first_launch(self):
        """Pas encore calibré : propose la calibration automatique (l'assistant reste possible)."""
        w = ctk.CTkToplevel(self)
        w.title("Bienvenue")
        w.geometry("520x260")
        w.attributes("-topmost", True)
        w.resizable(False, False)
        ctk.CTkLabel(w, text="Première étape : la calibration", font=ctk.CTkFont(size=17, weight="bold")
                     ).pack(anchor="w", padx=18, pady=(16, 6))
        ctk.CTkLabel(w, text="Dans le jeu, ouvre l'Hôtel de vente sur l'onglet « Vente » et sélectionne "
                             "une de tes ventes (ou un objet de l'inventaire), bien visible.\n\nClique ensuite "
                             "« Calibration automatique » : tu as "
                             f"{self.cfg.calib_countdown} s pour revenir sur le jeu, l'outil trouve l'HDV et "
                             "place toutes les zones.",
                     wraplength=480, justify="left", anchor="w").pack(fill="x", padx=18)

        def auto():
            w.destroy()
            self.tabs.set("Calibration")
            self._countdown("automatique", self._calib_auto_ui)

        def wizard():
            w.destroy()
            self._open_wizard()

        ctk.CTkButton(w, text="✨ Calibration automatique", height=40, font=ctk.CTkFont(size=14, weight="bold"),
                      command=auto).pack(fill="x", padx=18, pady=(18, 6))
        bar = ctk.CTkFrame(w, fg_color="transparent")
        bar.pack(fill="x", padx=18)
        ctk.CTkButton(bar, text="Assistant pas à pas", fg_color=BTN2, hover_color=BTN2_HOVER, command=wizard).pack(side="left")
        ctk.CTkButton(bar, text="Plus tard", fg_color=BTN2, hover_color=BTN2_HOVER, width=90, command=w.destroy).pack(side="right")

    # ------------------------------------------------------------------ UI
    def _build_vars(self):
        c = self.cfg
        self.v = {
            "undercut_mode": ctk.StringVar(value=UNDERCUT_LABELS.get(c.undercut_mode, "kamas")),
            "undercut_value": ctk.StringVar(value=f"{c.undercut_value:g}"),
            "rounding": ctk.StringVar(value=ROUNDING_LABELS.get(c.rounding, ROUNDING_LABELS["none"])),
            "min_price": ctk.StringVar(value=str(c.min_price)),
            "floor_mode": ctk.StringVar(value=FLOOR_LABELS.get(c.floor_mode, FLOOR_LABELS["floor"])),
            "floor_ratio": ctk.StringVar(value=f"{c.floor_ratio * 100:g}"),
            "relist_max": ctk.StringVar(value=str(c.relist_max)),
            "relist_rows": ctk.StringVar(value=str(c.relist_rows)),
            "relist_scroll_page": ctk.DoubleVar(value=c.relist_scroll_page),
            "auto_paste": ctk.BooleanVar(value=c.auto_paste),
            "click_field": ctk.BooleanVar(value=c.click_field),
            "auto_validate": ctk.BooleanVar(value=c.auto_validate),
            "require_focus": ctk.BooleanVar(value=c.require_focus),
            "sound": ctk.BooleanVar(value=c.sound),
            "toast": ctk.BooleanVar(value=c.toast),
            "relist_auto": ctk.BooleanVar(value=c.relist_auto),
            "relist_confirm_enter": ctk.BooleanVar(value=c.relist_confirm_enter),
            "relist_summary": ctk.BooleanVar(value=c.relist_summary),
            "auto_recalibrate": ctk.BooleanVar(value=c.auto_recalibrate),
            "fast_digits": ctk.BooleanVar(value=c.fast_digits),
            "banner": ctk.BooleanVar(value=c.banner),
            "verify_before_enter": ctk.BooleanVar(value=c.verify_before_enter),
            "smart_f1": ctk.BooleanVar(value=c.smart_f1),
            "always_on_top": ctk.BooleanVar(value=c.always_on_top),
            "check_updates": ctk.BooleanVar(value=c.check_updates),
            "notify": ctk.BooleanVar(value=c.notify),
        }
        for var in self.v.values():
            var.trace_add("write", lambda *_: self._schedule_save())
        self.status_var = ctk.StringVar(value="")
        self.qty_var = ctk.StringVar(value="-")
        self.read_vars = {lot: ctk.StringVar(value="—") for lot in self.cfg.lots}
        self.unit_vars = {lot: ctk.StringVar(value="") for lot in self.cfg.lots}
        self.avg_var = ctk.StringVar(value="—")
        self.mine_var = ctk.StringVar(value="—")
        self.engine_var = ctk.StringVar(value="—")
        self.digits_var = ctk.StringVar(value="")
        self.profile_var = ctk.StringVar(value=self.cfg.profile)
        self.stats_var = ctk.StringVar(value="")
        self.preview_var = ctk.StringVar(value="")
        self.log_filter = ctk.StringVar(value="Tout")
        self.scale_var = ctk.StringVar(value=scale_label(self.cfg.ui_scale))
        for name in ("undercut_mode", "undercut_value", "rounding", "min_price", "floor_mode", "floor_ratio"):
            self.v[name].trace_add("write", lambda *_: self._update_preview())
        self.scroll_lbl = ctk.StringVar(value="")
        self.stats = {"ventes": 0, "modifs": 0, "suspects": 0}

    def _tip(self, widget, text: str):
        Tooltip(widget, text)
        return widget

    def _switch(self, parent, text: str, var: str, tip: str = "", **kw):
        """Interrupteur d'option (avec son aide au survol)."""
        s = ctk.CTkSwitch(parent, text=text, variable=self.v[var], **kw)
        s.pack(anchor="w", pady=2)
        if tip:
            self._tip(s, tip)
        return s

    def _section(self, parent, title: str, sub: str = "", tip: str = ""):
        f = ctk.CTkFrame(parent, fg_color=CARD, border_width=1, border_color=P["border"], corner_radius=12)
        f.pack(fill="x", padx=6, pady=(8, 2))
        hr = ctk.CTkFrame(f, fg_color="transparent")
        hr.pack(fill="x", padx=14, pady=(10, 0))
        ctk.CTkLabel(hr, text=title, font=ctk.CTkFont(size=14, weight="bold")).pack(side="left")
        if tip:
            self._tip(ctk.CTkLabel(hr, text=" ⓘ", text_color=MUTED, cursor="question_arrow"), tip
                      ).pack(side="left")
        if sub:
            ctk.CTkLabel(f, text=sub, text_color=MUTED, font=ctk.CTkFont(size=12), anchor="w",
                         wraplength=500, justify="left").pack(anchor="w", fill="x", padx=14)
        body = ctk.CTkFrame(f, fg_color="transparent")
        body.pack(fill="x", padx=12, pady=(6, 12))
        return body

    def _collapsible(self, parent, title: str, sub: str = "", opened: bool = False):
        """Section repliable (« ▸ Avancé ») : retourne le cadre du contenu."""
        outer = ctk.CTkFrame(parent, fg_color="transparent")
        outer.pack(fill="x", padx=0, pady=(10, 2))
        body = ctk.CTkFrame(outer, fg_color="transparent")
        state = {"open": opened}

        def label():
            return ("▾ " if state["open"] else "▸ ") + title

        def toggle():
            state["open"] = not state["open"]
            btn.configure(text=label())
            if state["open"]:
                body.pack(fill="x")
            else:
                body.pack_forget()

        btn = ctk.CTkButton(outer, text=label(), anchor="w", fg_color=CARD, hover_color=P["card2"], border_width=1, border_color=P["border"], text_color=P["text"],
                            font=ctk.CTkFont(size=13, weight="bold"), height=32, command=toggle)
        btn.pack(fill="x", padx=6)
        if sub:
            ctk.CTkLabel(outer, text=sub, text_color=MUTED, font=ctk.CTkFont(size=11), anchor="w"
                         ).pack(fill="x", padx=16)
        if opened:
            body.pack(fill="x")
        return body

    def _row(self, parent):
        r = ctk.CTkFrame(parent, fg_color="transparent")
        r.pack(fill="x", pady=2)
        return r

    def _build_ui(self):
        hk = self.cfg.hotkeys
        self.grid_columnconfigure(0, weight=3)
        self.grid_columnconfigure(1, weight=2)
        self.grid_rowconfigure(1, weight=1)
        self.grid_rowconfigure(2, weight=0)   # journal : hauteur fixe, le reste aux onglets

        # ---------------- en-tête
        wrap = ctk.CTkFrame(self, fg_color="transparent", corner_radius=0)
        wrap.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(4, 0))
        head = ctk.CTkFrame(wrap, fg_color="transparent")
        head.pack(fill="x")
        ctk.CTkLabel(head, text="◆", text_color=P["gold"], font=ctk.CTkFont(size=20)
                     ).pack(side="left", padx=(16, 6), pady=10)
        ctk.CTkLabel(head, text="Dofus Price Helper", font=ctk.CTkFont(size=19, weight="bold")
                     ).pack(side="left")
        ctk.CTkLabel(head, text=core.app_version(), text_color=MUTED, font=ctk.CTkFont(size=12)
                     ).pack(side="left", padx=(8, 10), pady=(6, 0))
        info = ctk.CTkFrame(wrap, fg_color="transparent")
        info.pack(fill="x", padx=12, pady=(0, 6))
        # barre d'état : une pastille par chose à surveiller (cliquable)
        chips = ctk.CTkFrame(info, fg_color="transparent")
        chips.pack(side="left")
        self.chips = {}
        for key, tip, action in (
                ("state", "Raccourcis actifs ou en pause. Clic = pause / reprise.", self._toggle_pause),
                ("profile", "Profil de calibration actif (un par HDV ou personnage). Clic = onglet Calibration.",
                 lambda: self.tabs.set("Calibration")),
                ("calib", "Zones de base : tableau, quantité, champ « Prix du lot ». Clic = onglet Calibration.",
                 lambda: self.tabs.set("Calibration")),
                ("hdv", "L'HDV a-t-il été vu à la dernière action ? Avec le repère « Hôtel de vente », "
                        "les zones suivent l'HDV si tu le déplaces.", lambda: self.jobs.put(("read", None)))):
            lbl = ctk.CTkLabel(chips, text="", corner_radius=13, fg_color=BTN2, height=26,
                               font=ctk.CTkFont(size=12, weight="bold"), cursor="hand2")
            lbl.pack(side="left", padx=3, ipadx=10)
            lbl.bind("<Button-1>", lambda _e, a=action: a(), add="+")
            self._tip(lbl, tip)
            self.chips[key] = lbl
        # progression d'une boucle (F2 / Ctrl+F3), affichée seulement pendant la boucle
        self.loop_bar = ctk.CTkFrame(info, fg_color=CARD, corner_radius=13, border_width=1,
                                     border_color=P["border"])
        self.loop_lbl = ctk.CTkLabel(self.loop_bar, text="", font=ctk.CTkFont(size=12, weight="bold"))
        self.loop_lbl.pack(side="left", padx=(12, 8))
        self.loop_pb = ctk.CTkProgressBar(self.loop_bar, width=140, height=8, progress_color=P["accent"])
        self.loop_pb.pack(side="left", padx=4)
        self.loop_stop = ctk.CTkButton(self.loop_bar, text="■ Arrêter", width=84, height=24,
                                       fg_color=style.CHIP["red"][0], hover_color="#5a2730",
                                       text_color=P["red"], command=self._stop_loop)
        self.loop_stop.pack(side="left", padx=(8, 4), pady=3)
        self._tip(ctk.CTkButton(head, text="🗗 Compact", width=90, fg_color=BTN2, hover_color=BTN2_HOVER, command=self._open_compact),
                  "Petite fenêtre toujours au premier plan pendant que tu joues : dernière action, état, "
                  "pause.").pack(side="right", padx=(4, 12))
        self._tip(ctk.CTkCheckBox(head, text="📌", variable=self.v["always_on_top"], width=44),
                  "Fenêtre de l'outil toujours au-dessus du jeu.").pack(side="right", padx=(8, 2))
        self.pause_btn = ctk.CTkButton(head, text="⏸ Pause", width=90, command=self._toggle_pause)
        self.pause_btn.pack(side="right", padx=4)
        self.update_btn = ctk.CTkButton(head, text="", width=150, fg_color=style.CHIP["green"][0],
                                        hover_color="#1c4535", text_color=P["green"])   # affiché si une version plus récente existe

        # ---------------- onglets
        tabs = ctk.CTkTabview(self, anchor="nw", fg_color="transparent", corner_radius=12)
        tabs.grid(row=1, column=0, sticky="nsew", padx=(8, 4), pady=(0, 4))
        self.tabs = tabs
        for name in ("Accueil", "Prix", "Mes ventes", "Calibration", "Raccourcis", "Options"):
            tabs.add(name)
        tabs.set("Accueil")
        self._tab_home(ctk.CTkScrollableFrame(tabs.tab("Accueil"), fg_color="transparent"), hk)
        self._tab_shortcuts(ctk.CTkScrollableFrame(tabs.tab("Raccourcis"), fg_color="transparent"), hk)
        self._tab_prices(ctk.CTkScrollableFrame(tabs.tab("Prix"), fg_color="transparent"))
        self._tab_relist(ctk.CTkScrollableFrame(tabs.tab("Mes ventes"), fg_color="transparent"), hk)
        self._tab_calibration(ctk.CTkScrollableFrame(tabs.tab("Calibration"), fg_color="transparent"))
        self._tab_options(ctk.CTkScrollableFrame(tabs.tab("Options"), fg_color="transparent"))

        # ---------------- activité : dernières actions + dernière lecture
        side = ctk.CTkFrame(self, fg_color=CARD, border_width=1, border_color=P["border"], corner_radius=12)
        side.grid(row=1, column=1, sticky="nsew", padx=(4, 12), pady=(14, 4))
        ctk.CTkLabel(side, text="Activité", font=ctk.CTkFont(size=15, weight="bold")
                     ).pack(anchor="w", padx=14, pady=(12, 2))
        self.act_box = ctk.CTkFrame(side, fg_color="transparent")
        self.act_box.pack(fill="x", padx=10)
        self.act_empty = ctk.CTkLabel(
            self.act_box, text="Aucune action pour l'instant.\nOuvre l'HDV, sélectionne un objet de ton "
                               f"inventaire et appuie sur {self.cfg.hotkeys['sell'].upper()}.",
            text_color=MUTED, justify="left", anchor="w", wraplength=360)
        self.act_rows = []
        for _ in range(self.ACTIVITY_ROWS):
            r = ctk.CTkFrame(self.act_box, fg_color="transparent")
            t = ctk.CTkLabel(r, text="", text_color=MUTED, width=40, anchor="w", font=ctk.CTkFont(size=12))
            t.pack(side="left")
            hint = ctk.CTkLabel(r, text="", anchor="e", font=ctk.CTkFont(size=12))
            hint.pack(side="right", padx=(6, 2))
            txt = ctk.CTkLabel(r, text="", anchor="w", font=ctk.CTkFont(size=12, weight="bold"))
            txt.pack(side="left", fill="x", expand=True)
            self.act_rows.append((r, t, txt, hint))
        ctk.CTkFrame(side, fg_color=P["border"], height=1).pack(fill="x", padx=14, pady=(8, 6))
        hr = ctk.CTkFrame(side, fg_color="transparent")
        hr.pack(fill="x", padx=14)
        ctk.CTkLabel(hr, text="Dernière lecture", font=ctk.CTkFont(size=13, weight="bold")).pack(side="left")
        self.read_info = ctk.CTkLabel(hr, text="", text_color=MUTED, font=ctk.CTkFont(size=12))
        self.read_info.pack(side="right")
        self.read_empty = ctk.CTkLabel(side, text="Pas encore de lecture. Elle s'affiche ici à chaque "
                                                  "vente, ou avec « Lire (test) » (onglet Calibration).",
                                       text_color=MUTED, justify="left", anchor="w", wraplength=360)
        self.read_grid = grid = ctk.CTkFrame(side, fg_color=P["card2"], corner_radius=8)
        for c, t in enumerate(("Lot", "Prix", "Par objet")):
            ctk.CTkLabel(grid, text=t, text_color=MUTED, height=22).grid(
                row=0, column=c, sticky="w" if c == 0 else "e", padx=10, pady=(4, 0))
        for i, lot in enumerate(self.cfg.lots, start=1):
            ctk.CTkLabel(grid, text=str(lot), height=22).grid(row=i, column=0, sticky="w", padx=10)
            ctk.CTkLabel(grid, textvariable=self.read_vars[lot], text_color=P["gold"], height=22,
                         font=ctk.CTkFont(size=13, weight="bold")).grid(row=i, column=1, sticky="e", padx=10)
            ctk.CTkLabel(grid, textvariable=self.unit_vars[lot], text_color=MUTED, height=22
                         ).grid(row=i, column=2, sticky="e", padx=10)
        ctk.CTkFrame(grid, fg_color="transparent", height=4).grid(row=len(self.cfg.lots) + 1, column=0)
        grid.grid_columnconfigure(1, weight=1)
        self.read_empty.pack(anchor="w", fill="x", padx=14, pady=4)
        ctk.CTkLabel(side, textvariable=self.status_var, text_color=MUTED, wraplength=380,
                     justify="left").pack(side="bottom", anchor="w", padx=14, pady=(0, 10))
        self._refresh_activity()

        # ---------------- journal
        lf = ctk.CTkFrame(self, fg_color=CARD, border_width=1, border_color=P["border"], corner_radius=12)
        lf.grid(row=2, column=0, columnspan=2, sticky="nsew", padx=12, pady=(6, 12))
        top = ctk.CTkFrame(lf, fg_color="transparent")
        top.pack(fill="x", padx=8, pady=(6, 0))
        ctk.CTkLabel(top, text="Journal", font=ctk.CTkFont(weight="bold")).pack(side="left", padx=4)
        ctk.CTkSegmentedButton(top, values=list(LOG_FILTERS), variable=self.log_filter, height=24,
                               command=lambda _v: self._render_log()).pack(side="left", padx=10)
        ctk.CTkButton(top, text="Effacer", width=70, height=24, fg_color=BTN2, hover_color=BTN2_HOVER,
                      command=self._clear_log).pack(side="right")
        self.copy_btn = self._tip(ctk.CTkButton(top, text="Copier", width=70, height=24, fg_color=BTN2, hover_color=BTN2_HOVER,
                                                command=self._copy_log),
                                  "Copie les lignes affichées (selon le filtre) : à coller dans un message "
                                  "quand tu signales un problème.")
        self.copy_btn.pack(side="right", padx=6)
        body = ctk.CTkFrame(lf, fg_color="transparent")
        body.pack(fill="both", expand=True)
        self.log_text = tk.Text(body, wrap="word", bg=P["log_bg"], fg=P["text"], relief="flat",
                                font=("Consolas", self._log_font_size()), padx=6, pady=4, height=6,
                                highlightthickness=0, borderwidth=0)
        self.log_text.configure(state="disabled")
        self.log_text.pack(side="left", fill="both", expand=True, padx=(10, 0), pady=(6, 10))
        sb = ctk.CTkScrollbar(body, command=self.log_text.yview, height=40)
        sb.pack(side="right", fill="y", padx=(0, 8), pady=(6, 10))
        self.log_text.configure(yscrollcommand=sb.set)

    ACTIVITY_ROWS = 7

    # ---- onglet Accueil
    HOME_KEYS = (("sell", "Vendre", "Objet de l'inventaire : prix juste sous le moins cher. Sur une de tes "
                                    "ventes : la met à jour."),
                 ("sell_all", "Tout vendre", "Remet en vente au même prix tant que c'est sûr."),
                 ("relist", "Remettre sous le moins cher", "La vente sélectionnée dans « mes ventes »."),
                 ("relist_all", "Toute la liste", "Met à jour toutes tes ventes, une par une."))

    def _tab_home(self, page, hk):
        page.pack(fill="both", expand=True)
        # premiers pas : se cochent tout seuls, disparaissent quand tout est fait
        self.steps_card = self._section(page, "Premiers pas", "Trois étapes, cochées automatiquement.")
        self.steps_outer = self.steps_card.master
        self.step_rows = {}
        actions = {"calib": ("Calibrer", lambda: (self.tabs.set("Calibration"),
                                                  self._countdown("automatique", self._calib_auto_ui))),
                   "read": ("Tester", lambda: self.jobs.put(("read", None))),
                   "sell": (None, None)}
        hints = {"calib": "HDV ouvert sur l'onglet « Vente », puis « Calibrer » : tout est placé tout seul.",
                 "read": "Sélectionne un objet de ton inventaire dans l'HDV, puis « Tester ».",
                 "sell": f"Sélectionne un objet de ton inventaire et appuie sur {hk['sell'].upper()}."}
        for key, title in FIRST_STEPS:
            r = self._row(self.steps_card)
            mark = ctk.CTkLabel(r, text="", width=28, font=ctk.CTkFont(size=16, weight="bold"))
            mark.pack(side="left")
            label, cmd = actions[key]
            btn = None
            if label:
                btn = ctk.CTkButton(r, text=label, width=90, height=28, command=cmd)
                btn.pack(side="right", padx=4)
            col = ctk.CTkFrame(r, fg_color="transparent")
            col.pack(side="left", fill="x", expand=True)
            ctk.CTkLabel(col, text=title, anchor="w", font=ctk.CTkFont(size=13, weight="bold")).pack(fill="x")
            ctk.CTkLabel(col, text=hints[key], anchor="w", text_color=MUTED, wraplength=360, justify="left",
                         font=ctk.CTkFont(size=12)).pack(fill="x")
            self.step_rows[key] = (mark, btn)
        # touches principales en grosses cartes
        kb = self._section(page, "Touches principales", "Dans le jeu, HDV ouvert.")
        grid = ctk.CTkFrame(kb, fg_color="transparent")
        grid.pack(fill="x")
        grid.grid_columnconfigure((0, 1), weight=1, uniform="k")
        self.relist_all_note = None
        for i, (name, title, desc) in enumerate(self.HOME_KEYS):
            card = ctk.CTkFrame(grid, fg_color=P["card2"], corner_radius=10)
            card.grid(row=i // 2, column=i % 2, sticky="nsew", padx=4, pady=4)
            self._hk_label(card, name, text_color=P["gold"], anchor="w",
                           font=ctk.CTkFont(family=style.MONO, size=18, weight="bold")
                           ).pack(fill="x", padx=12, pady=(10, 0))
            ctk.CTkLabel(card, text=title, anchor="w", font=ctk.CTkFont(size=13, weight="bold")
                         ).pack(fill="x", padx=12)
            ctk.CTkLabel(card, text=desc, anchor="w", justify="left", wraplength=220, text_color=MUTED,
                         font=ctk.CTkFont(size=12)).pack(fill="x", padx=12, pady=(0, 4))
            if name == "relist_all":
                self.relist_all_note = ctk.CTkButton(
                    card, text="Désactivé : activer dans « Mes ventes »", height=22, anchor="w",
                    fg_color="transparent", hover_color=P["btn2"], text_color=P["orange"],
                    font=ctk.CTkFont(size=12), command=lambda: self.tabs.set("Mes ventes"))
            ctk.CTkFrame(card, fg_color="transparent", height=6).pack(side="bottom")
        r = self._row(kb)
        ctk.CTkButton(r, text="Tous les raccourcis", width=150, fg_color=BTN2, hover_color=BTN2_HOVER,
                      command=lambda: self.tabs.set("Raccourcis")).pack(side="left", pady=(4, 0))
        self._tip(ctk.CTkButton(r, text="Aide-mémoire en jeu", width=170, fg_color=BTN2,
                                hover_color=BTN2_HOVER, command=self._toggle_cheatsheet),
                  "Affiche les touches par-dessus le jeu, au-dessus de l'HDV. En jeu : "
                  f"{hk['cheatsheet'].upper()}.").pack(side="left", padx=8, pady=(4, 0))
        # session
        sb = self._section(page, "Cette session")
        tiles = ctk.CTkFrame(sb, fg_color="transparent")
        tiles.pack(fill="x")
        tiles.grid_columnconfigure((0, 1, 2), weight=1, uniform="t")
        self.tiles = {}
        for i, (key, label, color) in enumerate((("ventes", "mises en vente", P["green"]),
                                                  ("modifs", "prix mis à jour", P["accent"]),
                                                  ("suspects", "lectures suspectes", P["orange"]))):
            t = ctk.CTkFrame(tiles, fg_color=P["card2"], corner_radius=10)
            t.grid(row=0, column=i, sticky="nsew", padx=4)
            n = ctk.CTkLabel(t, text="0", text_color=color, font=ctk.CTkFont(size=24, weight="bold"))
            n.pack(pady=(8, 0))
            ctk.CTkLabel(t, text=label, text_color=MUTED, font=ctk.CTkFont(size=12)).pack(pady=(0, 8))
            self.tiles[key] = n
        ctk.CTkLabel(sb, textvariable=self.stats_var, text_color=MUTED, font=ctk.CTkFont(size=12),
                     anchor="w", justify="left").pack(fill="x", pady=(6, 0))
        self._refresh_home()

    def _step_done(self, key: str) -> bool:
        return self._calibrated() if key == "calib" else key in (self.cfg.first_steps or [])

    def _mark_step(self, key: str):
        if key not in (self.cfg.first_steps or []):
            self.cfg.first_steps = list(self.cfg.first_steps or []) + [key]
            self._save_cfg()
            self._refresh_home()

    def _refresh_home(self):
        if not hasattr(self, "tiles"):
            return
        all_done = True
        for key, (mark, btn) in self.step_rows.items():
            done = self._step_done(key)
            all_done = all_done and done
            mark.configure(text="✓" if done else "○", text_color=P["green"] if done else MUTED)
            if btn is not None:
                btn.configure(fg_color=BTN2 if done else P["accent"],
                              hover_color=BTN2_HOVER if done else P["accent_hover"])
        if all_done:
            self.steps_outer.pack_forget()
        for key, lbl in self.tiles.items():
            lbl.configure(text=str(self.stats[key]))
        note = self.relist_all_note
        if note is not None:
            if self.cfg.relist_auto:
                note.pack_forget()
            elif not note.winfo_ismapped():
                note.pack(fill="x", padx=6, pady=(0, 2))

    # ---- panneau Activité
    def _add_activity(self, res: core.Result):
        self.activity.insert(0, action_entry(res))
        del self.activity[self.ACTIVITY_ROWS:]
        self._refresh_activity()

    def _refresh_activity(self):
        if not self.activity:
            self.act_empty.pack(anchor="w", fill="x", padx=4, pady=4)
        else:
            self.act_empty.pack_forget()
        colors = {"ok": P["green"], "warn": P["orange"], "error": P["red"]}
        for i, (r, t, txt, hint) in enumerate(self.act_rows):
            if i < len(self.activity):
                e = self.activity[i]
                t.configure(text=e["time"])
                txt.configure(text=e["text"])
                hint.configure(text=e["hint"], text_color=colors.get(e["level"], MUTED))
                r.pack(fill="x", padx=4, pady=1)
            else:
                r.pack_forget()

    # ---- onglets
    def _tab_shortcuts(self, page, hk):
        page.pack(fill="both", expand=True)
        b = self._section(page, "Vendre (onglet Vente de l'HDV)",
                          "« Changer » puis appuie sur la nouvelle touche ou combinaison (Échap = annuler).")
        for name in ("sell", "sell_all", "optimize"):
            self._hotkey_line(b, name, HOTKEY_LABELS[name])
        b = self._section(page, "Mes ventes (liste de tes ventes en cours)")
        for name in ("relist", "relist_all"):
            self._hotkey_line(b, name, HOTKEY_LABELS[name])
        b = self._section(page, "Divers")
        self._hotkey_line(b, None, "Forcer une lecture jugée suspecte", literal="même touche ×2")
        for name in ("pause", "show_zones", "cheatsheet"):
            self._hotkey_line(b, name, HOTKEY_LABELS[name])
        adv = self._collapsible(page, "Avancé : raccourcis de calibration",
                                "Rarement utiles : la calibration automatique place tout.")
        b = self._section(adv, "Raccourcis de calibration", "Utilisés dans le jeu, souris sur la zone.")
        for name in CALIB_HOTKEYS:
            self._hotkey_line(b, name, HOTKEY_LABELS[name])
        b = self._section(page, "Tous les raccourcis")
        ctk.CTkButton(b, text="Rétablir les raccourcis par défaut", width=230, fg_color=BTN2, hover_color=BTN2_HOVER,
                      command=self._reset_hotkeys).pack(anchor="w", pady=(2, 2))
        b = self._section(page, "Vente rapide", "Ce que fait la touche de vente après avoir calculé le prix.")
        self._switch(b, "Coller le prix automatiquement", "auto_paste",
                     tip="Sinon le prix est seulement copié : colle-le toi-même avec Ctrl+V.")
        self._switch(b, "Cliquer sur « Prix du lot » avant de coller", "click_field",
                     tip="Donne le focus au champ avant de coller. Demande le point « Prix du lot » calibré.")
        self._switch(b, "Mettre en vente automatiquement (Entrée) ⚠️", "auto_validate", progress_color=ORANGE,
                     tip="La vente part sans que tu vérifies le prix (sauf lecture suspecte). Avec « Relire "
                         "Prix du lot » (onglet Options), le prix collé est relu avant de valider.")

    def _hk_label(self, parent, name: str, suffix: str = "", **kw):
        """Libellé d'un raccourci, mis à jour quand on le change (_refresh_hotkey_labels)."""
        lbl = ctk.CTkLabel(parent, text=self.cfg.hotkeys[name].upper() + suffix, **kw)
        self.hk_labels.setdefault(name, []).append((lbl, suffix))
        return lbl

    def _refresh_hotkey_labels(self):
        for name, lbls in self.hk_labels.items():
            for lbl, suffix in lbls:
                lbl.configure(text=self.cfg.hotkeys[name].upper() + suffix)

    def _hotkey_line(self, parent, name: Optional[str], text: str, literal: str = ""):
        r = self._row(parent)
        kstyle = dict(width=120, corner_radius=6, fg_color=P["card2"],
                     font=ctk.CTkFont(family="Consolas", weight="bold"))
        if name:
            self._hk_label(r, name, **kstyle).pack(side="left", padx=(2, 10))
            btn = ctk.CTkButton(r, text="Changer", width=80, height=24, fg_color=BTN2, hover_color=BTN2_HOVER,
                                command=lambda n=name: self._capture_hotkey(n))
            btn.pack(side="right", padx=4)
            self.hk_buttons[name] = btn
        else:
            ctk.CTkLabel(r, text=literal.upper(), **kstyle).pack(side="left", padx=(2, 10))
        ctk.CTkLabel(r, text=text, anchor="w", justify="left", wraplength=300
                     ).pack(side="left", fill="x", expand=True)

    # ---- changement de raccourci
    def _capture_hotkey(self, name: str):
        if not KEYBOARD_AVAILABLE:
            self._log("[Hotkeys] Module 'keyboard' indisponible : raccourcis non modifiables.", "ERROR")
            return
        if self._capturing:
            return
        self._capturing = name
        self.hk_buttons[name].configure(text="Appuie…", fg_color=ORANGE)
        self._log(f"[Hotkeys] « {HOTKEY_LABELS[name]} » : appuie sur la nouvelle touche ou combinaison "
                  "(Échap = annuler).", "CAL")
        try:
            core.HOTKEYS.clear()   # sinon la touche choisie déclencherait son action actuelle
        except Exception:
            pass

        def read():
            try:
                combo = keyboard.read_hotkey(suppress=False)
            except Exception as e:
                combo = f"!{e}"
            self.ui_events.put(("hotkey", (name, combo)))
        threading.Thread(target=read, daemon=True).start()

    def _on_hotkey_captured(self, name: str, combo: str):
        self._capturing = None
        self.hk_buttons[name].configure(text="Changer", fg_color=BTN2)
        err = hotkey_problem(name, combo, self.cfg.hotkeys)
        if combo == "esc":
            self._log("[Hotkeys] Changement annulé.", "INFO")
        elif err:
            self._log(f"[Hotkeys] {combo.upper()} refusé : {err}.", "ERROR")
        else:
            self.cfg.hotkeys[name] = combo
            self.cfg.save()
            self._log(f"[Hotkeys] « {HOTKEY_LABELS[name]} » = {combo.upper()}.", "OK")
            self._refresh_hotkey_labels()
        self._register_hotkeys()

    def _reset_hotkeys(self):
        if self._capturing:
            return
        self.cfg.hotkeys = dict(core.DEFAULT_HOTKEYS)
        self.cfg.save()
        self._refresh_hotkey_labels()
        self._register_hotkeys()
        self._log("[Hotkeys] Raccourcis par défaut rétablis.", "WARN")

    def _tab_prices(self, page):
        page.pack(fill="both", expand=True)
        pv = self._section(page, "Aperçu", tip="Exemple calculé avec tes réglages (lot de 1, prix moyen "
                                               f"{fmt(PREVIEW_AVG)}). Change dès que tu modifies un réglage.")
        self.preview_lbl = ctk.CTkLabel(pv, textvariable=self.preview_var, justify="left", anchor="w",
                                        font=ctk.CTkFont(size=13), text_color=P["green"], wraplength=480)
        self.preview_lbl.pack(anchor="w", fill="x", padx=2)
        b = self._section(page, "Undercut", "De combien passer sous le moins cher.")
        r = self._row(b)
        ctk.CTkSegmentedButton(r, values=list(UNDERCUT_LABELS.values()), variable=self.v["undercut_mode"]
                               ).pack(side="left")
        self._tip(ctk.CTkEntry(r, textvariable=self.v["undercut_value"], width=70),
                  "En kamas : 1 = 1 kama de moins. En % : 1 = 1 % de moins.").pack(side="left", padx=8)
        r = self._row(b)
        self._tip(ctk.CTkLabel(r, text="Arrondi", width=90, anchor="w"),
                  "Toujours vers le bas : le prix ne remonte jamais au-dessus du moins cher.").pack(side="left")
        ctk.CTkOptionMenu(r, values=list(ROUNDING_LABELS.values()), variable=self.v["rounding"], width=170
                          ).pack(side="left")
        r = self._row(b)
        self._tip(ctk.CTkLabel(r, text="Prix min", width=90, anchor="w"),
                  "L'outil ne descend jamais sous ce prix.").pack(side="left")
        ctk.CTkEntry(r, textvariable=self.v["min_price"], width=90).pack(side="left")
        b = self._section(page, "Prix plancher", "Protège contre un vendeur qui brade. 0 = désactivé.",
                          tip="Plancher = ce % du « Prix moyen » affiché par l'HDV (zone Prix moyen "
                              "requise, placée par la calibration automatique).")
        r = self._row(b)
        ctk.CTkEntry(r, textvariable=self.v["floor_ratio"], width=60).pack(side="left")
        ctk.CTkLabel(r, text="% du prix moyen").pack(side="left", padx=6)
        r = self._row(b)
        self._tip(ctk.CTkLabel(r, text="Concurrent en dessous", width=150, anchor="w"),
                  "Au plancher : tu vends au plancher. Garder mon prix : tes ventes en cours ne bougent "
                  "pas. Arrêt : la lecture est jugée suspecte et rien n'est fait.").pack(side="left")
        ctk.CTkOptionMenu(r, values=list(FLOOR_LABELS.values()), variable=self.v["floor_mode"], width=170
                          ).pack(side="left")
        self._update_preview()

    def _update_preview(self):
        if not hasattr(self, "preview_lbl"):
            return
        v = self.v
        try:
            mode = {lbl: k for k, lbl in UNDERCUT_LABELS.items()}.get(v["undercut_mode"].get(), "fixed")
            rounding = {lbl: k for k, lbl in ROUNDING_LABELS.items()}.get(v["rounding"].get(), "none")
            floor_mode = {lbl: k for k, lbl in FLOOR_LABELS.items()}.get(v["floor_mode"].get(), "floor")
            value = float(v["undercut_value"].get().replace(",", "."))
            min_price = int(v["min_price"].get())
            ratio = max(0.0, float(v["floor_ratio"].get().replace(",", ".") or 0) / 100)
        except (ValueError, tk.TclError):
            self.preview_var.set("Valeur invalide : corrige le champ pour voir l'aperçu.")
            self.preview_lbl.configure(text_color=P["orange"])
            return
        self.preview_var.set("\n".join(price_preview(mode, value, rounding, min_price, ratio, floor_mode,
                                                     self.cfg.min_avg_ratio)))
        self.preview_lbl.configure(text_color=P["green"])

    def _tab_relist(self, page, hk):
        page.pack(fill="both", expand=True)
        b = self._section(page, "Toute la liste",
                          tip="Clique chaque ligne, met à jour, défile et continue. Départ à la ligne sous "
                              "la souris. C'est le mode le plus risqué vis-à-vis des CGU d'Ankama.")
        self._switch(b, "Activer le parcours de toute la liste ⚠️", "relist_auto", progress_color=ORANGE,
                     tip="Sans cet interrupteur, le raccourci ne fait rien (sécurité).")
        self._switch(b, "Valider la fenêtre de confirmation avec Entrée", "relist_confirm_enter",
                     tip="Après « Modifier », si une fenêtre de confirmation reste ouverte, l'outil appuie "
                         "sur Entrée.")
        self._switch(b, "Fenêtre de résumé à la fin du parcours", "relist_summary",
                     tip="Prix modifiés et lignes à revoir, avec l'image du nom de chaque objet. Le résumé "
                         "reste aussi dans « Derniers parcours » ci-dessous.")
        r = self._row(b)
        self._tip(ctk.CTkLabel(r, text="Défilement", width=120, anchor="w"),
                  "De combien la liste défile entre deux lectures. Moins = plus sûr, plus = plus rapide."
                  ).pack(side="left")
        ctk.CTkSlider(r, from_=0.2, to=1.0, number_of_steps=8, variable=self.v["relist_scroll_page"],
                      width=180, command=lambda _v: self._update_scroll_lbl()).pack(side="left")
        ctk.CTkLabel(r, textvariable=self.scroll_lbl, text_color=MUTED).pack(side="left", padx=8)
        self._update_scroll_lbl()
        r = self._row(b)
        self._tip(ctk.CTkLabel(r, text="Lignes visibles", width=120, anchor="w"),
                  "Nombre de lignes entièrement visibles dans la liste de tes ventes.").pack(side="left")
        ctk.CTkEntry(r, textvariable=self.v["relist_rows"], width=60).pack(side="left")
        r = self._row(b)
        self._tip(ctk.CTkLabel(r, text="Lignes max / appui", width=120, anchor="w"),
                  "Garde-fou : le parcours s'arrête après ce nombre de lignes lues.").pack(side="left")
        ctk.CTkEntry(r, textvariable=self.v["relist_max"], width=60).pack(side="left")
        hb = self._section(page, "Derniers parcours",
                           f"Les {MAX_RUNS} derniers résumés du parcours de toute la liste. Clic = détail.")
        self.runs_box = ctk.CTkFrame(hb, fg_color="transparent")
        self.runs_box.pack(fill="x")
        self._refresh_runs()

    def _refresh_runs(self):
        box = getattr(self, "runs_box", None)
        if box is None:
            return
        for w in box.winfo_children():
            w.destroy()
        if not self.runs:
            ctk.CTkLabel(box, text="Aucun parcours pour l'instant.", text_color=MUTED).pack(anchor="w", pady=2)
            return
        for run in reversed(self.runs):
            bad = any(not c.modified for c in run["changes"])
            ctk.CTkButton(box, text=run_title(run), anchor="w", height=26, fg_color=BTN2, hover_color=BTN2_HOVER,
                          text_color=P["orange"] if bad else P["text"],
                          command=lambda r=run: self._summary_window(r)).pack(fill="x", pady=1)
        ctk.CTkButton(box, text="Effacer l'historique", width=150, height=24, fg_color="transparent",
                      border_width=1, border_color=BTN2, command=self._clear_runs).pack(anchor="e", pady=(6, 0))

    def _clear_runs(self):
        self.runs = []
        try:
            save_runs(self.runs)
        except OSError:
            pass
        self._refresh_runs()

    def _update_scroll_lbl(self):
        try:
            self.scroll_lbl.set(f"{self.v['relist_scroll_page'].get():.0%} d'une page")
        except tk.TclError:
            pass

    def _tab_calibration(self, page):
        page.pack(fill="both", expand=True)
        ab = self._section(page, "Calibration automatique",
                           "HDV ouvert sur l'onglet « Vente », une de tes ventes (ou un objet) sélectionnée, "
                           "puis clique.",
                           tip="L'outil trouve l'HDV et place toutes les zones, quelles que soient la "
                               "résolution et l'échelle de l'interface. Fonctionne avec Dofus 3 en français, "
                               "sur la même version du jeu que le modèle de l'outil : sinon, calibration "
                               "manuelle dans « Avancé ».")
        r = self._row(ab)
        ctk.CTkButton(r, text="✨ Calibration automatique", width=300, height=46,
                      font=ctk.CTkFont(size=15, weight="bold"),
                      command=lambda: self._countdown("automatique", self._calib_auto_ui)
                      ).pack(side="left", pady=4)
        self._hk_label(r, "calibrate_auto", text_color=MUTED,
                       font=ctk.CTkFont(family="Consolas")).pack(side="left", padx=12)
        self._tip(ctk.CTkButton(r, text="Voir zones", width=90, fg_color=BTN2, hover_color=BTN2_HOVER, command=self._show_zones),
                  "Vérifie où les zones ont été placées.").pack(side="right", padx=4)
        self._tip(ctk.CTkButton(r, text="Lire (test)", width=90, fg_color=BTN2, hover_color=BTN2_HOVER,
                                command=lambda: self.jobs.put(("read", None))),
                  "Lit l'HDV une fois sans rien vendre : résultat dans le journal et le panneau "
                  "Activité.").pack(side="right", padx=4)
        self._switch(ab, "Recalibrer tout seul si la taille de l'HDV change", "auto_recalibrate",
                     tip="Échelle de l'interface ou résolution changée : l'HDV n'est plus retrouvé à sa "
                         "taille calibrée. L'outil refait alors la calibration automatique (~1 s) avant "
                         "l'action, et l'écrit dans le journal.")
        pb = self._section(page, "Profil de calibration", "Un profil par HDV ou par personnage.",
                           tip="Un profil garde ses zones, ses points et son repère. « Nouveau » copie le "
                               "profil actuel : recalibre seulement ce qui change.")
        r = self._row(pb)
        self.profile_menu = ctk.CTkOptionMenu(r, values=self.cfg.profile_names(), variable=self.profile_var,
                                              width=220, dynamic_resizing=False, command=self._switch_profile)
        self.profile_menu.pack(side="left")
        ctk.CTkButton(r, text="Nouveau", width=90, fg_color=BTN2, hover_color=BTN2_HOVER, command=self._new_profile
                      ).pack(side="left", padx=(8, 4))
        ctk.CTkButton(r, text="Supprimer", width=90, fg_color=BTN2, hover_color=BTN2_HOVER, command=self._delete_profile
                      ).pack(side="left", padx=4)
        adv = self._collapsible(page, "Avancé : assistant et zones manuelles",
                                "Seulement si la calibration automatique échoue ou place mal une zone.")
        top = self._section(adv, "Assistant", "Pas à pas, avec une vérification à la fin.")
        ctk.CTkButton(top, text="🧭 Ouvrir l'assistant de calibration", width=260,
                      command=self._open_wizard).pack(anchor="w", pady=2)
        b = self._section(adv, "Zones et points",
                          f"« Calibrer » = compte à rebours de {self.cfg.calib_countdown} s pour placer la "
                          "souris, ou raccourci en jeu.",
                          tip="Zones : coin haut-gauche, puis coin bas-droit. Points : une position. "
                              "✕ efface une zone optionnelle.")
        self.calib_labels = {}
        items = [
            ("anchor", "Repère : titre « Hôtel de vente » (suivi)",
             ("calibrate_anchor", " ×2"), False, lambda: self._calib_rect_ui("anchor", "titre de l'HDV")),
            ("table", "Tableau « Actuellement en vente »", ("calibrate_table", " ×2"), True,
             lambda: self._calib_rect_ui("table", "tableau")),
            ("qty", "Menu « Quantité »", ("calibrate_qty", " ×2"), True,
             lambda: self._calib_rect_ui("qty", "quantité")),
            ("price_field", "Champ « Prix du lot » (sert aussi à lire ton prix)", ("calibrate_field", ""), True,
             lambda: self._countdown("champ Prix du lot", lambda: self._calib_point("price_field"))),
            ("avg", "Prix moyen (plancher, garde-fou)", ("calibrate_avg", " ×2"), False,
             lambda: self._calib_rect_ui("avg", "prix moyen")),
            ("count", "Compteur « x/100 lots » (F2 vérifié)", ("calibrate_count", " ×2"), False,
             lambda: self._calib_rect_ui("count", "compteur")),
            ("modify_button", "Bouton « Modifier » (sinon Entrée)", ("calibrate_modify", ""), False,
             lambda: self._countdown("bouton Modifier", lambda: self._calib_point("modify_button"))),
            ("rows", "Lignes de « mes ventes » (1re puis 2e)", ("calibrate_rows", " ×2"), False,
             self._calib_rows_ui),
            ("sell_button", "Bouton « Mettre en vente » (si validation au clic)", ("calibrate_button", ""), False,
             lambda: self._countdown("bouton Mettre en vente", lambda: self._calib_point("sell_button"))),
            ("name", "Nom de l'objet (reconnaître tes ventes, déduit sinon)", ("calibrate_name", " ×2"), False,
             lambda: self._calib_rect_ui("name", "nom de l'objet")),
            ("mine", "Ton prix (secours) : le champ « Prix du lot »", ("calibrate_mine", " ×2"), False,
             lambda: self._calib_rect_ui("mine", "ton prix")),
        ]
        for key, label, hot, required, cmd in items:
            r = self._row(b)
            st = ctk.CTkLabel(r, text="", width=26)
            st.pack(side="left")
            ctk.CTkLabel(r, text=label, anchor="w", width=300).pack(side="left")
            self._hk_label(r, *hot, text_color=MUTED, width=120, anchor="w",
                           font=ctk.CTkFont(family="Consolas")).pack(side="left")
            if not required:
                ctk.CTkButton(r, text="✕", width=28, height=26, fg_color=BTN2, hover_color=BTN2_HOVER,
                              command=lambda k=key: self._clear_zone(k)).pack(side="right", padx=(0, 4))
            ctk.CTkButton(r, text="Calibrer", width=80, height=26, command=cmd).pack(side="right", padx=4)
            self.calib_labels[key] = (st, required)

    def _tab_options(self, page):
        page.pack(fill="both", expand=True)
        b = self._section(page, "Général")
        self._switch(b, "Raccourcis actifs seulement quand Dofus a le focus", "require_focus",
                     tip="Évite de déclencher une vente en tapant ailleurs. Désactive seulement si l'outil "
                         "ne reconnaît pas la fenêtre du jeu (message [Focus] dans le journal).")
        self._switch(b, "Sons", "sound", tip="Un bip différent pour un succès, un avertissement, une erreur.")
        self._switch(b, "Afficher le résultat de chaque action", "toast",
                     tip="Petit message à l'écran : lot et prix choisis, ou la raison d'un arrêt.")
        self._switch(b, "… dans un bandeau fixe au-dessus de l'HDV", "banner",
                     tip="Toujours au même endroit. Désactivé : une popup près de la souris.")
        self._switch(b, "Notification Windows à la fin d'un long parcours", "notify",
                     tip="Tout vendre ou toute la liste de plus de 20 s : une notification Windows "
                         "quand c'est fini, si tu es dans une autre fenêtre que le jeu et l'outil.")
        self._switch(b, "Fenêtre de l'outil toujours au-dessus du jeu", "always_on_top",
                     tip="Même chose que 📌 en haut. Le jeu doit être en fenêtré ou plein écran fenêtré.")
        b = self._section(page, "Apparence")
        r = self._row(b)
        self._tip(ctk.CTkLabel(r, text="Style", width=120, anchor="w"),
                  "Verre : le jeu derrière l'outil apparaît flouté, comme une vitre teintée. Reste flouté "
                  "pendant que tu joues. Windows 10 (1803+) ou 11.").pack(side="left")
        seg = ctk.CTkSegmentedButton(r, values=["Classique", "Verre"], command=self._set_ui_style)
        self.style_seg = seg
        seg.set("Verre" if self._glass_on() else "Classique")
        seg.pack(side="left")
        if not style.glass_supported():
            seg.configure(state="disabled")
            ctk.CTkLabel(r, text="(verre : Windows 10 1803+ requis)", text_color=MUTED).pack(side="left", padx=8)
        r = self._row(b)
        self._tip(ctk.CTkLabel(r, text="Teinte du verre", width=120, anchor="w"),
                  "Plus la teinte est forte, plus le texte est lisible ; plus elle est faible, plus on voit "
                  "le jeu.").pack(side="left")
        self.glass_slider = ctk.CTkSlider(r, from_=0.3, to=0.95, number_of_steps=13, width=200,
                                          command=self._set_glass_opacity)
        self.glass_slider.set(min(0.95, max(0.3, self.cfg.glass_opacity)))
        self.glass_slider.pack(side="left")
        self.glass_lbl = ctk.CTkLabel(r, text=f"{self.cfg.glass_opacity:.0%}", text_color=MUTED)
        self.glass_lbl.pack(side="left", padx=8)
        self._update_glass_controls()
        r = self._row(b)
        self._tip(ctk.CTkLabel(r, text="Taille du texte", width=120, anchor="w"),
                  "Agrandit ou réduit tout le texte et les boutons de l'outil.").pack(side="left")
        ctk.CTkSegmentedButton(r, values=list(UI_SCALES), variable=self.scale_var,
                               command=self._set_ui_scale).pack(side="left")
        ctk.CTkLabel(b, text="La taille et la position de la fenêtre sont gardées d'un lancement à l'autre.",
                     text_color=MUTED, font=ctk.CTkFont(size=11)).pack(anchor="w", pady=(4, 0))
        b = self._section(page, "Sécurité et rapidité")
        self._switch(b, "Relire « Prix du lot » avant de valider", "verify_before_enter",
                     tip="Le prix collé est relu dans le champ avant Entrée : jamais un mauvais prix validé.")
        self._switch(b, "Touche de vente intelligente", "smart_f1",
                     tip="Vend un objet de l'inventaire OU met à jour une de tes ventes, selon ce qui est "
                         "sélectionné dans l'HDV.")
        b = self._section(page, "Lecture rapide des chiffres",
                          tip="Apprise toute seule à partir de Tesseract. À réapprendre si tu changes de "
                              "résolution ou de taille d'interface du jeu.")
        self._switch(b, "Utiliser la lecture rapide", "fast_digits",
                     tip="Beaucoup plus rapide que Tesseract, qui reste utilisé en secours.")
        ctk.CTkButton(b, text="Réapprendre les chiffres", width=180, fg_color=BTN2, hover_color=BTN2_HOVER,
                      command=self._reset_digits).pack(anchor="w", pady=4)
        b = self._section(page, "Mises à jour et journal", f"Version {core.app_version()}.",
                          tip="Le journal (fichier) garde l'historique des messages et des erreurs : à "
                              "joindre quand tu signales un problème.")
        self._switch(b, "Vérifier au démarrage si une nouvelle version est publiée (GitHub)", "check_updates")
        r = self._row(b)
        ctk.CTkButton(r, text="Ouvrir le dossier du journal", width=200, fg_color=BTN2, hover_color=BTN2_HOVER,
                      command=self._open_log_dir).pack(side="left")
        ctk.CTkButton(r, text="Page des versions", width=150, fg_color=BTN2, hover_color=BTN2_HOVER,
                      command=lambda: self._open_url(core.RELEASES_URL)).pack(side="left", padx=8)
        r = self._row(b)
        self._tip(ctk.CTkButton(r, text="📦 Rapport de problème", width=200,
                                command=lambda: self._countdown("rapport", self._make_report)),
                  "Crée un zip à envoyer quand quelque chose ne marche pas : journal, réglages, captures "
                  "de diagnostic et une image de l'HDV (affiche-le pendant le compte à rebours). Rien "
                  "n'est envoyé tout seul ; ton historique de ventes n'est pas inclus.").pack(side="left")
        ctk.CTkButton(r, text="Signaler sur GitHub", width=150, fg_color=BTN2, hover_color=BTN2_HOVER,
                      command=lambda: self._open_url(dofus_update.ISSUES_URL)).pack(side="left", padx=8)

    def _set_ui_scale(self, label: str):
        s = UI_SCALES.get(label, 1.0)
        if s == self.cfg.ui_scale:
            return
        self.cfg.ui_scale = s
        ctk.set_widget_scaling(s)
        size = self._log_font_size()
        self.log_text.configure(font=("Consolas", size))
        self.log_text.tag_configure("HDR", font=("Consolas", size, "bold"))
        try:
            self.cfg.save()
        except OSError as e:
            self._log(f"[Param] Sauvegarde impossible : {e}", "ERROR")

    CLEAR_FIELDS = {"anchor": ("anchor_region",), "avg": ("avg_region",), "count": ("count_region",),
                    "modify_button": ("modify_button",), "rows": ("relist_row",), "sell_button": ("sell_button",),
                    "mine": ("mine_region",), "name": ("name_region",)}

    def _clear_zone(self, key: str):
        """Efface une zone / un point optionnel (✕ dans l'onglet Calibration)."""
        for f in self.CLEAR_FIELDS.get(key, ()):
            setattr(self.cfg, f, None)
        if key == "rows":
            self.cfg.relist_step = 0
        self.cfg.save()
        self._log(f"[Calib] Zone « {key} » effacée.", "CAL")
        self._refresh_status()

    # ---- profils de calibration
    def _busy(self) -> bool:
        if self.engine._lock.locked():
            self._log("[Profil] Une action est en cours : réessaie quand elle est finie.", "WARN")
            return True
        return False

    def _after_profile_change(self, msg: str):
        try:
            self.cfg.save()
        except OSError as e:
            self._log(f"[Profil] Sauvegarde impossible : {e}", "ERROR")
        self.profile_menu.configure(values=self.cfg.profile_names())
        self.profile_var.set(self.cfg.profile)
        self.hdv_state = None          # autre HDV : pas encore vu
        self._log(msg, "CAL")
        self._refresh_status()

    def _switch_profile(self, name: str):
        if name == self.cfg.profile:
            return
        if self._busy():
            self.profile_var.set(self.cfg.profile)
            return
        self.cfg.switch_profile(name)
        self._after_profile_change(f"[Profil] « {name} » actif.")

    def _new_profile(self):
        if self._busy():
            return
        name = ctk.CTkInputDialog(title="Nouveau profil",
                                  text=f"Nom du nouveau profil (copie de « {self.cfg.profile} ») :").get_input()
        if name is None:
            return
        try:
            self.cfg.new_profile(name)
        except ValueError as e:
            self._log(f"[Profil] {e}.", "ERROR")
            return
        self._after_profile_change(f"[Profil] « {self.cfg.profile} » créé (copie) et actif : recalibre "
                                   "ce qui change dans cet HDV.")

    def _delete_profile(self):
        names = self.cfg.profile_names()
        if len(names) <= 1:
            self._log("[Profil] C'est le seul profil : rien à supprimer.", "WARN")
            return
        if self._busy():
            return
        name = self.cfg.profile
        if not self._confirm("Supprimer le profil", f"Supprimer le profil « {name} » et sa calibration ?",
                             ok="Supprimer", danger=True):
            return
        other = next(n for n in names if n != name)
        self.cfg.switch_profile(other)
        self.cfg.delete_profile(name)
        self._after_profile_change(f"[Profil] « {name} » supprimé ; « {other} » actif.")

    def _wizard_checks(self) -> list:
        """Lecture complète une fois (thread de travail) -> lignes ✓ / ✗ pour l'assistant."""
        c = self.cfg
        out = []
        try:
            moved = self.engine._reanchor()
            if c.anchor_region:
                out.append("✓ Repère HDV trouvé" + (f" (zones recalées {moved})" if moved else "")
                           if "introuvable" not in self.engine.last_anchor_msg else "✗ Repère HDV introuvable")
            sr = self.engine.read_only()
            n = len(sr.prices)
            out.append(f"{'✓' if n else '✗'} Tableau : {n} prix lus "
                       + ", ".join(f"lot {l} = {fmt(r.value)}" for l, r in sorted(sr.prices.items())))
            out.append(f"{'✓' if sr.selected else '✗'} Quantité : {sr.selected or 'illisible'}")
            if c.avg_region:
                out.append(f"{'✓' if sr.avg else '✗'} Prix moyen : {fmt(sr.avg) if sr.avg else 'illisible'}")
            for zone in core.CUT_CHECK_ZONES:
                if core.cut_text_hint(zone, getattr(c, f"{zone}_region")):
                    out.append(f"⚠ Zone {ZONE_LABELS[zone]} : le texte touche son bord (chiffre coupé ?). "
                               "Recalibre-la avec 3-4 px de marge en haut et en bas.")
            if core.mine_regions(c):
                out.append(f"{'✓' if sr.mine else '–'} Champ « Prix du lot » : "
                           f"{fmt(sr.mine) if sr.mine else 'vide ou illisible'}")
            if c.count_region:
                out.append(f"{'✓' if sr.listed else '✗'} Compteur : "
                           f"{'%d/%d' % sr.listed if sr.listed else 'illisible'}")
            if c.modify_button:
                mode = core.detect_panel(c)
                out.append("✓ Panneau : " + {"relist": "une de tes ventes (F1 = mise à jour)",
                                              "sell": "objet de l'inventaire (F1 = vente)"}.get(mode, "vide"))
            if core.name_region_for(c):
                known = core.item_key(core.grab_name(c)) is not None
                out.append(f"{'✓' if known else '–'} Objet reconnu (pour ne pas passer sous tes propres "
                           f"ventes) : {'oui' if known else 'non, rien de lisible dans la zone du nom'}")
            out.append(f"• Chiffres appris : {len(core.digit_reader().known())}/10 "
                       "(se complète tout seul en vendant)")
        except Exception as e:
            out.append(f"✗ Erreur : {e}")
        return out

    def _reset_digits(self):
        core.digit_reader().reset()
        self._log("[Chiffres] Modèles effacés : réapprentissage pendant les prochaines lectures.", "WARN")
        self._refresh_status()

    def _apply_topmost(self):
        """Toujours au-dessus du jeu (le jeu doit être en fenêtré ou plein écran fenêtré)."""
        on = bool(self.v["always_on_top"].get())
        try:
            self.attributes("-topmost", on)
            if on:
                self.lift()
        except tk.TclError:
            pass

    # ---- journal : filtres, blocs Ctrl+F3 repliables, copie
    MAX_LOG = 1500

    def _log_font_size(self) -> int:
        return max(8, round(10 * (self.cfg.ui_scale or 1.0)))

    def _clear_log(self):
        self.log_entries.clear()
        self.log_blocks = {k: b for k, b in self.log_blocks.items() if k == self._block}
        if self._block is not None:       # parcours en cours : son en-tête reste
            self.log_entries.append({"t": time.strftime("%H:%M:%S"), "msg": "", "tag": "INFO",
                                     "cat": "sale", "block": self._block, "header": True})
        self._render_log()

    def _copy_log(self):
        self.clipboard_clear()
        self.clipboard_append(self.log_text.get("1.0", "end-1c"))
        self.copy_btn.configure(text="Copié ✓")
        self.after(1500, lambda: self.copy_btn.configure(text="Copier"))

    def _setup_log_tags(self):
        for tag, color in TAG_COLORS.items():
            self.log_text.tag_configure(tag, foreground=color)
        self.log_text.tag_configure("HDR", foreground=P["cyan"], font=(style.MONO, self._log_font_size(), "bold"))

    def _log(self, msg: str, tag: str = "INFO"):
        core.log_line(msg, tag)
        e = {"t": time.strftime("%H:%M:%S"), "msg": msg, "tag": tag, "cat": log_category(msg, tag),
             "block": self._block, "header": False}
        self.log_entries.append(e)
        if self._block is not None and e["cat"] == "problem":
            self.log_blocks[self._block]["problems"] += 1
        if len(self.log_entries) > self.MAX_LOG:
            del self.log_entries[:300]
            self._render_log()
        elif self._entry_visible(e):
            self._insert_entries([e])

    def _entry_visible(self, e: dict) -> bool:
        flt = LOG_FILTERS.get(self.log_filter.get(), "all")
        b = self.log_blocks.get(e["block"]) if e["block"] is not None else None
        if e["header"]:
            return flt != "problem" or bool(b and b["problems"])
        if b is not None and b["collapsed"]:
            return False
        return log_visible(e["cat"], flt, in_block=b is not None)

    def _insert_entries(self, entries: list):
        t = self.log_text
        t.configure(state="normal")
        for e in entries:
            if e["header"]:
                b = self.log_blocks.get(e["block"])
                if b is None:
                    continue
                htag = f"hdr{e['block']}"
                t.insert("end", ("▶ " if b["collapsed"] else "▼ ") + b["title"] + "\n", ("HDR", htag))
                t.tag_bind(htag, "<Button-1>", lambda _e, k=e["block"]: self._toggle_block(k))
                t.tag_bind(htag, "<Enter>", lambda _e: t.configure(cursor="hand2"))
                t.tag_bind(htag, "<Leave>", lambda _e: t.configure(cursor=""))
                continue
            t.insert("end", e["t"] + "  ", ("TIME",))
            t.insert("end", ("   " if e["block"] is not None else "") + e["msg"] + "\n", (e["tag"],))
        t.see("end")
        t.configure(state="disabled")

    def _render_log(self):
        t = self.log_text
        t.configure(state="normal")
        t.delete("1.0", "end")
        t.configure(state="disabled")
        self._insert_entries([e for e in self.log_entries if self._entry_visible(e)])

    def _toggle_block(self, key: int):
        b = self.log_blocks.get(key)
        if b:
            b["collapsed"] = not b["collapsed"]
            y = self.log_text.yview()[0]
            self._render_log()
            self.log_text.yview_moveto(y)

    def _block_start(self):
        """Début d'un Ctrl+F3 : ses lignes vont dans un bloc repliable du journal."""
        self._block_seq += 1
        self._block = self._block_seq
        self.log_blocks[self._block] = {"title": f"Ctrl+F3 · {time.strftime('%H:%M:%S')} · en cours…",
                                        "collapsed": False, "problems": 0}
        e = {"t": "", "msg": "", "tag": "INFO", "cat": "sale", "block": self._block, "header": True}
        self.log_entries.append(e)
        self._insert_entries([e])

    def _block_end(self, res: Optional[core.Result]):
        key, self._block = self._block, None
        b = self.log_blocks.get(key)
        if b is None:
            return
        title = b["title"].replace(" · en cours…", "")
        if res is not None and res.changes:
            mod = sum(1 for c in res.changes if c.modified)
            bad = len(res.changes) - mod
            title += f" · {mod} prix modifié{'s' if mod > 1 else ''}" + (f" · {bad} à revoir" if bad else "")
        elif res is not None:
            title += f" · {res.hint or res.level}"
        else:
            title += " · interrompu (erreur)"
        b["title"] = title + "   (clic = déplier / replier)"
        b["collapsed"] = True
        self._render_log()

    # ------------------------------------------------------------ settings
    def _schedule_save(self):
        if self._save_after:
            self.after_cancel(self._save_after)
        self._save_after = self.after(500, self._apply_settings)

    def _apply_settings(self):
        self._save_after = None
        c, v = self.cfg, self.v
        try:
            c.undercut_value = float(v["undercut_value"].get().replace(",", "."))
            c.min_price = int(v["min_price"].get())
            c.floor_ratio = max(0.0, float(v["floor_ratio"].get().replace(",", ".") or 0) / 100)
        except ValueError:
            self._log("[Param] Valeur numérique invalide, non sauvegardé.", "ERROR")
            return
        try:
            c.relist_max = max(10, int(v["relist_max"].get()))
            c.relist_rows = max(2, int(v["relist_rows"].get()))
        except ValueError:
            self._log("[Param] Nombre de lignes invalide, non sauvegardé.", "ERROR")
            return
        c.relist_scroll_page = round(float(v["relist_scroll_page"].get()), 2)
        c.undercut_mode = {lbl: k for k, lbl in UNDERCUT_LABELS.items()}.get(v["undercut_mode"].get(), "fixed")
        c.rounding = {lbl: k for k, lbl in ROUNDING_LABELS.items()}.get(v["rounding"].get(), "none")
        c.floor_mode = {lbl: k for k, lbl in FLOOR_LABELS.items()}.get(v["floor_mode"].get(), "floor")
        was_auto = c.relist_auto
        for name in ("auto_paste", "click_field", "auto_validate", "require_focus", "sound", "toast",
                     "relist_auto", "relist_confirm_enter", "relist_summary", "fast_digits", "auto_recalibrate",
                     "banner", "verify_before_enter", "smart_f1", "always_on_top", "check_updates", "notify"):
            setattr(c, name, bool(v[name].get()))
        self._apply_topmost()
        self._refresh_home()
        if c.relist_auto and not was_auto:
            self._log(f"[Param] {c.hotkeys['relist_all']} actif : l'outil parcourt toute la liste seul "
                      "(clics + molette). C'est le mode le plus risqué vis-à-vis des CGU d'Ankama. "
                      f"{c.hotkeys['pause']} pour l'arrêter.", "WARN")
        if c.click_field and not c.price_field:
            self._log("[Param] « Cliquer Prix du lot » : calibre d'abord le champ "
                      f"({c.hotkeys['calibrate_field']} ou bouton).", "WARN")
        if c.auto_validate:
            self._log("[Param] Mise en vente auto active : la vente part sans vérification visuelle "
                      "(sauf lecture suspecte). "
                      + ("Validation : Entrée." if c.validate_method != "click"
                         else "Validation : clic sur le bouton."), "WARN")
        try:
            c.save()
        except OSError as e:
            self._log(f"[Param] Sauvegarde impossible: {e}", "ERROR")

    def _sync_vars_from_cfg(self):
        # la calibration du champ active « Cliquer Prix du lot »
        if self.v["click_field"].get() != self.cfg.click_field:
            self.v["click_field"].set(self.cfg.click_field)

    # ------------------------------------------------------------- hotkeys
    def _register_hotkeys(self):
        if not KEYBOARD_AVAILABLE:
            self._log("[Hotkeys] Module 'keyboard' indisponible (sous Windows : lancer en admin si besoin).",
                      "ERROR")
            return
        hk = self.cfg.hotkeys
        last_warn = [0.0]
        try:
            core.HOTKEYS.clear()   # ré-enregistrement après un changement
        except Exception:
            pass

        def game_job(job):
            def cb():
                if self.engine.paused:
                    if time.time() - last_warn[0] > 5:   # sinon on croit les raccourcis cassés
                        last_warn[0] = time.time()
                        self.ui_events.put(("log", (f"[Hotkeys] Raccourci ignoré : l'outil est en pause "
                                                    f"({hk['pause'].upper()} pour reprendre).", "WARN")))
                    return
                if not core.game_has_focus(self.cfg):
                    if time.time() - last_warn[0] > 5:  # diagnostic, max 1 fois / 5 s
                        last_warn[0] = time.time()
                        info = core.foreground_info() or ("?", "?")
                        self.ui_events.put(("log", (
                            f"[Focus] Raccourci ignoré : fenêtre active « {info[0]} » ({info[1]}). "
                            "Ajuste WINDOW_PROCESS / WINDOW_TITLE dans la config si c'est bien le jeu.",
                            "WARN")))
                    return
                self.jobs.put(job + (time.time(),))   # heure d'appui : voir _worker
            return cb

        try:
            core.HOTKEYS.add(hk["sell"], game_job(("sell", False)))
            core.HOTKEYS.add(hk["optimize"], game_job(("sell", True)))
            core.HOTKEYS.add(hk["sell_all"], game_job(("sell_all", None)))
            core.HOTKEYS.add(hk["relist"], game_job(("relist", None)))
            core.HOTKEYS.add(hk["relist_all"], game_job(("relist_all", None)))
            core.HOTKEYS.add(hk["calibrate_mine"], lambda: self.jobs.put(("calib_rect", "mine")))
            core.HOTKEYS.add(hk["calibrate_modify"], lambda: self.jobs.put(("calib_point", "modify_button")))
            core.HOTKEYS.add(hk["calibrate_rows"], lambda: self.jobs.put(("calib_rows", None)))
            core.HOTKEYS.add(hk["calibrate_anchor"], lambda: self.jobs.put(("calib_rect", "anchor")))
            core.HOTKEYS.add(hk["calibrate_name"], lambda: self.jobs.put(("calib_rect", "name")))
            core.HOTKEYS.add(hk["calibrate_auto"], lambda: self.jobs.put(("calib_auto", None)))
            core.HOTKEYS.add(hk["calibrate_table"], lambda: self.jobs.put(("calib_rect", "table")))
            core.HOTKEYS.add(hk["calibrate_qty"], lambda: self.jobs.put(("calib_rect", "qty")))
            core.HOTKEYS.add(hk["calibrate_avg"], lambda: self.jobs.put(("calib_rect", "avg")))
            core.HOTKEYS.add(hk["calibrate_count"], lambda: self.jobs.put(("calib_rect", "count")))
            core.HOTKEYS.add(hk["calibrate_field"], lambda: self.jobs.put(("calib_point", "price_field")))
            core.HOTKEYS.add(hk["calibrate_button"], lambda: self.jobs.put(("calib_point", "sell_button")))
            core.HOTKEYS.add(hk["show_zones"], lambda: self.ui_events.put(("zones", None)))
            core.HOTKEYS.add(hk["pause"], lambda: self.ui_events.put(("pause", None)))
            core.HOTKEYS.add(hk["cheatsheet"], lambda: self.ui_events.put(("cheatsheet", None)))
        except Exception as e:
            self._log(f"[Hotkeys] Erreur d'enregistrement: {e}", "ERROR")
            return
        self._log("[Hotkeys] Prêt.", "INFO")

    # -------------------------------------------------------------- worker
    def _worker(self):
        """Toutes les actions lentes (OCR, saisie) passent ici, hors thread UI."""
        while True:
            name, arg, *pressed = self.jobs.get()
            if pressed:
                # Touche de jeu appuyée PENDANT une action longue (F2, Ctrl+F3) : elle attendait
                # dans la file. L'exécuter après coup (ou après une pause) agirait sur un écran
                # qui a changé depuis -> ignorée.
                waited = time.time() - pressed[0]
                if self.engine.paused or waited > STALE_JOB_S:
                    why = "pause active" if self.engine.paused else f"appuyé il y a {waited:.0f} s, pendant une autre action"
                    self.ui_events.put(("log", (f"[Hotkeys] Raccourci ignoré ({why}).", "WARN")))
                    continue
            try:
                if name == "sell":
                    res = self.engine.sell(optimize=True) if arg else self.engine.smart()
                    self.ui_events.put(("result", res))
                elif name == "sell_all":
                    self.ui_events.put(("loop_start", "sell_all"))
                    res = None
                    try:
                        res = self.engine.sell_all()
                        self.ui_events.put(("result", res))
                    finally:
                        self.ui_events.put(("loop_end", res))
                elif name == "relist":
                    self.ui_events.put(("result", self.engine.relist()))
                elif name == "relist_all":
                    self.ui_events.put(("block_start", None))
                    self.ui_events.put(("loop_start", "relist_all"))
                    self.ui_events.put(("log", ("[MAJ TOUT] Parcours de la liste… « Arrêter » ou "
                                                f"{self.cfg.hotkeys['pause'].upper()} pour arrêter.", "CAL")))
                    res = None
                    try:
                        res = self.engine.relist_all()
                        self.ui_events.put(("result", res))
                    finally:
                        self.ui_events.put(("block_end", res))
                        self.ui_events.put(("loop_end", res))
                elif name == "calib_rows":
                    self.ui_events.put(("calib_rows", self.engine.calibrate_rows()))
                elif name == "read":
                    self.ui_events.put(("screen", self.engine.read_only()))
                elif name == "wizard_test":
                    self.ui_events.put(("wizard_test", self._wizard_checks()))
                elif name == "calib_rect":
                    self.ui_events.put(("calib_rect", (arg, self.engine.calibrate_rect(arg))))
                elif name == "calib_point":
                    self.ui_events.put(("calib_point", (arg, self.engine.calibrate_point(arg))))
                elif name == "report":
                    try:
                        self.ui_events.put(("report", dofus_update.make_report(self.cfg)))
                    except Exception as e:
                        self.ui_events.put(("report", e))
                elif name == "calib_auto":
                    res = self.engine.calibrate_auto()
                    self.ui_events.put(("calib_auto", (res, self._wizard_checks() if res.ok else [])))
            except Exception as e:
                self.ui_events.put(("log", (f"[Erreur] {e}", "ERROR")))
            msg, self.engine.last_anchor_msg = self.engine.last_anchor_msg, ""
            if msg:
                self.ui_events.put(("anchor", msg))

    def _unstick_keys(self):
        """Toutes les secondes : touches que `keyboard` croit enfoncées à tort -> libérées
        (sinon plus aucun raccourci ne répond, jusqu'au redémarrage)."""
        if KEYBOARD_AVAILABLE and not self._capturing:
            try:
                freed = core.release_stuck_keys()
            except Exception:
                freed = []
            if freed:
                self._log(f"[Hotkeys] Touche restée « enfoncée » libérée : {', '.join(freed)} "
                          "(les raccourcis remarchent).", "WARN")
        self.after(1000, self._unstick_keys)

    def _poll_ui(self):
        try:
            while True:
                name, arg = self.ui_events.get_nowait()
                if name == "result":
                    self._on_result(arg)
                elif name == "block_start":
                    self._block_start()
                elif name == "block_end":
                    self._block_end(arg)
                elif name == "loop_start":
                    self._loop_start(arg)
                elif name == "loop_progress":
                    self._loop_progress(arg)
                elif name == "loop_end":
                    self._loop_end(arg)
                elif name == "cheatsheet":
                    self._toggle_cheatsheet()
                elif name == "anchor":
                    self._log(f"[Repère] {arg}", "CAL" if "recalées" in arg else "WARN")
                    if "introuvable" in arg:
                        self._set_hdv("lost")
                    elif "recalées" in arg:
                        self._set_hdv("ok")
                    self._refresh_status()
                elif name == "screen":
                    self._show_screen(arg)
                    txt = " | ".join(f"lot {l}: {fmt(r.value)} ({r.confidence:.0f}%)"
                                     for l, r in arg.prices.items())
                    extra = ""
                    if self.cfg.avg_region:
                        extra += f" | prix moyen: {fmt(arg.avg) if arg.avg else '?'}"
                    if core.mine_regions(self.cfg):
                        extra += f" | ton prix: {fmt(arg.mine) if arg.mine else '?'}"
                    if self.cfg.count_region:
                        extra += f" | lots en vente: {'%d/%d' % arg.listed if arg.listed else '?'}"
                    dr = core.digit_reader()
                    extra += (f" | lecture : {arg.engine or '?'} (chiffres appris "
                              f"{len(dr.known())}/10)")
                    self._log(f"[Test] quantité: {arg.selected or '?'} | {txt or 'rien lu'}{extra}", "INFO")
                elif name == "calib_rect":
                    self._on_calib_rect(*arg)
                elif name == "calib_point":
                    self._on_calib_point(*arg)
                elif name == "calib_rows":
                    self._on_calib_rows(arg)
                elif name == "calib_auto":
                    self._on_calib_auto(*arg)
                elif name == "log":
                    self._log(*arg)
                elif name == "zones":
                    self._show_zones()
                elif name == "pause":
                    self._toggle_pause()
                elif name == "refresh":
                    self._refresh_status()
                elif name == "wizard_test":
                    self._wiz_report_show(arg)
                elif name == "update":
                    self._on_update(arg)
                elif name == "update_progress":
                    self.update_btn.configure(text=arg)
                elif name == "update_ready":
                    self._on_update_ready(*arg)
                elif name == "report":
                    self._on_report(arg)
                elif name == "hotkey":
                    self._on_hotkey_captured(*arg)
        except queue.Empty:
            pass
        self.after(30, self._poll_ui)

    # ------------------------------------------------------------- results
    def _on_result(self, res: core.Result):
        self._show_screen(res.screen)
        self._count_stats(res)
        tag = {"warn": "WARN", "error": "ERROR"}.get(res.level) or (
            "OPT" if res.message.startswith("[OPT]") else "OK")
        self._log(res.message, tag)
        if res.message.startswith("[MAJ TOUT]"):
            self._relist_summary(res)
        core.beep(res.level, self.cfg)
        head = (f"Lot {res.lot} → {fmt(res.new_price)}" if res.new_price is not None
                else "Liste mise à jour" if res.message.startswith("[MAJ TOUT]") else "Pas de prix")
        self.last_action = (head, res.hint or res.level, LEVEL_COLORS[res.level])
        self._add_activity(res)
        if res.level == "ok" and res.message.startswith(("[VENTE]", "[OPT]", "[TOUT]", "[MAJ]")) \
                and ("mis en vente" in res.message or "modifié" in res.message or res.message.startswith("[TOUT]")):
            self._mark_step("sell")
        self._refresh_compact()
        if self.cfg.toast:
            if self.cfg.banner:
                self._banner(head, res.hint or res.level, LEVEL_COLORS[res.level])
            else:
                self._toast(head, res.hint or res.level, LEVEL_COLORS[res.level])

    # ---- résumé de fin de Ctrl+F3
    def _relist_summary(self, res: core.Result):
        """Journal : une ligne par prix modifié / ligne à revoir. Historique (onglet Mes ventes) et
        fenêtre : la même chose avec l'image du nom de chaque objet (le nom n'est pas lu en texte)."""
        for c in res.changes:
            self._log("   " + c.text(), "OK" if c.modified else "WARN")
        if not res.changes:
            return
        run = {"time": time.time(), "changes": list(res.changes)}
        self.runs = (self.runs + [run])[-MAX_RUNS:]
        try:
            save_runs(self.runs)
        except OSError as e:
            self._log(f"[Résumé] Historique non enregistré : {e}", "WARN")
        self._refresh_runs()
        if self.cfg.relist_summary:
            self._summary_window(run)

    def _summary_window(self, run: dict):
        changes = run["changes"]
        mod = [c for c in changes if c.modified]
        bad = [c for c in changes if not c.modified]
        w = getattr(self, "_summary_win", None)
        if w is not None and w.winfo_exists():
            w.destroy()
        w = ctk.CTkToplevel(self)
        self._summary_win = w
        w.title("Résumé de la mise à jour (Ctrl+F3) · "
                + time.strftime("%d/%m %H:%M", time.localtime(run["time"])))
        w.geometry("560x520")
        w.attributes("-topmost", True)
        ctk.CTkLabel(w, text=f"{len(mod)} prix modifié{'s' if len(mod) > 1 else ''}"
                             + (f"  ·  {len(bad)} ligne{'s' if len(bad) > 1 else ''} à revoir avec "
                                f"{self.cfg.hotkeys['relist'].upper()}" if bad else ""),
                     font=ctk.CTkFont(size=15, weight="bold")).pack(anchor="w", padx=14, pady=(12, 4))
        body = ctk.CTkScrollableFrame(w, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=8, pady=4)
        self._summary_imgs = []                     # garder les images (sinon effacées par Tk)
        for c in bad + mod:                          # à revoir en premier
            r = ctk.CTkFrame(body, fg_color=CARD)
            r.pack(fill="x", pady=2)
            img = self._name_thumb(c.img)
            if img is not None:
                self._summary_imgs.append(img)
                ctk.CTkLabel(r, text="", image=img).pack(side="left", padx=6, pady=4)
            lot = f"lot {c.lot}" if c.lot else "lot ?"
            if c.modified:
                txt = f"{lot}   {fmt(c.old)} → {fmt(c.new)}"
                if c.old and c.new:
                    txt += f"   ({(c.new - c.old) / c.old:+.1%})"
                color = P["green"]
            else:
                txt = f"{lot}   NON modifiée : {c.note}"
                color = P["orange"]
            ctk.CTkLabel(r, text=txt, text_color=color, anchor="w", justify="left",
                         wraplength=300).pack(side="left", padx=6)
            ctk.CTkLabel(r, text=f"ligne {c.row}", text_color=MUTED).pack(side="right", padx=8)
        ctk.CTkButton(w, text="Fermer", width=100, command=w.destroy).pack(pady=(4, 12))

    @staticmethod
    def _name_thumb(img):
        """Image du nom (BGR) -> vignette pour l'interface, ou None."""
        if img is None or getattr(img, "size", 0) == 0:
            return None
        try:
            from PIL import Image
            pil = Image.fromarray(img[:, :, ::-1].copy())
            h = 36
            w = max(1, int(pil.width * h / pil.height))
            return ctk.CTkImage(light_image=pil, dark_image=pil, size=(w, h))
        except Exception:
            return None

    def _count_stats(self, res: core.Result):
        m = res.message
        if "SUSPECT" in m:
            self.stats["suspects"] += 1
        if m.startswith("[TOUT]"):
            for seg in m.split("] ", 1)[1].split(" | ")[0].split(" + "):
                n = seg.split("×")[0]
                if n.isdigit():
                    self.stats["ventes"] += int(n)
        elif "mis en vente" in m:
            self.stats["ventes"] += 1
        if m.startswith("[MAJ TOUT]"):
            try:
                self.stats["modifs"] += int(m.split(" modifiées")[0].split(": ")[-1])
            except ValueError:
                pass
        elif m.startswith("[MAJ]") and "| modifié" in m:
            self.stats["modifs"] += 1
        self._refresh_status()

    def _show_screen(self, sr: core.ScreenRead):
        if not sr.prices and sr.selected is None:
            return
        if any(r and r.value is not None for r in sr.prices.values()):
            self._set_hdv("ok")
            self._mark_step("read")
            if not self.read_grid.winfo_ismapped():
                self.read_grid.pack(fill="x", padx=12, pady=6, before=self.read_empty)
                self.read_empty.pack_forget()
        self.qty_var.set(str(sr.selected) if sr.selected else "?")
        for lot, var in self.read_vars.items():
            r = sr.prices.get(lot)
            if r and r.value is not None:
                var.set(fmt(r.value))
                self.unit_vars[lot].set(f"{r.value / lot:,.1f}/u".replace(",", " ") if lot > 1 else "")
            else:
                var.set("—")
                self.unit_vars[lot].set("")
        self.avg_var.set(f"{fmt(sr.avg)} /u" if sr.avg else "—")
        mine = sr.mine if sr.mine is not None else (sr.mine_r.value if sr.mine_r else None)
        self.mine_var.set(fmt(mine) if mine else "—")
        self.engine_var.set({"chiffres": "lecture rapide", "tesseract": "Tesseract"}.get(sr.engine, "—"))
        info = [f"quantité {sr.selected}" if sr.selected else "quantité ?"]
        if sr.avg:
            info.append(f"moyen {fmt(sr.avg)}/u")
        if mine:
            info.append(f"ton prix {fmt(mine)}")
        self.read_info.configure(text=" · ".join(info))

    # ------------------------------------------------------------- overlays
    def _popup_content(self, card, head: str, sub: str, color: str) -> dict:
        """Contenu commun du popup et du bandeau : pastille de couleur, titre, détail."""
        row = ctk.CTkFrame(card, fg_color="transparent")
        row.pack(padx=(12, 16), pady=9)
        dot = ctk.CTkFrame(row, width=10, height=10, corner_radius=5, fg_color=color)
        dot.pack(side="left", padx=(0, 10))
        head_l = ctk.CTkLabel(row, text=head, text_color="#ffffff", font=ctk.CTkFont(size=15, weight="bold"))
        head_l.pack(side="left")
        sub_l = ctk.CTkLabel(row, text=sub, text_color=color, font=ctk.CTkFont(size=13))
        sub_l.pack(side="left", padx=(10, 0))
        return {"dot": dot, "head": head_l, "sub": sub_l}

    def _toast(self, head: str, sub: str, color: str, ms: int = 1800):
        """Popup près de la souris : carte arrondie aux couleurs de l'outil."""
        try:
            x, y = core.mouse_position()
        except Exception:
            x, y = self.winfo_pointerx(), self.winfo_pointery()
        t, card = rounded_popup(self, alpha=0.96)
        self._popup_content(card, head, sub, color)
        t.geometry(f"+{x + 18}+{y + 18}")
        t.after(ms, lambda: t.winfo_exists() and t.destroy())

    def _overlay(self, x, y, w, h, color, alpha, ms, label=""):
        t = tk.Toplevel(self)
        t.overrideredirect(True)
        t.attributes("-topmost", True)
        try:
            t.attributes("-alpha", alpha)
        except tk.TclError:
            pass
        t.configure(bg=color)
        if label:
            tk.Label(t, text=label, bg=color, fg="black", font=("Segoe UI", 8, "bold")).place(x=2, y=0)
        t.geometry(f"{w}x{h}+{x}+{y}")
        t.after(ms, t.destroy)

    def _show_zones(self, ms: int = 2500):
        c = self.cfg
        shown = False
        for name, label in ZONE_LABELS.items():
            r = getattr(c, f"{name}_region")
            if r:
                self._overlay(*r, ZONE_COLORS[name], 0.35, ms, label)
                shown = True
        for name in POINT_COLORS:
            p = getattr(c, name)
            if p:
                self._overlay(p[0] - 6, p[1] - 6, 12, 12, POINT_COLORS[name], 0.9, ms)
                shown = True
        if not shown:
            self._log("[Zones] Rien n'est calibré.", "WARN")

    # ---------------------------------------------------------- calibration
    # ------------------------------------------------------------------ bandeau
    def _banner(self, head: str, sub: str, color: str, ms: int = 6000):
        """Bandeau fixe au-dessus de l'HDV (toujours au même endroit), à la place de la popup."""
        c = self.cfg
        if not (c.anchor_region or c.price_field or c.table_region):
            return self._toast(head, sub, color)
        x, y = self._overlay_anchor()
        b = getattr(self, "_banner_win", None)
        if b is not None and b.winfo_exists():
            b.destroy()                  # recréé : la taille suit le texte
        b, card = rounded_popup(self, alpha=0.96)
        self._banner_win = b
        self._popup_content(card, head, sub, color)
        b.geometry(f"+{max(0, int(x))}+{max(0, int(y))}")
        if getattr(self, "_banner_after", None):
            self.after_cancel(self._banner_after)
        self._banner_after = self.after(ms, lambda: b.winfo_exists() and b.destroy())

    # ------------------------------------------------------------------ assistant
    # (clé, type, titre, optionnel, raccourci, préparation dans le jeu, comment faire)
    WIZ_STEPS = [
        ("anchor", "rect", "Repère : titre « Hôtel de vente »", True, "calibrate_anchor",
         "Ouvre l'HDV, onglet VENTE. Rien d'autre à préparer.",
         "1. Clique « Calibrer », puis pose la souris juste AU-DESSUS À GAUCHE du « H » de "
         "« Hôtel de vente » (dans la barre de titre rouge).\n"
         "2. Au 2e compte à rebours, pose-la juste EN DESSOUS À DROITE du « e » final.\n"
         "Reste dans la barre de titre, sans prendre l'icône ni le décor du jeu autour.\n"
         "À quoi ça sert : si tu déplaces la fenêtre de l'HDV, toutes les zones suivent toutes seules."),
        ("table", "rect", "Tableau « Actuellement en vente »", False, "calibrate_table",
         "Clique sur un objet de ton INVENTAIRE (à droite) : le tableau à gauche se remplit.",
         "1. Coin HAUT-GAUCHE : juste au-dessus et à gauche du « 1 » de la colonne « Lot » (ligne lot 1).\n"
         "2. Coin BAS-DROIT : juste en dessous et à droite du dernier prix (ligne lot 1000), en "
         "incluant l'icône kamas.\n"
         "Ne prends pas les titres « Lot / Prix ». Les icônes d'objet et de kamas peuvent être dedans : "
         "elles sont ignorées. Prends les 4 lignes même si un lot est vide."),
        ("qty", "rect", "Menu « Quantité »", False, "calibrate_qty",
         "Toujours un objet de l'inventaire sélectionné.",
         "1. Coin HAUT-GAUCHE : un peu au-dessus et à gauche du chiffre dans le menu « Quantité ».\n"
         "2. Coin BAS-DROIT : un peu en dessous du chiffre, AVANT la petite flèche.\n"
         "Garde 3-4 px de marge en haut et en bas : un chiffre coupé est mal lu."),
        ("price_field", "point", "Champ « Prix du lot »", False, "calibrate_field",
         "Objet de l'inventaire sélectionné.",
         "Clique « Calibrer », puis pose la souris AU MILIEU du champ noir « Prix du lot » "
         "(là où s'écrit le prix), et ne bouge plus jusqu'à la fin du compte à rebours.\n"
         "Ce point sert à cliquer dans le champ, à relire le prix avant chaque validation, à lire "
         "« ton prix » dans tes ventes et à trouver le nom de l'objet."),
        ("avg", "rect", "Prix moyen", True, "calibrate_avg",
         "Objet de l'inventaire (ou une de tes ventes) sélectionné.",
         "1. Coin HAUT-GAUCHE : un peu au-dessus et à gauche du nombre sous « PRIX MOYEN ».\n"
         "2. Coin BAS-DROIT : un peu en dessous et à droite de l'icône kamas qui suit le nombre.\n"
         "Laisse de la place à droite : le nombre peut avoir plus de chiffres sur un autre objet "
         "(ex. 51 puis 1 189). Sert au prix plancher."),
        ("count", "rect", "Compteur « x/100 lots en vente »", True, "calibrate_count",
         "Rien à préparer : la ligne est en bas de la liste de droite.",
         "1. Coin HAUT-GAUCHE : un peu au-dessus et à gauche du premier chiffre de « 21/100 lots en vente ».\n"
         "2. Coin BAS-DROIT : un peu en dessous et à droite du mot « vente ».\n"
         "Prends TOUTE la ligne avec 3-4 px de marge en haut et en bas. F2 s'en sert pour vérifier "
         "chaque vente."),
        ("modify_button", "point", "Bouton « Modifier »", True, "calibrate_modify",
         "Clique sur une de TES ventes dans la liste de droite : en bas à gauche apparaissent "
         "« RETIRER » et « MODIFIER ».",
         "Clique « Calibrer », puis pose la souris au MILIEU du bouton « MODIFIER ».\n"
         "Il sert à F3 / Ctrl+F3 (valider le nouveau prix) et à F1 pour savoir s'il doit vendre "
         "ou mettre à jour."),
        ("rows", "rows", "Lignes de la liste « mes ventes »", True, "calibrate_rows",
         "Remonte la liste de droite tout en haut (molette).",
         "1. Au 1er compte à rebours : souris au CENTRE de la 1re ligne entièrement visible, sur le "
         "nom de l'objet.\n"
         "2. Au 2e : souris au CENTRE de la ligne juste en dessous, à la même hauteur relative.\n"
         "L'outil en déduit la hauteur d'une ligne. Utile seulement pour Ctrl+F3 (toute la liste)."),
        ("sell_button", "point", "Bouton « Mettre en vente »", True, "calibrate_button",
         "Objet de l'inventaire sélectionné. Inutile si la validation se fait avec Entrée (par défaut).",
         "Clique « Calibrer », puis pose la souris au milieu du bouton « METTRE EN VENTE ». "
         "Utilisé seulement si VALIDATE_METHOD = « click » dans la config."),
        ("name", "rect", "Nom de l'objet", True, "calibrate_name",
         "Objet sélectionné. À faire SEULEMENT si la vérification finale dit « Objet reconnu : non » : "
         "sinon la zone est déduite du champ « Prix du lot ». Le nom sert à reconnaître tes propres "
         "ventes (ne pas passer dessous).",
         "1. Coin HAUT-GAUCHE : juste au-dessus et à gauche de la 1re lettre du nom (à droite de l'icône).\n"
         "2. Coin BAS-DROIT : sous la 2e ligne du nom (les noms longs tiennent sur 2 lignes), "
         "à droite du panneau, SANS la ligne « NIV. 26 »."),
        ("mine", "rect", "Ton prix (secours)", True, "calibrate_mine",
         "Inutile en temps normal : ton prix est lu autour du point « Prix du lot ». À faire seulement "
         "si F3 dit « Ton prix illisible ». Sélectionne une de TES ventes.",
         "1. Coin HAUT-GAUCHE : le coin haut-gauche du champ noir « Prix du lot » (le rectangle qui "
         "contient ton prix, ex. 76).\n"
         "2. Coin BAS-DROIT : le coin bas-droit de ce même champ, AVANT l'icône kamas.\n"
         "Ne prends PAS la liste de droite."),
    ]

    def _open_wizard(self):
        w = getattr(self, "_wiz", None)
        if w is not None and w.winfo_exists():
            w.lift()
            return
        w = ctk.CTkToplevel(self)
        w.title("Assistant de calibration")
        w.geometry("640x560")
        w.attributes("-topmost", True)
        self._wiz, self._wiz_i = w, 0
        self._wiz_title = ctk.CTkLabel(w, text="", font=ctk.CTkFont(size=16, weight="bold"), anchor="w")
        self._wiz_title.pack(fill="x", padx=16, pady=(14, 4))
        self._wiz_prep = ctk.CTkLabel(w, text="", wraplength=520, justify="left", anchor="w",
                                      text_color=P["cyan"])
        self._wiz_prep.pack(fill="x", padx=16)
        self._wiz_text = ctk.CTkLabel(w, text="", wraplength=520, justify="left", anchor="w")
        self._wiz_text.pack(fill="x", padx=16, pady=(8, 0))
        self._wiz_state = ctk.CTkLabel(w, text="", anchor="w", font=ctk.CTkFont(weight="bold"))
        self._wiz_state.pack(fill="x", padx=16, pady=(10, 0))
        self._wiz_msg = ctk.CTkLabel(w, text="", anchor="w", text_color=P["gold"], wraplength=520,
                                     justify="left")
        self._wiz_msg.pack(fill="x", padx=16, pady=(4, 0))
        self._wiz_report = ctk.CTkTextbox(w, height=150, font=("Consolas", 11))
        bar = ctk.CTkFrame(w, fg_color="transparent")
        bar.pack(side="bottom", fill="x", padx=16, pady=12)
        self._wiz_back = ctk.CTkButton(bar, text="← Retour", width=90, fg_color=BTN2, hover_color=BTN2_HOVER, command=lambda: self._wiz_go(-1))
        self._wiz_back.pack(side="left")
        self._wiz_next = ctk.CTkButton(bar, text="Suivant →", width=110, command=lambda: self._wiz_go(1))
        self._wiz_next.pack(side="right")
        self._wiz_do = ctk.CTkButton(bar, text="Calibrer", width=130, command=self._wiz_calibrate)
        self._wiz_do.pack(side="right", padx=8)
        ctk.CTkButton(bar, text="Voir zones", width=90, fg_color=BTN2, hover_color=BTN2_HOVER, command=self._show_zones
                      ).pack(side="left", padx=8)
        self._wiz_show()
        self._wiz_tick()

    def _wiz_values(self):
        c = self.cfg
        return {"anchor": c.anchor_region, "table": c.table_region, "qty": c.qty_region,
                "price_field": c.price_field, "avg": c.avg_region, "count": c.count_region,
                "modify_button": c.modify_button, "rows": c.relist_row, "sell_button": c.sell_button,
                "name": c.name_region, "mine": c.mine_region}

    def _wiz_show(self):
        n = len(self.WIZ_STEPS)
        self._wiz_msg.configure(text="")
        if self._wiz_i >= n:
            self._wiz_prep.configure(text="")
            self._wiz_title.configure(text=f"Vérification ({n + 1}/{n + 1})")
            self._wiz_text.configure(text="Sélectionne un objet de ton inventaire (ou une de tes ventes) "
                                          "dans l'HDV, puis clique « Tester ». L'outil lit tout une fois et "
                                          "dit ce qui va et ce qui ne va pas.")
            self._wiz_state.configure(text="")
            self._wiz_do.configure(text="Tester", command=self._wiz_test)
            self._wiz_next.configure(text="Terminer", command=self._wiz.destroy)
            self._wiz_report.pack(fill="both", expand=True, padx=16, pady=(8, 0))
            return
        self._wiz_report.pack_forget()
        key, kind, title, optional, hot, prep, text = self.WIZ_STEPS[self._wiz_i]
        self._wiz_title.configure(text=f"Étape {self._wiz_i + 1}/{n + 1} : {title}"
                                       + ("  (optionnel)" if optional else ""))
        self._wiz_prep.configure(text="Dans le jeu : " + prep)
        how = ("Zone = 2 positions de souris (coin haut-gauche, puis coin bas-droit)."
               if kind == "rect" else "Point = 1 position de souris." if kind == "point"
               else "2 positions de souris (1re ligne, puis 2e).")
        self._wiz_text.configure(
            text=text + f"\n\n{how} Après « Calibrer », un compte à rebours de "
                        f"{self.cfg.calib_countdown} s te laisse placer la souris dans le jeu "
                        f"(sans cliquer). Raccourci équivalent en jeu : "
                        f"{self.cfg.hotkeys[hot].upper()}. Vérifie ensuite avec « Voir zones ».")
        self._wiz_do.configure(text="Calibrer", command=self._wiz_calibrate)
        self._wiz_next.configure(text="Suivant →" if not optional else "Suivant / passer →",
                                 command=lambda: self._wiz_go(1))
        self._wiz_back.configure(state="normal" if self._wiz_i > 0 else "disabled")
        self._wiz_tick(once=True)

    def _wiz_tick(self, once: bool = False):
        w = getattr(self, "_wiz", None)
        if w is None or not w.winfo_exists():
            return
        if self._wiz_i < len(self.WIZ_STEPS):
            key = self.WIZ_STEPS[self._wiz_i][0]
            ok = bool(self._wiz_values().get(key))
            self._wiz_state.configure(text="✓ Calibré" if ok else "✗ Pas encore calibré",
                                      text_color=P["green"] if ok else P["red"])
            msg = self.status_var.get()
            if msg.startswith("Calibration"):
                self._wiz_msg.configure(text=msg)
        if not once:
            self.after(400, self._wiz_tick)

    def _wiz_go(self, d: int):
        self._wiz_i = max(0, min(len(self.WIZ_STEPS), self._wiz_i + d))
        self._wiz_show()

    def _wiz_calibrate(self):
        key, kind, title = self.WIZ_STEPS[self._wiz_i][:3]
        if kind == "rect":
            self._calib_rect_ui(key, title)
        elif kind == "point":
            self._countdown(title, lambda: self._calib_point(key))
        else:
            self._calib_rows_ui()

    def _wiz_test(self):
        self._wiz_report.delete("1.0", "end")
        self._wiz_report.insert("end", "Lecture en cours…")
        self.jobs.put(("wizard_test", None))

    def _wiz_report_show(self, rep: list):
        w = getattr(self, "_wiz", None)
        if w is None or not w.winfo_exists():
            return
        self._wiz_report.delete("1.0", "end")
        self._wiz_report.insert("end", "\n".join(rep))

    def _countdown(self, label: str, action, n: Optional[int] = None):
        n = self.cfg.calib_countdown if n is None else n
        if n <= 0:
            self._refresh_status()
            action()
            return
        if label == "rapport":
            self.status_var.set(f"Rapport dans {n}s… affiche l'HDV (il sera photographié) !")
        else:
            todo = "affiche l'HDV !" if label == "automatique" else "place la souris !"
            self.status_var.set(f"Calibration {label} dans {n}s… {todo}")
        self.after(1000, lambda: self._countdown(label, action, n - 1))

    def _calib_rect_ui(self, name: str, label: str):
        def second():
            self._on_calib_rect(name, self.engine.calibrate_rect(name))

        def first():
            self._on_calib_rect(name, self.engine.calibrate_rect(name))
            self._countdown(f"{label} : coin BAS-DROIT", second)

        self._countdown(f"{label} : coin HAUT-GAUCHE", first)

    def _on_calib_rect(self, name: str, res):
        state, val = res
        label = ZONE_LABELS[name]
        if state == "first":
            self._log(f"[Calib] {label} : coin 1 = {val}. Place la souris sur le coin opposé "
                      "et appuie à nouveau.", "CAL")
        else:
            self._log(f"[Calib] {label} = {val}", "CAL")
            hint = core.zone_hint(name, val) or core.cut_text_hint(name, val)
            if hint:
                self._log(f"[Calib] {label} : {hint}. Recalibre si la lecture échoue.", "WARN")
            self._show_zones()
        self._refresh_status()

    def _calib_rows_ui(self):
        def second():
            self._on_calib_rows(self.engine.calibrate_rows())

        def first():
            self._on_calib_rows(self.engine.calibrate_rows())
            self._countdown("2e ligne de tes ventes", second)

        self._countdown("1re ligne de tes ventes", first)

    def _on_calib_rows(self, res):
        state, val = res
        if state == "first":
            self._log(f"[Calib] Lignes : 1re ligne = {val}. Souris sur la 2e ligne et ré-appuie.", "CAL")
        elif state == "error":
            self._log(f"[Calib] Lignes : {val}", "ERROR")
        else:
            self._log(f"[Calib] Lignes : 1re ligne {val[0]}, hauteur {val[1]} px "
                      f"({self.cfg.relist_rows} lignes visibles, RELIST_ROWS)", "CAL")
        self._refresh_status()

    def _calib_auto_ui(self):
        if self._busy():
            return
        self._log("[Calib auto] Recherche de l'HDV à l'écran…", "CAL")
        self.jobs.put(("calib_auto", None))

    def _on_calib_auto(self, res, checks: list):
        self._log(f"[Calib auto] {res.message}", "CAL" if res.ok else "ERROR")
        self._set_hdv("ok" if res.ok else "lost")
        if not res.ok:
            if not self._calibrated():
                self._log("[Calib auto] Essaie l'assistant pas à pas : onglet Calibration › Avancé.", "WARN")
            self._refresh_status()
            return
        for line in checks:
            self._log("   " + line, "OK" if line.startswith("✓") else
                      "WARN" if line[:1] in "⚠–•" else "ERROR")
        self._log("[Calib auto] Vérifie avec « Voir zones » ; une zone mal placée se recalibre "
                  "individuellement (onglet Calibration › Avancé).", "CAL")
        self._sync_vars_from_cfg()
        self._refresh_status()
        self._show_zones(4000)

    def _calib_point(self, name: str):
        self._on_calib_point(name, self.engine.calibrate_point(name))

    def _on_calib_point(self, name: str, p):
        label = POINT_LABELS[name]
        self._log(f"[Calib] {label} = {p}", "CAL")
        self._sync_vars_from_cfg()
        self._refresh_status()

    # ---------------------------------------------------------------- misc
    def _toggle_pause(self):
        self.engine.paused = not self.engine.paused
        self._log("[Hotkeys] " + ("En pause." if self.engine.paused else "Actifs."), "WARN")
        self._refresh_status()

    CHIP_GREEN, CHIP_ORANGE, CHIP_RED, CHIP_GREY = "green", "orange", "red", "grey"   # dofus_style.CHIP

    def _set_hdv(self, state: Optional[str]):
        if state != self.hdv_state:
            self.hdv_state = state
            self._refresh_status()

    def _chip_values(self) -> dict:
        """Texte et couleur de chaque pastille de la barre d'état."""
        c = self.cfg
        paused = self.engine.paused
        calib = self._calibrated()
        if self.hdv_state == "ok":
            hdv = ("HDV vu ✓", self.CHIP_GREEN)
        elif self.hdv_state == "lost":
            hdv = ("HDV introuvable", self.CHIP_RED)
        else:
            hdv = ("HDV : pas encore lu", self.CHIP_GREY)
        if hdv[0] != "HDV introuvable" and not c.anchor_region:
            hdv = (hdv[0] + " · sans repère", hdv[1])
        return {
            "state": ("⏸ Pause" if paused else "● Actif", self.CHIP_ORANGE if paused else self.CHIP_GREEN),
            "profile": (f"Profil : {c.profile}", self.CHIP_GREY),
            "calib": ("Calibration OK" if calib else "Calibration à faire",
                      self.CHIP_GREEN if calib else self.CHIP_RED),
            "hdv": hdv,
        }

    def _refresh_status(self):
        c = self.cfg
        paused = self.engine.paused
        for key, (text, color) in self._chip_values().items():
            bg, fg = style.CHIP[color]
            self.chips[key].configure(text=text, fg_color=bg, text_color=fg)
        self._refresh_compact()
        self.pause_btn.configure(text="▶ Reprendre" if paused else "⏸ Pause")
        try:
            n = len(core.digit_reader().known())
            self.digits_var.set(f"Chiffres appris {n}/10" + ("  ✓" if n == 10 else ""))
        except Exception:
            self.digits_var.set("")
        st = core.ENGINE_STATS
        tot = st.get("chiffres", 0) + st.get("tesseract", 0)
        fast = f"  |  lecture rapide {st.get('chiffres', 0) * 100 // tot}%" if tot else ""
        self.stats_var.set(f"{self.digits_var.get()}{fast}")
        values = {"table": c.table_region, "qty": c.qty_region, "price_field": c.price_field,
                  "avg": c.avg_region, "count": c.count_region, "modify_button": c.modify_button,
                  "rows": c.relist_row, "sell_button": c.sell_button, "mine": c.mine_region,
                  "anchor": c.anchor_region, "name": c.name_region}
        names = {"table": "tableau", "qty": "quantité", "price_field": "Prix du lot"}
        missing = []
        for key, (lbl, required) in getattr(self, "calib_labels", {}).items():
            ok = bool(values.get(key))
            lbl.configure(text="✓" if ok else ("✗" if required else "–"),
                          text_color=P["green"] if ok else (P["red"] if required else MUTED))
            if required and not ok:
                missing.append(names[key])
        self.status_var.set(("À calibrer : " + ", ".join(missing) + " (onglet Calibration)")
                            if missing else "")
        self._refresh_home()

    # ---- style : classique ou verre
    def _glass_on(self) -> bool:
        return self.cfg.ui_style == "glass" and style.glass_supported()

    def _apply_style(self):
        """Classique (fond opaque) ou verre (le jeu flouté derrière l'outil), en direct."""
        glass = self._glass_on()
        ok = style.set_glass(self, glass, self.cfg.glass_opacity)
        if glass and not ok:
            self._log("[Style] Effet verre refusé par Windows : style classique.", "WARN")
        bg = style.GLASS_BG if glass and ok else P["bg"]
        if self.cget("fg_color") != bg:
            self.configure(fg_color=bg)
            self._refresh_transparent(self)
        w = self._compact
        if w is not None and w.winfo_exists():
            w.configure(fg_color=style.GLASS_BG if glass and ok else P["bg"])
            style.set_glass(w, glass and ok, self.cfg.glass_opacity)
        self._update_glass_controls()

    def _refresh_transparent(self, widget):
        """Après un changement du fond de la fenêtre : les zones « transparentes » de
        CustomTkinter gardent la couleur de leur création -> les recalculer, de haut en bas."""
        for c in widget.winfo_children():
            try:
                if isinstance(c, ctk.CTkScrollableFrame):
                    c._parent_frame.configure(bg_color="transparent")
                    if c._parent_frame.cget("fg_color") == "transparent":
                        c.configure(fg_color="transparent")
                elif isinstance(c, ctk.CTkBaseClass):
                    c.configure(bg_color="transparent")
                    if c.cget("fg_color") == "transparent":
                        c.configure(fg_color="transparent")
            except (tk.TclError, ValueError, AttributeError):
                pass
            self._refresh_transparent(c)

    def _set_ui_style(self, label: str):
        self.cfg.ui_style = "glass" if label == "Verre" else "classic"
        self._apply_style()
        self._save_cfg()

    def _set_glass_opacity(self, value: float):
        self.cfg.glass_opacity = round(float(value), 2)
        self.glass_lbl.configure(text=f"{self.cfg.glass_opacity:.0%}")
        if self._glass_on():
            style.set_glass(self, True, self.cfg.glass_opacity)
            w = self._compact
            if w is not None and w.winfo_exists():
                style.set_glass(w, True, self.cfg.glass_opacity)
        if getattr(self, "_glass_save", None):
            self.after_cancel(self._glass_save)
        self._glass_save = self.after(500, self._save_cfg)

    def _update_glass_controls(self):
        seg = getattr(self, "style_seg", None)
        if seg is not None:
            seg.set("Verre" if self._glass_on() and self.cget("fg_color") == style.GLASS_BG else "Classique")
        sl = getattr(self, "glass_slider", None)
        if sl is not None:
            sl.configure(state="normal" if self._glass_on() else "disabled")

    def _save_cfg(self):
        try:
            self.cfg.save()
        except OSError as e:
            self._log(f"[Param] Sauvegarde impossible : {e}", "ERROR")

    # ---- boucles (F2 / Ctrl+F3) : progression, Arrêter, notification
    LOOP_NAMES = {"relist_all": "Toute la liste", "sell_all": "Tout vendre"}

    def _loop_start(self, kind: str):
        self._loop = {"kind": kind, "t0": time.time(), "frac": None,
                      "text": "Démarrage…" if kind == "relist_all" else "en cours…"}
        self.loop_stop.configure(text="■ Arrêter", state="normal")
        self._loop_show()

    def _loop_progress(self, d: dict):
        if self._loop is None or d.get("finished"):
            return
        text, frac = progress_text(d)
        self._loop.update(text=text, frac=frac)
        self._loop_show()

    def _loop_show(self):
        lp = self._loop
        if lp is None:
            return
        self.loop_lbl.configure(text=f"{self.LOOP_NAMES.get(lp['kind'], '')} · {lp['text']}")
        if lp["frac"] is None:
            if self.loop_pb.cget("mode") != "indeterminate":
                self.loop_pb.configure(mode="indeterminate")
                self.loop_pb.start()
        else:
            if self.loop_pb.cget("mode") != "determinate":
                self.loop_pb.stop()
                self.loop_pb.configure(mode="determinate")
            self.loop_pb.set(lp["frac"])
        if not self.loop_bar.winfo_ismapped():
            self.loop_bar.pack(side="right", padx=(8, 0))
        self._refresh_compact()

    def _stop_loop(self):
        if self._loop is not None:
            self.engine.stop_requested = True
            self.loop_stop.configure(text="Arrêt…", state="disabled")
            self._log("[Boucle] Arrêt demandé : fin après la ligne en cours.", "WARN")
            self._refresh_compact()

    def _loop_end(self, res: Optional[core.Result]):
        lp, self._loop = self._loop, None
        self.loop_pb.stop()
        self.loop_bar.pack_forget()
        self._refresh_compact()
        if lp is None or not self.cfg.notify or time.time() - lp["t0"] < LONG_LOOP_S:
            return
        try:
            game = core.game_has_focus(self.cfg)
            mine = self.focus_displayof() is not None
        except Exception:
            game, mine = True, True
        if game or mine:
            return                       # le résultat est déjà visible (bandeau / fenêtre)
        name = self.LOOP_NAMES.get(lp["kind"], "Parcours")
        if res is None:
            body = "Interrompu par une erreur : voir le journal."
        elif res.changes:
            mod = sum(1 for c in res.changes if c.modified)
            bad = len(res.changes) - mod
            body = f"{mod} prix modifié{'s' if mod > 1 else ''}" + (f" · {bad} à revoir" if bad else "")
        else:
            body = res.hint or "Terminé."
        windows_notify(f"Dofus Price Helper · {name} terminé", body)

    # ---- aide-mémoire des touches, par-dessus le jeu
    CHEAT_KEYS = ("sell", "sell_all", "optimize", "relist", "relist_all", "pause", "cheatsheet")
    CHEAT_TEXT = {"sell": "Vendre / mettre à jour", "sell_all": "Tout vendre", "optimize": "Meilleur lot",
                  "relist": "Remettre sous le moins cher", "relist_all": "Toute la liste",
                  "pause": "Pause / reprise", "cheatsheet": "Fermer cet aide-mémoire"}

    def _toggle_cheatsheet(self, ms: int = 10000):
        w = self._cheat
        if w is not None and w.winfo_exists():
            w.destroy()
            self._cheat = None
            return
        t, card = rounded_popup(self)
        ctk.CTkLabel(card, text="◆  Raccourcis", text_color=P["gold"], anchor="w",
                     font=ctk.CTkFont(size=14, weight="bold")).pack(fill="x", padx=14, pady=(10, 4))
        g = ctk.CTkFrame(card, fg_color="transparent")
        g.pack(padx=12, pady=(0, 10))
        for i, name in enumerate(self.CHEAT_KEYS):
            ctk.CTkLabel(g, text=self.cfg.hotkeys[name].upper(), fg_color=P["card2"], corner_radius=6,
                         width=96, font=ctk.CTkFont(family=style.MONO, size=12, weight="bold")
                         ).grid(row=i, column=0, sticky="w", pady=2)
            txt = self.CHEAT_TEXT[name]
            if name == "relist_all" and not self.cfg.relist_auto:
                txt += "  (désactivé)"
            ctk.CTkLabel(g, text=txt, anchor="w", font=ctk.CTkFont(size=13),
                         text_color=MUTED if txt.endswith("(désactivé)") else P["text"]
                         ).grid(row=i, column=1, sticky="w", padx=(10, 4))
        x, y = self._overlay_anchor()
        t.geometry(f"+{max(0, int(x))}+{max(0, int(y))}")
        self._cheat = t
        t.after(ms, lambda: t.winfo_exists() and t.destroy())

    def _overlay_anchor(self):
        """Où afficher bandeau et aide-mémoire : au-dessus de l'HDV si on sait où il est."""
        c = self.cfg
        if c.anchor_region:
            return c.anchor_region[0] - 40, c.anchor_region[1] - 50
        if c.price_field:
            return c.price_field[0] - 80, c.price_field[1] - 200
        if c.table_region:
            return c.table_region[0], c.table_region[1] - 60
        try:
            x, y = core.mouse_position()
        except Exception:
            x, y = self.winfo_pointerx(), self.winfo_pointery()
        return x + 18, y + 18

    # ---- confirmation au style de l'outil (au lieu de la boîte Windows)
    def _confirm(self, title: str, text: str, ok: str = "Oui", danger: bool = False) -> bool:
        d = ctk.CTkToplevel(self)
        d.title(title)
        d.resizable(False, False)
        d.attributes("-topmost", True)
        d.transient(self)
        res = {"ok": False}
        ctk.CTkLabel(d, text=title, anchor="w", font=ctk.CTkFont(size=16, weight="bold")
                     ).pack(fill="x", padx=18, pady=(16, 6))
        ctk.CTkLabel(d, text=text, anchor="w", justify="left", wraplength=400).pack(fill="x", padx=18)
        bar = ctk.CTkFrame(d, fg_color="transparent")
        bar.pack(fill="x", padx=18, pady=(18, 16))

        def done(v):
            res["ok"] = v
            d.destroy()
        kw = dict(fg_color=style.CHIP["red"][0], hover_color="#5a2730", text_color=P["red"]) if danger else {}
        ctk.CTkButton(bar, text=ok, width=110, command=lambda: done(True), **kw).pack(side="right")
        ctk.CTkButton(bar, text="Annuler", width=100, fg_color=BTN2, hover_color=BTN2_HOVER,
                      command=lambda: done(False)).pack(side="right", padx=8)
        d.protocol("WM_DELETE_WINDOW", lambda: done(False))
        d.bind("<Escape>", lambda _e: done(False))
        d.update_idletasks()
        x = self.winfo_rootx() + (self.winfo_width() - d.winfo_reqwidth()) // 2
        y = self.winfo_rooty() + (self.winfo_height() - d.winfo_reqheight()) // 3
        d.geometry(f"+{max(0, x)}+{max(0, y)}")
        d.after(250, lambda: d.winfo_exists() and (d.grab_set(), d.focus_force()))
        self.wait_window(d)
        return res["ok"]

    # ---- mode compact : petite fenêtre au premier plan pendant le jeu
    def _open_compact(self):
        w = self._compact
        if w is not None and w.winfo_exists():
            w.lift()
            return
        w = ctk.CTkToplevel(self)
        self._compact = w
        w.title("Dofus Price Helper")
        w.attributes("-topmost", True)
        w.resizable(False, False)
        g = self.cfg.compact_geometry
        try:
            ok = bool(g) and geometry_on_screen(g, core.screen_bounds())
        except Exception:
            ok = False
        pos = g[g.index("+"):] if ok and "+" in g else ""   # position gardée, taille fixe
        w.geometry("340x170" + pos)
        if self._glass_on():
            w.configure(fg_color=style.GLASS_BG)
        top = ctk.CTkFrame(w, fg_color="transparent")
        top.pack(fill="x", padx=10, pady=(10, 4))
        self._cmp_chips = {}
        for key in ("state", "calib", "hdv"):
            lbl = ctk.CTkLabel(top, text="", corner_radius=11, height=22, fg_color=BTN2,
                               font=ctk.CTkFont(size=11, weight="bold"))
            lbl.pack(side="left", padx=2, ipadx=6)
            self._cmp_chips[key] = lbl
        self._cmp_head = ctk.CTkLabel(w, text="", anchor="w", font=ctk.CTkFont(size=15, weight="bold"))
        self._cmp_head.pack(fill="x", padx=12)
        self._cmp_sub = ctk.CTkLabel(w, text="", anchor="w", wraplength=300, justify="left")
        self._cmp_sub.pack(fill="x", padx=12)
        self._cmp_pb = ctk.CTkProgressBar(w, height=6, progress_color=P["accent"])   # pendant une boucle
        bar = ctk.CTkFrame(w, fg_color="transparent")
        bar.pack(fill="x", padx=10, pady=(6, 10), side="bottom")
        self._cmp_pause = ctk.CTkButton(bar, text="", width=120, command=self._toggle_pause)
        self._cmp_pause.pack(side="left")
        ctk.CTkButton(bar, text="Agrandir ⤢", width=100, fg_color=BTN2, hover_color=BTN2_HOVER, command=self._close_compact
                      ).pack(side="right")
        w.protocol("WM_DELETE_WINDOW", self._close_compact)
        self.withdraw()
        self._refresh_compact()
        if self._glass_on():
            w.after(300, lambda: w.winfo_exists() and style.set_glass(w, True, self.cfg.glass_opacity))

    def _compact_geometry(self) -> str:
        w = self._compact
        try:
            return w.geometry() if w is not None and w.winfo_exists() else ""
        except tk.TclError:
            return ""

    def _close_compact(self):
        w = self._compact
        if w is not None and w.winfo_exists():
            self.cfg.compact_geometry = self._compact_geometry()
            w.destroy()
        self._compact = None
        self.deiconify()
        self._apply_topmost()
        try:
            self.cfg.save()
        except OSError:
            pass

    def _refresh_compact(self):
        w = self._compact
        if w is None or not w.winfo_exists():
            return
        chips = self._chip_values()
        short = {"Calibration OK": "Calib. OK", "Calibration à faire": "Calib. à faire",
                 "HDV introuvable": "HDV ✗"}
        for key, lbl in self._cmp_chips.items():
            text, color = chips[key]
            if key == "hdv" and text not in short:
                text = "HDV ✓" if self.hdv_state == "ok" else "HDV ?"
            bg, fg = style.CHIP[color]
            lbl.configure(text=short.get(text, text), fg_color=bg, text_color=fg)
        lp = self._loop
        if lp is not None:                       # boucle en cours : progression + Arrêter
            self._cmp_head.configure(text=self.LOOP_NAMES.get(lp["kind"], "En cours") + "…")
            self._cmp_sub.configure(text=lp["text"], text_color=P["text"])
            if lp["frac"] is None:
                if self._cmp_pb.cget("mode") != "indeterminate":
                    self._cmp_pb.configure(mode="indeterminate")
                    self._cmp_pb.start()
            else:
                if self._cmp_pb.cget("mode") != "determinate":
                    self._cmp_pb.stop()
                    self._cmp_pb.configure(mode="determinate")
                self._cmp_pb.set(lp["frac"])
            if not self._cmp_pb.winfo_ismapped():
                self._cmp_pb.pack(fill="x", padx=12, pady=(4, 0))
            stopping = self.engine.stop_requested
            self._cmp_pause.configure(text="Arrêt…" if stopping else "■ Arrêter", command=self._stop_loop,
                                      fg_color=style.CHIP["red"][0], hover_color="#5a2730",
                                      text_color=P["red"])
            return
        self._cmp_pb.stop()
        self._cmp_pb.pack_forget()
        head, sub, color = self.last_action
        self._cmp_head.configure(text=head)
        self._cmp_sub.configure(text=sub, text_color=color)
        self._cmp_pause.configure(text="▶ Reprendre" if self.engine.paused else "⏸ Pause",
                                  command=self._toggle_pause, fg_color=P["accent"],
                                  hover_color=P["accent_hover"], text_color="#ffffff")

    # ---- mises à jour / journal
    def _on_update(self, up):
        if not up:
            return
        self._update = up
        if up.installable:
            self._log(f"[Version] {up.tag} est disponible (tu as {core.app_version()}) : clique sur "
                      f"« ⬆ Installer {up.tag} » en haut (téléchargement, puis redémarrage).", "OK")
            self.update_btn.configure(text=f"⬆ Installer {up.tag}", command=self._install_update)
        else:
            self._log(f"[Version] {up.tag} est disponible (tu as {core.app_version()}) : {up.page_url}", "OK")
            self.update_btn.configure(text=f"⬆ {up.tag} disponible", command=lambda: self._open_url(up.page_url))
        self.update_btn.pack(side="right", padx=4)

    def _install_update(self):
        up = self._update
        if getattr(self, "_installing", False):
            return
        if self.engine._lock.locked():
            self._log("[Version] Une action est en cours : installe la mise à jour quand elle est finie.", "WARN")
            return
        if not self._confirm(
                "Mise à jour", f"Installer {up.tag} maintenant ?\n\nL'outil télécharge la nouvelle version "
                f"({up.size / 1e6:.0f} Mo), se ferme, puis redémarre tout seul (moins d'une minute).\n"
                "Tes réglages, ta calibration et tes profils sont gardés.", ok="Installer"):
            return
        self._installing = True
        self._log(f"[Version] Téléchargement de {up.tag}…", "INFO")

        def progress(done, total):
            pct = f" {done * 100 // total} %" if total else ""
            self.ui_events.put(("update_progress", f"⬇ Téléchargement{pct}"))

        def work():
            try:
                self.ui_events.put(("update_ready", (dofus_update.prepare(up, progress), None)))
            except Exception as e:
                self.ui_events.put(("update_ready", (None, e)))

        threading.Thread(target=work, daemon=True).start()

    def _on_update_ready(self, new_dir, err):
        up = self._update
        if err is not None:
            self._installing = False
            self._log(f"[Version] Mise à jour impossible : {err}. Télécharge-la à la main sur la page "
                      "des versions (elle s'ouvre).", "ERROR")
            self.update_btn.configure(text=f"⬆ {up.tag} disponible", command=lambda: self._open_url(up.page_url))
            self._open_url(up.page_url)
            return
        try:
            dofus_update.launch_installer(new_dir, dofus_update.work_dir(new_dir))
        except Exception as e:
            self._installing = False
            self._log(f"[Version] Installation impossible : {e}", "ERROR")
            return
        self._log(f"[Version] {up.tag} prête : l'outil se ferme et redémarre tout seul.", "OK")
        self.after(300, self._on_close)

    # ---- rapport de problème
    def _make_report(self):
        self._log("[Rapport] Préparation…", "INFO")
        self.jobs.put(("report", None))

    def _on_report(self, res):
        if isinstance(res, Exception):
            self._log(f"[Rapport] Impossible de créer le rapport : {res}", "ERROR")
            return
        self._log(f"[Rapport] Créé : {res}. Envoie ce fichier (Discord, GitHub…) avec quelques mots "
                  "sur le problème. Il contient le journal, les réglages, les captures de diagnostic et "
                  "une image de l'HDV ; pas ton historique de ventes.", "OK")
        dofus_update.reveal(res)

    def _open_url(self, url: str):
        import webbrowser
        webbrowser.open(url)

    def _open_log_dir(self):
        import os
        core.LOG_DIR.mkdir(parents=True, exist_ok=True)
        try:
            os.startfile(core.LOG_DIR)
        except (AttributeError, OSError) as e:
            self._log(f"[Journal] Dossier : {core.LOG_DIR} ({e})", "WARN")

    def report_callback_exception(self, exc, val, tb):
        """Erreur dans l'interface : au journal (fichier) au lieu d'être perdue."""
        import traceback
        core.log_line("Erreur interface :\n" + "".join(traceback.format_exception(exc, val, tb)), "ERROR")
        self._log(f"[Erreur] {val}", "ERROR")

    def _on_close(self):
        if self._compact is not None and self._compact.winfo_exists():
            self.cfg.compact_geometry = self._compact_geometry()
        try:
            self.cfg.window_geometry = "zoomed" if self.state() == "zoomed" else self.geometry()
        except tk.TclError:
            pass
        self._apply_settings()
        try:
            self.cfg.save()       # taille de la fenêtre, même si un réglage était invalide
        except OSError:
            pass
        if KEYBOARD_AVAILABLE:
            try:
                keyboard.unhook_all()
            except Exception:
                pass
        self.destroy()


if __name__ == "__main__":
    if not dofus_update.single_instance():   # déjà ouvert : sa fenêtre est ramenée devant
        raise SystemExit(0)
    try:
        core.setup_file_log()
    except OSError:
        pass   # dossier non accessible : l'outil marche sans fichier journal
    App().mainloop()
