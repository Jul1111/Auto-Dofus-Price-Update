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
  Ctrl+Alt+P          arrêter le parcours en cours (Tout vendre, Toute la liste)
"""
from __future__ import annotations

import os
import queue
import sys
import threading
import time
import tkinter as tk
from typing import Optional

import dofus_core as core  # active la gestion DPI avant Tk
import dofus_update  # noqa: E402

import customtkinter as ctk

import dofus_backup
import dofus_logo
import dofus_style as style
from dofus_style import P

style.configure(*style.saved_look(core.CONFIG_PATH))   # thème et accent : avant les couleurs ci-dessous

try:
    import keyboard
    KEYBOARD_AVAILABLE = True
except Exception:  # pas installé / pas les droits
    KEYBOARD_AVAILABLE = False

try:
    import pystray
    TRAY_AVAILABLE = True
except Exception:  # pas installé : pas d'icône dans la zone de notification
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


LOG_ICONS = {"sale": "◆", "update": "✎", "warn": "▲", "error": "✖", "cal": "◎", "ok": "✓", "info": "·"}


def log_kind(msg: str, tag: str) -> str:
    """Type d'une ligne du journal, pour son icône : vente, mise à jour, alerte, erreur…"""
    m = msg.lstrip()
    if tag == "ERROR":
        return "error"
    if tag == "WARN":
        return "warn"
    if m.startswith(("[MAJ TOUT]", "[MAJ]")):
        return "update"
    if m.startswith(("[VENTE]", "[TOUT]", "[OPT]")):
        return "sale"
    if tag == "CAL":
        return "cal"
    return "ok" if tag in ("OK", "OPT") else "info"


# ---------------------------------------------------------------- historique des Ctrl+F3
RUNS_PATH = core.BASE_DIR / "dofus_relist_runs.json"
MAX_RUNS = 10


def runs_to_json(runs: list) -> list:
    """Parcours -> JSON (sans les images des noms, gardées en mémoire seulement)."""
    return [{"time": r["time"], "summary": r.get("summary") or {}, "changes": [
        {"row": c.row, "lot": c.lot, "old": c.old, "new": c.new, "modified": c.modified, "note": c.note}
        for c in r["changes"]]} for r in runs]


def runs_from_json(data) -> list:
    runs = []
    for r in data if isinstance(data, list) else []:
        try:
            summary = r.get("summary")
            runs.append({"time": float(r["time"]), "summary": summary if isinstance(summary, dict) else {},
                         "changes": [core.RowChange(
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
ANIMATE = {"on": True}  # fondus et progression douce (option « Animations »)


def rounded_popup(master, radius: int = 12, alpha: float = 0.97, border: str = None):
    """Fenêtre flottante sans bord (HUD, aide-mémoire, bulle d'aide) : une carte arrondie avec une
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
        t.attributes("-alpha", 0.0 if ANIMATE["on"] else alpha)
    except tk.TclError:
        pass
    if ANIMATE["on"]:
        style.fade(t, 0.0, alpha, 130)      # apparition en fondu
    card = ctk.CTkFrame(t, fg_color=P["card"], corner_radius=radius, border_width=1,
                        border_color=border or P["border"])
    card.pack()
    return t, card


def make_draggable(window, on_drop=None) -> None:
    """Fenêtre sans bord déplaçable en la tirant (clic gauche maintenu n'importe où dessus,
    sauf les boutons). on_drop(x, y) : appelé à la fin d'un déplacement."""
    state = {}

    def press(e):
        state.update(x=e.x_root, y=e.y_root, wx=window.winfo_x(), wy=window.winfo_y(), moved=False)

    def drag(e):
        if "x" not in state:
            return
        dx, dy = e.x_root - state["x"], e.y_root - state["y"]
        if abs(dx) + abs(dy) > 2:
            state.update(moved=True, nx=state["wx"] + dx, ny=state["wy"] + dy)
            window.geometry(f"+{state['nx']}+{state['ny']}")

    def release(_e):
        if state.get("moved") and on_drop is not None:
            on_drop(state["nx"], state["ny"])
        state.clear()

    def bind_all(w):
        if isinstance(w, ctk.CTkButton):
            return
        for seq, fn in (("<ButtonPress-1>", press), ("<B1-Motion>", drag), ("<ButtonRelease-1>", release)):
            try:
                w.bind(seq, fn, add="+")
            except (NotImplementedError, ValueError, tk.TclError):
                pass
        for c in w.winfo_children():
            bind_all(c)
    bind_all(window)
    try:
        window.configure(cursor="fleur")
    except tk.TclError:
        pass


def close_popup(t) -> None:
    """Ferme une fenêtre flottante (en fondu si les animations sont actives)."""
    try:
        if not t.winfo_exists():
            return
        if not ANIMATE["on"]:
            t.destroy()
            return
        start = float(t.attributes("-alpha"))
    except tk.TclError:
        return
    style.fade(t, start, 0.0, 160, then=lambda: t.winfo_exists() and t.destroy())


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


# ---------------------------------------------------------------- raccourcis dans la fenêtre de l'outil
TAB_NAMES = ("Accueil", "Prix", "Mes ventes", "Calibration", "Raccourcis", "Options")


def tab_index_for_key(keycode: int, keysym: str) -> Optional[int]:
    """Ctrl+1 … Ctrl+6 -> onglet 0 … 5. Par le code de la touche : marche aussi en AZERTY,
    où la rangée du haut donne & é " ' ( - sans Maj."""
    if 49 <= keycode <= 54:          # rangée du haut (VK_1 … VK_6)
        return keycode - 49
    if 97 <= keycode <= 102:         # pavé numérique
        return keycode - 97
    if len(keysym) == 1 and keysym in "123456":
        return int(keysym) - 1
    return None


# ---------------------------------------------------------------- zone de notification (près de l'horloge)
TRAY_STATES = {"ok": ("#3ecf8e", "Actif"),
               "loop": ("#5ccfe6", "Parcours en cours"), "calib": ("#f0616d", "Calibration à faire")}


def tray_image(color: str, size: int = 64, ring: str = None):
    """Icône : la pièce du logo, pastille de couleur = état de l'outil, anneau = couleur du profil."""
    return dofus_logo.logo_with_dot(color, size, ring=ring)


_ICO_PATH = None


def logo_ico() -> Optional[str]:
    """Chemin d'un .ico du logo (créé une fois dans le dossier temporaire), ou None."""
    global _ICO_PATH
    if _ICO_PATH is None:
        import tempfile
        from pathlib import Path
        path = Path(tempfile.gettempdir()) / f"dofus_price_helper_{core.app_version()}.ico"
        try:
            if not path.exists():
                dofus_logo.write_ico(path)
            _ICO_PATH = str(path)
        except Exception:
            _ICO_PATH = ""
    return _ICO_PATH or None


def brand(window) -> None:
    """Met le logo comme icône de la fenêtre (barre de titre, barre des tâches)."""
    ico = logo_ico()
    if ico:
        try:
            window.iconbitmap(ico)     # avant le délai de CustomTkinter : il ne remet pas son icône
        except tk.TclError:
            pass


class Tray:
    """Icône dans la zone de notification : clic = ouvrir, clic droit = menu (pystray)."""

    def __init__(self, app):
        self.app, self.icon, self._last = app, None, None
        self.told = False      # bulle « l'outil continue ici » déjà montrée

    def start(self):
        # Pas pendant la fermeture : _on_close enregistre les réglages (-> _apply_tray), ce qui
        # recréait l'icône ; son fil (non « daemon ») gardait alors l'outil actif sans fenêtre.
        if self.icon is not None or not TRAY_AVAILABLE or self.app.closing:
            return
        put = self.app.ui_events.put
        item = pystray.MenuItem
        menu = pystray.Menu(
            item("Ouvrir l'outil", lambda: put(("tray", "open")), default=True),
            item("■ Arrêter le parcours", lambda: put(("tray", "stop")),
                 visible=lambda _i: self.app._loop is not None),
            item("Aide-mémoire en jeu", lambda: put(("tray", "cheatsheet"))),
            item("HUD discret", lambda: put(("tray", "hud")), checked=lambda _i: bool(self.app.cfg.hud)),
            pystray.Menu.SEPARATOR,
            item("Quitter", lambda: put(("tray", "quit"))),
            item("Forcer l'arrêt", self._kill))
        color, text = (self._last or (*TRAY_STATES["ok"], None))[:2]
        ring = self._last[2] if self._last else None
        try:
            self.icon = pystray.Icon("DofusPriceHelper", tray_image(color, ring=ring),
                                     f"Dofus Price Helper · {text}", menu)
            self.icon.run_detached()
        except Exception as e:
            self.icon = None
            self.app._log(f"[Zone de notification] Icône impossible : {e}", "WARN")

    def update(self, state: str, ring: str = None, profile: str = ""):
        color, text = TRAY_STATES.get(state, TRAY_STATES["ok"])
        if profile:
            text += f" · {profile}"
        if (color, text, ring) == self._last:
            return
        self._last = (color, text, ring)
        if self.icon is not None:
            try:
                self.icon.icon = tray_image(color, ring=ring)
                self.icon.title = f"Dofus Price Helper · {text}"
                self.icon.update_menu()          # « Arrêter le parcours » visible ou non
            except Exception:
                pass

    def notify(self, text: str):
        if self.icon is not None:
            try:
                self.icon.notify(text, "Dofus Price Helper")
            except Exception:
                pass

    def _kill(self, *_):
        """Arrêt immédiat, appelé directement par l'icône (marche même si la fenêtre est figée)."""
        core.log_line("Arrêt forcé depuis l'icône de la zone de notification.", "WARN")
        try:
            if self.icon is not None:
                self.icon.visible = False      # sinon une icône « fantôme » reste près de l'horloge
        except Exception:
            pass
        os._exit(1)

    def stop(self):
        icon, self.icon = self.icon, None
        if icon is not None:
            try:
                icon.stop()
            except Exception:
                pass


RELAUNCH_FLAG = "--relance"


def relaunch_command() -> list:
    """Commande qui relance l'outil (après un changement de thème)."""
    import sys
    args = [a for a in sys.argv[1:] if a != RELAUNCH_FLAG] + [RELAUNCH_FLAG]
    if getattr(sys, "frozen", False):          # version .exe
        return [sys.executable] + args
    return [sys.executable, sys.argv[0]] + args


# ---------------------------------------------------------------- « Quoi de neuf » après une mise à jour
# {version: [lignes]} ; {pause} / {hud} = touches actuelles. Les plus récentes en dernier.
WHATS_NEW = {
    "1.8.0": [
        "Le HUD, une ligne discrète par-dessus le jeu, remplace le popup de résultat, le bandeau et le "
        "mode compact. Après chaque action, il s'allume de la couleur du résultat.",
        "{hud} l'affiche ou le cache. « Déplacer » (onglet Options) le pose où tu veux.",
    ],
    "1.9.0": [
        "HUD réglable dans l'onglet Options : taille, opacité, et contenu (état, dernière action, ou les deux).",
        "Pendant Tout vendre ou Toute la liste, le HUD rappelle « {pause} = arrêter », et le menu de "
        "l'icône près de l'horloge propose « Arrêter le parcours ».",
        "Une couleur par profil, visible dans le HUD, sur la pastille Profil et sur l'icône près de "
        "l'horloge. Elle se choisit dans l'onglet Calibration.",
        "Dernière lecture : une pastille de couleur indique si chaque prix a été lu de façon sûre "
        "(détail au survol).",
        "Sauvegarder et restaurer réglages, profils et calibration en un seul fichier (onglet Options).",
    ],
    "1.10.0": [
        "Renommer un profil (onglet Calibration) : ses personnages associés, sa couleur et son repère suivent.",
        "{window} affiche ou cache la fenêtre de l'outil, même depuis le jeu.",
        "Quand la mise en vente automatique est coupée, le HUD rappelle « Entrée pour valider » une fois "
        "le prix saisi (ou « Ctrl+V puis Entrée » s'il est seulement copié).",
    ],
    "1.11.0": [
        "Plus de pause : {pause} arrête le parcours en cours (Tout vendre, Toute la liste), comme le bouton "
        "« Arrêter », et les touches restent actives. Le bouton Pause a disparu.",
        "HUD : option « 3 derniers prix sous la ligne » (onglet Options) pour vérifier les derniers lots "
        "d'un coup d'œil, aussi pendant un parcours.",
        "Fin de Toute la liste : le résumé commence par un récap (modifiés, à revoir, déjà au bon prix, "
        "durée, raison de l'arrêt). Un clic sur une ligne la retrouve dans le journal.",
        "Visite guidée en 5 bulles au premier lancement. Elle se relance avec « Visite guidée » "
        "(onglet Accueil).",
    ],
}


def whats_new(last_seen: str, current: str) -> list:
    """[(version, lignes)] à montrer : les versions après `last_seen`, jusqu'à `current` (3 au plus).
    last_seen vide = mise à jour depuis une version qui ne le notait pas : les dernières."""
    cur = core.parse_version(current)
    if cur is None:
        return []
    seen = core.parse_version(last_seen) or (0, 0, 0)
    out = [(v, lines) for v, lines in WHATS_NEW.items()
           if seen < (core.parse_version(v) or (0, 0, 0)) <= cur]
    out.sort(key=lambda x: core.parse_version(x[0]))
    return out[-3:]


# ---------------------------------------------------------------- dernière lecture : fiabilité
def reading_quality(reading, min_conf: float) -> tuple:
    """(niveau "good" | "doubt" | "bad" | None, texte) pour la pastille d'un prix lu."""
    if reading is None or reading.value is None:
        return None, "Pas lu"
    conf = reading.confidence
    if reading.raw == "estimé":
        return "doubt", "Estimé d'après les autres lots (pas lu directement)"
    if conf >= max(80.0, min_conf + 15):
        level = "good"
    elif conf >= min_conf:
        level = "doubt"
    else:
        level = "bad"
    words = {"good": "lecture sûre", "doubt": "lecture moyenne : vérifie le prix",
             "bad": "lecture douteuse : l'outil ne collera pas ce prix tout seul"}[level]
    raw = f" · lu « {reading.raw} »" if reading.raw and reading.raw != str(reading.value) else ""
    return level, f"Fiabilité {conf:.0f} % : {words}{raw}"


def validate_reminder(res, cfg) -> Optional[str]:
    """Rappel pour le HUD quand le prix est prêt mais pas mis en vente (validation automatique
    coupée) : « Entrée pour valider », ou « Ctrl+V puis Entrée » s'il est seulement copié."""
    msg = res.message.lstrip()
    if res.level != "ok" or not msg.startswith(("[VENTE]", "[OPT]")) or res.new_price is None:
        return None
    done = msg.rsplit(" | ", 1)[-1]
    if done.startswith("saisi") and "mis en vente" not in done:
        return "Prix saisi · Entrée pour valider"
    if done.startswith("copié"):
        return "Prix copié · Ctrl+V puis Entrée"
    return None


HUD_HISTORY_N = 3
HUD_MARKS = {"ok": "✓", "warn": "!", "error": "✕"}


def hud_history_line(res) -> Optional[tuple]:
    """Ligne « derniers prix » du HUD pour un résultat : (texte, niveau, heure), ou None quand
    aucun prix n'a été mis ou proposé (lecture seule, « rien à faire », fin de parcours)."""
    msg = res.message.lstrip()
    if res.lot is None or res.new_price is None or not msg.startswith(("[VENTE]", "[OPT]", "[MAJ]")):
        return None
    if "rien à faire" in msg:
        return None
    old = res.old_price
    price = f"{fmt(old)} → {fmt(res.new_price)}" if old and old != res.new_price else fmt(res.new_price)
    return (f"{HUD_MARKS.get(res.level, '·')} Lot {res.lot}  {price}", res.level, time.strftime("%H:%M"))


def duration_text(seconds) -> str:
    s = max(0, int(round(seconds or 0)))
    return f"{s} s" if s < 60 else f"{s // 60} min {s % 60:02d}"


# ---------------------------------------------------------------- visite guidée
# (onglet, widgets visés par ordre de préférence, titre, texte) ; {touche} = raccourci actuel
TOUR = (
    ("Accueil", ("steps_outer",), "Bienvenue ! D'abord, la calibration",
     "L'outil lit l'Hôtel de vente à l'écran. Ouvre l'HDV sur l'onglet « Vente », puis clique « Calibrer » : "
     "toutes les zones sont placées seules."),
    ("Accueil", ("keys_outer",), "Les touches, dans le jeu",
     "{sell} vend l'objet sélectionné juste sous le moins cher, {sell_all} remet tout en vente et {relist} "
     "met à jour une de tes ventes. {cheatsheet} affiche l'aide-mémoire par-dessus le jeu."),
    ("Accueil", ("pause_btn",), "Pause",
     "Ce bouton, ou {pause} depuis le jeu, met l'outil en pause. Pendant un parcours, il l'arrête."),
    ("Options", ("hud_switch",), "Le HUD, par-dessus le jeu",
     "Une ligne discrète montre le résultat de chaque action et la progression d'un parcours. {hud} "
     "l'affiche ou le cache, « Déplacer » le pose où tu veux."),
    ("Accueil", ("log_frame",), "Le journal",
     "Tout ce que fait l'outil, ligne par ligne. Un clic sur une ligne avec un prix le copie. "
     "Pour revoir cette visite : « Visite guidée », dans l'onglet Accueil."),
)


def tour_steps(hk: dict) -> list:
    keys = {k: str(v).upper() for k, v in hk.items()}
    return [{"tab": tab, "targets": targets, "title": title, "text": text.format(**keys)}
            for tab, targets, title, text in TOUR]


def tour_place(target, size, area, gap: int = 12) -> tuple:
    """Position (x, y) de la bulle de taille `size` près de `target` (x, y, l, h), dans `area`
    (x0, y0, x1, y1) : dessous, sinon dessus, à droite, à gauche ; au centre sans cible."""
    bw, bh = size
    x0, y0, x1, y1 = area

    def clamp(v, lo, hi):
        return max(lo, min(v, hi)) if hi >= lo else lo
    if target is None:
        return (x0 + (x1 - x0 - bw) // 2, y0 + (y1 - y0 - bh) // 2)
    tx, ty, tw, th = target
    cx = clamp(tx, x0 + gap, x1 - bw - gap)
    cy = clamp(ty, y0 + gap, y1 - bh - gap)
    if ty + th + gap + bh <= y1:
        return (cx, ty + th + gap)
    if ty - gap - bh >= y0:
        return (cx, ty - gap - bh)
    if tx + tw + gap + bw <= x1:
        return (tx + tw + gap, cy)
    if tx - gap - bw >= x0:
        return (tx - gap - bw, cy)
    return (cx, clamp(y1 - bh - gap, y0, y1))


HUD_SIZES = {"small": ("Petit", 11), "normal": ("Normal", 12), "large": ("Grand", 15)}
HUD_CONTENTS = {"state": "État", "action": "Action", "both": "Les deux"}


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
        brand(self)
        ctk.set_widget_scaling(self.cfg.ui_scale if 0.5 <= self.cfg.ui_scale <= 2 else 1.0)
        self.geometry("1120x800")
        self.minsize(980, 680)
        self._restore_geometry()

        self.engine = core.PriceEngine(self.cfg)
        self.engine.progress = lambda r: self.ui_events.put(("row", r))   # une ligne d'un parcours
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
        self._loop: Optional[dict] = None   # boucle en cours (F2 / Ctrl+F3) : type, début
        self.activity: list = []             # panneau Activité : dernières actions (récentes d'abord)
        self.hud_recent: list = []           # HUD : derniers prix traités (récents d'abord)
        self._cheat = None                   # aide-mémoire affiché par-dessus le jeu
        self._hud_note = None                # message temporaire du HUD : (titre, détail, couleur, fin)
        self._log_seq = 0
        self.tray = Tray(self)
        self._char: Optional[str] = None     # personnage du jeu au premier plan (titre de la fenêtre)
        self._profile_lock = threading.Lock()
        self._hud = None                     # HUD discret par-dessus le jeu
        self._tour: Optional[dict] = None    # visite guidée en cours : étape, bulle, cadre
        self._hud_moving = False
        self._game_fg = False
        self.restart_requested = False
        self.closing = False
        ANIMATE["on"] = bool(self.cfg.animations)

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
        if not self.cfg.tour_done:
            self.after(900, lambda: self._tour_start(first=True))   # 1er lancement : visite, puis calibration
        elif not self._calibrated():
            self.after(800, self._first_launch)   # 1er lancement : calibration automatique proposée
        else:
            self.after(2500, self._check_calibration)   # fenêtre du jeu / écran changés depuis ?
        if self.cfg.tray:
            self.tray.start()
        self.after(400, self._apply_hud)          # HUD activé : créé dès le lancement (caché hors du jeu)
        self.after(1800, self._whats_new)         # 1er lancement d'une nouvelle version
        self.after(1200, self._watch_game)
        self.bind("<Control-KeyPress>", self._on_ctrl_key)
        self.bind("<Escape>", self._on_escape)
        self.bind("<Unmap>", self._on_unmap)
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
        brand(w)
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
        ctk.CTkButton(bar, text="Assistant pas à pas", fg_color=BTN2, text_color=P["text"], hover_color=BTN2_HOVER, command=wizard).pack(side="left")
        ctk.CTkButton(bar, text="Plus tard", fg_color=BTN2, text_color=P["text"], hover_color=BTN2_HOVER, width=90, command=w.destroy).pack(side="right")

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
            "relist_auto": ctk.BooleanVar(value=c.relist_auto),
            "relist_confirm_enter": ctk.BooleanVar(value=c.relist_confirm_enter),
            "relist_summary": ctk.BooleanVar(value=c.relist_summary),
            "auto_recalibrate": ctk.BooleanVar(value=c.auto_recalibrate),
            "fast_digits": ctk.BooleanVar(value=c.fast_digits),
            "verify_before_enter": ctk.BooleanVar(value=c.verify_before_enter),
            "smart_f1": ctk.BooleanVar(value=c.smart_f1),
            "always_on_top": ctk.BooleanVar(value=c.always_on_top),
            "check_updates": ctk.BooleanVar(value=c.check_updates),
            "notify": ctk.BooleanVar(value=c.notify),
            "animations": ctk.BooleanVar(value=c.animations),
            "tray": ctk.BooleanVar(value=c.tray),
            "tray_minimize": ctk.BooleanVar(value=c.tray_minimize),
            "auto_profile": ctk.BooleanVar(value=c.auto_profile),
            "hud": ctk.BooleanVar(value=c.hud),
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
        self._logo_img = ctk.CTkImage(light_image=dofus_logo.logo_image(64), dark_image=dofus_logo.logo_image(64),
                                      size=(28, 28))
        ctk.CTkLabel(head, text="", image=self._logo_img).pack(side="left", padx=(14, 8), pady=8)
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
                ("state", "Raccourcis actifs. Pendant un parcours : clic = l'arrêter.", self._stop_loop),
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
                                       fg_color=style.CHIP["red"][0], hover_color=P["red_hover"],
                                       text_color=style.CHIP["red"][1], command=self._stop_loop)
        self.loop_stop.pack(side="left", padx=(8, 4), pady=3)
        # calibration décalée (fenêtre du jeu redimensionnée, écran changé) : affiché au besoin
        ob, of = style.CHIP["orange"]
        self.drift_bar = ctk.CTkFrame(wrap, fg_color=ob, corner_radius=10)
        self.drift_lbl = ctk.CTkLabel(self.drift_bar, text="", text_color=of, anchor="w", justify="left",
                                      wraplength=620, font=ctk.CTkFont(size=12, weight="bold"))
        self.drift_lbl.pack(side="left", fill="x", expand=True, padx=12, pady=6)
        ctk.CTkButton(self.drift_bar, text="Ignorer", width=80, height=26, fg_color=BTN2, hover_color=BTN2_HOVER,
                      text_color=P["text"], command=self._ignore_drift).pack(side="right", padx=(4, 8), pady=6)
        ctk.CTkButton(self.drift_bar, text="Voir zones", width=90, height=26, fg_color=BTN2,
                      hover_color=BTN2_HOVER, text_color=P["text"], command=self._show_zones
                      ).pack(side="right", padx=4, pady=6)
        self._tip(ctk.CTkButton(self.drift_bar, text="✨ Recalibrer", width=110, height=26,
                                command=lambda: (self.tabs.set("Calibration"),
                                                 self._countdown("automatique", self._calib_auto_ui))),
                  "Calibration automatique : affiche l'HDV (onglet Vente) pendant le compte à rebours."
                  ).pack(side="right", padx=4, pady=6)
        self._tip(ctk.CTkCheckBox(head, text="📌", variable=self.v["always_on_top"], width=44),
                  "Fenêtre de l'outil toujours au-dessus du jeu.").pack(side="right", padx=(8, 14))
        self.update_btn = ctk.CTkButton(head, text="", width=150, fg_color=style.CHIP["green"][0],
                                        hover_color=P["green_hover"], text_color=style.CHIP["green"][1])   # affiché si une version plus récente existe

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
        # pastille devant chaque prix : vert = lecture sûre, orange = moyenne, rouge = douteuse
        for c, t in ((0, "Lot"), (2, "Prix"), (3, "Par objet")):
            ctk.CTkLabel(grid, text=t, text_color=MUTED, height=22).grid(
                row=0, column=c, sticky="w" if c == 0 else "e", padx=10, pady=(4, 0))
        self.read_dots, self.read_tips = {}, {}
        for i, lot in enumerate(self.cfg.lots, start=1):
            ctk.CTkLabel(grid, text=str(lot), height=22).grid(row=i, column=0, sticky="w", padx=10)
            dot = ctk.CTkLabel(grid, text="", width=14, height=22, font=ctk.CTkFont(size=12))
            dot.grid(row=i, column=1, sticky="e")
            price = ctk.CTkLabel(grid, textvariable=self.read_vars[lot], text_color=P["gold"], height=22,
                                 font=ctk.CTkFont(size=13, weight="bold"))
            price.grid(row=i, column=2, sticky="e", padx=(4, 10))
            ctk.CTkLabel(grid, textvariable=self.unit_vars[lot], text_color=MUTED, height=22
                         ).grid(row=i, column=3, sticky="e", padx=10)
            self.read_dots[lot] = dot
            self.read_tips[lot] = (Tooltip(dot, ""), Tooltip(price, ""))   # fiabilité au survol
        ctk.CTkFrame(grid, fg_color="transparent", height=4).grid(row=len(self.cfg.lots) + 1, column=0)
        grid.grid_columnconfigure(1, weight=1)   # la pastille reste collée au prix
        self.read_empty.pack(anchor="w", fill="x", padx=14, pady=4)
        ctk.CTkLabel(side, textvariable=self.status_var, text_color=MUTED, wraplength=380,
                     justify="left").pack(side="bottom", anchor="w", padx=14, pady=(0, 10))
        self._refresh_activity()

        # ---------------- journal
        lf = ctk.CTkFrame(self, fg_color=CARD, border_width=1, border_color=P["border"], corner_radius=12)
        lf.grid(row=2, column=0, columnspan=2, sticky="nsew", padx=12, pady=(6, 12))
        self.log_frame = lf
        top = ctk.CTkFrame(lf, fg_color="transparent")
        top.pack(fill="x", padx=8, pady=(6, 0))
        ctk.CTkLabel(top, text="Journal", font=ctk.CTkFont(weight="bold")).pack(side="left", padx=4)
        ctk.CTkSegmentedButton(top, values=list(LOG_FILTERS), variable=self.log_filter, height=24,
                               command=lambda _v: self._render_log()).pack(side="left", padx=10)
        ctk.CTkButton(top, text="Effacer", width=70, height=24, fg_color=BTN2, text_color=P["text"], hover_color=BTN2_HOVER,
                      command=self._clear_log).pack(side="right")
        self.copy_btn = self._tip(ctk.CTkButton(top, text="Copier", width=70, height=24, fg_color=BTN2, text_color=P["text"], hover_color=BTN2_HOVER,
                                                command=self._copy_log),
                                  "Copie les lignes affichées (selon le filtre) : à coller dans un message "
                                  "quand tu signales un problème.")
        self.copy_btn.pack(side="right", padx=6)
        self.log_hint = ctk.CTkLabel(top, text="Clic sur une ligne avec un prix = le copier", text_color=MUTED,
                                     font=ctk.CTkFont(size=11))
        self.log_hint.pack(side="right", padx=8)
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
        self.keys_outer = kb.master
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
        ctk.CTkButton(r, text="Tous les raccourcis", width=150, fg_color=BTN2, text_color=P["text"], hover_color=BTN2_HOVER,
                      command=lambda: self.tabs.set("Raccourcis")).pack(side="left", pady=(4, 0))
        self._tip(ctk.CTkButton(r, text="Aide-mémoire en jeu", width=170, fg_color=BTN2, text_color=P["text"],
                                hover_color=BTN2_HOVER, command=self._toggle_cheatsheet),
                  "Affiche les touches par-dessus le jeu, au-dessus de l'HDV. En jeu : "
                  f"{hk['cheatsheet'].upper()}.").pack(side="left", padx=8, pady=(4, 0))
        self._tip(ctk.CTkButton(r, text="Visite guidée", width=130, fg_color=BTN2, text_color=P["text"],
                                hover_color=BTN2_HOVER, command=self._tour_start),
                  "Les principaux endroits de l'outil, en 5 bulles.").pack(side="left", pady=(4, 0))
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
                              hover_color=BTN2_HOVER if done else P["accent_hover"],
                              text_color=P["text"] if done else P["on_accent"])
        if all_done:
            self.steps_outer.pack_forget()
        for key, lbl in self.tiles.items():
            lbl.configure(text=str(self.stats[key]))
        note = self.relist_all_note
        if note is not None:
            if self.cfg.relist_auto:
                note.pack_forget()
            elif not note.winfo_manager():
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
        for name in ("pause", "show_zones", "cheatsheet", "hud", "toggle_window"):
            self._hotkey_line(b, name, HOTKEY_LABELS[name])
        b = self._section(page, "Dans la fenêtre de l'outil", "Quand c'est l'outil qui a le focus (pas le jeu).")
        self._hotkey_line(b, None, "Changer d'onglet : Accueil, Prix, Mes ventes, Calibration, Raccourcis, "
                                   "Options", literal="Ctrl+1 … 6")
        self._hotkey_line(b, None, "Vider le journal", literal="Ctrl+L")
        self._hotkey_line(b, None, "Fermer l'aide-mémoire et le résumé", literal="Échap")
        adv = self._collapsible(page, "Avancé : raccourcis de calibration",
                                "Rarement utiles : la calibration automatique place tout.")
        b = self._section(adv, "Raccourcis de calibration", "Utilisés dans le jeu, souris sur la zone.")
        for name in CALIB_HOTKEYS:
            self._hotkey_line(b, name, HOTKEY_LABELS[name])
        b = self._section(page, "Tous les raccourcis")
        ctk.CTkButton(b, text="Rétablir les raccourcis par défaut", width=230, fg_color=BTN2, text_color=P["text"], hover_color=BTN2_HOVER,
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
            btn = ctk.CTkButton(r, text="Changer", width=80, height=24, fg_color=BTN2, text_color=P["text"], hover_color=BTN2_HOVER,
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
        self.hk_buttons[name].configure(text="Appuie…", fg_color=ORANGE, text_color=P["on_accent"])
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
        self.hk_buttons[name].configure(text="Changer", fg_color=BTN2, text_color=P["text"])
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
        ctk.CTkButton(box, text="Effacer l'historique", width=150, height=24, fg_color="transparent", text_color=P["text"],
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
        r = self._row(ab)
        self._tip(ctk.CTkButton(r, text="Voir zones", width=90, fg_color=BTN2, text_color=P["text"], hover_color=BTN2_HOVER, command=self._show_zones),
                  "Vérifie où les zones ont été placées.").pack(side="left", padx=(0, 8))
        self._tip(ctk.CTkButton(r, text="Lire (test)", width=90, fg_color=BTN2, text_color=P["text"], hover_color=BTN2_HOVER,
                                command=lambda: self.jobs.put(("read", None))),
                  "Lit l'HDV une fois sans rien vendre : résultat dans le journal et le panneau "
                  "Activité.").pack(side="left")
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
        ctk.CTkButton(r, text="Nouveau", width=90, fg_color=BTN2, text_color=P["text"], hover_color=BTN2_HOVER, command=self._new_profile
                      ).pack(side="left", padx=(8, 4))
        ctk.CTkButton(r, text="Renommer", width=90, fg_color=BTN2, text_color=P["text"], hover_color=BTN2_HOVER,
                      command=self._rename_profile).pack(side="left", padx=4)
        ctk.CTkButton(r, text="Supprimer", width=90, fg_color=BTN2, text_color=P["text"], hover_color=BTN2_HOVER, command=self._delete_profile
                      ).pack(side="left", padx=4)
        self._switch(pb, "Changer de profil tout seul selon le personnage", "auto_profile",
                     tip="Le titre de la fenêtre du jeu donne le personnage (« Perso - Classe - … »). Quand tu "
                         "passes sur un autre personnage, l'outil prend son profil : celui que tu as choisi "
                         "pour lui, ou un profil qui porte son nom. Choisir un profil pendant que tu joues un "
                         "personnage le lui associe.")
        r = self._row(pb)
        self.char_lbl = ctk.CTkLabel(r, text="Personnage : pas encore vu (passe sur le jeu)", text_color=MUTED,
                                     anchor="w", font=ctk.CTkFont(size=12))
        self.char_lbl.pack(side="left", fill="x", expand=True)
        self.char_btn = ctk.CTkButton(r, text="", width=200, height=26, fg_color=BTN2, text_color=P["text"],
                                      hover_color=BTN2_HOVER, command=self._link_character)
        r = self._row(pb)
        self._tip(ctk.CTkLabel(r, text="Couleur du profil", anchor="w"),
                  "Montrée dans le HUD, sur la pastille Profil et sur l'icône près de l'horloge : en "
                  "multi-compte, tu vois d'un coup d'œil quel profil est actif.").pack(side="left", padx=(0, 10))
        self.pcolor_btns = {}
        for key, (label, color) in style.PROFILE_COLORS.items():
            sw = ctk.CTkButton(r, text="", width=24, height=24, corner_radius=12, fg_color=color,
                               hover_color=color, border_width=3, command=lambda k=key: self._set_profile_color(k))
            sw.pack(side="left", padx=2)
            self._tip(sw, label)
            self.pcolor_btns[key] = sw
        self._refresh_profile_colors()
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
                ctk.CTkButton(r, text="✕", width=28, height=26, fg_color=BTN2, text_color=P["text"], hover_color=BTN2_HOVER,
                              command=lambda k=key: self._clear_zone(k)).pack(side="right", padx=(0, 4))
            ctk.CTkButton(r, text="Calibrer", width=80, height=26, command=cmd).pack(side="right", padx=4)
            self.calib_labels[key] = (st, required)

    def _tab_options(self, page):
        page.pack(fill="both", expand=True)
        b = self._section(page, "Général")
        self._switch(b, "Raccourcis actifs seulement quand Dofus a le focus", "require_focus",
                     tip="Évite de déclencher une vente en tapant ailleurs. Désactive seulement si l'outil "
                         "ne reconnaît pas la fenêtre du jeu (message [Focus] dans le journal).")
        self._switch(b, "Sons", "sound", tip="Un son doux différent pour un succès, un avertissement, une "
                                             "erreur, et la fin d'un long parcours.")
        r = self._row(b)
        ctk.CTkLabel(r, text="Volume", width=120, anchor="w").pack(side="left", padx=(42, 0))
        self.vol_slider = ctk.CTkSlider(r, from_=0.05, to=1.0, number_of_steps=19, width=180,
                                        command=self._set_volume)
        self.vol_slider.set(min(1.0, max(0.05, self.cfg.sound_volume)))
        self.vol_slider.pack(side="left")
        self.vol_lbl = ctk.CTkLabel(r, text=f"{self.cfg.sound_volume:.0%}", text_color=MUTED, width=44)
        self.vol_lbl.pack(side="left", padx=6)
        self.sound_test = [0]
        ctk.CTkButton(r, text="▶ Tester", width=80, height=24, fg_color=BTN2, text_color=P["text"], hover_color=BTN2_HOVER,
                      command=self._test_sound).pack(side="left", padx=4)
        self._switch(b, "Notification Windows à la fin d'un long parcours", "notify",
                     tip="Tout vendre ou toute la liste de plus de 20 s : une notification Windows "
                         "quand c'est fini, si tu es dans une autre fenêtre que le jeu et l'outil.")
        self._switch(b, "Fenêtre de l'outil toujours au-dessus du jeu", "always_on_top",
                     tip="Même chose que 📌 en haut. Le jeu doit être en fenêtré ou plein écran fenêtré.")
        r = self._row(b)
        self.hud_switch = self._tip(ctk.CTkSwitch(r, text="HUD par-dessus le jeu (résultat de chaque action)",
                                                  variable=self.v["hud"]),
                  "Une petite ligne au-dessus du jeu : état, dernière action (elle s'allume de la couleur du "
                  "résultat), progression. Les clics la traversent ; visible seulement quand Dofus est au "
                  "premier plan. Touche : "
                  f"{self.cfg.hotkeys['hud'].upper()}.")
        self.hud_switch.pack(side="left")
        self.hud_move_btn = ctk.CTkButton(r, text="Déplacer", width=90, height=24, fg_color=BTN2,
                                          text_color=P["text"], hover_color=BTN2_HOVER, command=self._hud_move)
        self.hud_move_btn.pack(side="left", padx=10)
        r = self._row(b)
        ctk.CTkLabel(r, text="Taille", width=70, anchor="w").pack(side="left", padx=(42, 0))
        seg = ctk.CTkSegmentedButton(r, values=[v[0] for v in HUD_SIZES.values()], command=self._set_hud_size)
        seg.set(HUD_SIZES.get(self.cfg.hud_size, HUD_SIZES["normal"])[0])
        seg.pack(side="left")
        ctk.CTkLabel(r, text="Contenu", width=70, anchor="w").pack(side="left", padx=(16, 0))
        seg = ctk.CTkSegmentedButton(r, values=list(HUD_CONTENTS.values()), command=self._set_hud_content)
        seg.set(HUD_CONTENTS.get(self.cfg.hud_content, HUD_CONTENTS["both"]))
        seg.pack(side="left")
        self._tip(seg, "État : actif, pause… seulement. Action : la dernière action seulement. Pendant un "
                       "parcours, la progression s'affiche toujours.")
        r = self._row(b)
        self.hud_hist_var = ctk.BooleanVar(value=self.cfg.hud_history)
        self._tip(ctk.CTkSwitch(r, text="3 derniers prix sous la ligne", variable=self.hud_hist_var,
                                command=self._set_hud_history),
                  "Les trois derniers lots traités (prix lu → prix mis), le plus récent en couleur : "
                  "pour vérifier d'un coup d'œil, aussi pendant un parcours.").pack(side="left", padx=(42, 0))
        r = self._row(b)
        ctk.CTkLabel(r, text="Opacité", width=70, anchor="w").pack(side="left", padx=(42, 0))
        sl = ctk.CTkSlider(r, from_=0.5, to=1.0, number_of_steps=10, width=180, command=self._set_hud_opacity)
        sl.set(min(1.0, max(0.5, self.cfg.hud_opacity)))
        sl.pack(side="left")
        self.hud_op_lbl = ctk.CTkLabel(r, text=f"{self.cfg.hud_opacity:.0%}", text_color=MUTED, width=44)
        self.hud_op_lbl.pack(side="left", padx=6)
        tr = self._switch(b, "Icône dans la zone de notification (près de l'horloge)", "tray",
                          tip="Clic = ouvrir l'outil. Clic droit : pause, HUD, aide-mémoire, quitter. "
                              "La pastille montre l'état : vert actif, bleu parcours en cours, "
                              "rouge calibration à faire.")
        tm = self._switch(b, "… réduire la fenêtre l'y cache (plus rien dans la barre des tâches)",
                          "tray_minimize", tip="Le bouton « réduire » de la fenêtre cache l'outil près de "
                                               "l'horloge. Clic sur l'icône pour le retrouver.")
        if not TRAY_AVAILABLE:
            tr.configure(state="disabled")
            tm.configure(state="disabled")
        b = self._section(page, "Apparence")
        self._look = {"theme": self.cfg.theme if self.cfg.theme in style.THEMES else "dark",
                      "accent": self.cfg.accent if self.cfg.accent in style.ACCENTS else "blue"}
        r = self._row(b)
        self._tip(ctk.CTkLabel(r, text="Thème", width=120, anchor="w"),
                  "Comme Windows : suit le mode clair / sombre de Windows (Paramètres › Couleurs).").pack(side="left")
        self.theme_seg = ctk.CTkSegmentedButton(r, values=list(style.THEMES.values()), command=self._pick_theme)
        self.theme_seg.set(style.THEMES[self._look["theme"]])
        self.theme_seg.pack(side="left")
        r = self._row(b)
        ctk.CTkLabel(r, text="Couleur", width=120, anchor="w").pack(side="left")
        self.accent_btns = {}
        for key, (label, color, hover) in style.ACCENTS.items():
            sw = ctk.CTkButton(r, text="", width=28, height=28, corner_radius=14, fg_color=color,
                               hover_color=hover, border_width=3, command=lambda k=key: self._pick_accent(k))
            sw.pack(side="left", padx=3)
            self._tip(sw, label)
            self.accent_btns[key] = sw
        self.look_preview = ctk.CTkFrame(b, fg_color="transparent")
        self.look_preview.pack(fill="x", pady=(6, 2))
        self.look_apply = ctk.CTkFrame(b, fg_color="transparent")
        ctk.CTkButton(self.look_apply, text="Appliquer (redémarre l'outil)", width=220,
                      command=self._apply_look).pack(side="left")
        ctk.CTkLabel(self.look_apply, text="Quelques secondes ; tes réglages sont gardés.", text_color=MUTED,
                     font=ctk.CTkFont(size=11)).pack(side="left", padx=10)
        self._refresh_look()
        r = self._row(b)
        self._tip(ctk.CTkLabel(r, text="Style", width=120, anchor="w"),
                  "Verre : le jeu derrière l'outil apparaît flouté, comme une vitre teintée. Reste flouté "
                  "pendant que tu joues. Windows 10 (1803+) ou 11.").pack(side="left")
        seg = ctk.CTkSegmentedButton(r, values=["Classique", "Verre"], command=self._set_ui_style)
        self.style_seg = seg
        seg.set("Verre" if self._glass_on() else "Classique")
        seg.pack(side="left")
        if not style.glass_supported() or not style.is_dark():
            seg.configure(state="disabled")
            ctk.CTkLabel(r, text="(verre : Windows 10 1803+ requis)" if not style.glass_supported()
                         else "(verre : thème sombre seulement)", text_color=MUTED).pack(side="left", padx=8)
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
        self._switch(b, "Animations (fondus des popups, progression douce)", "animations",
                     tip="Désactive si ton PC est lent ou si tu préfères un affichage instantané.")
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
        ctk.CTkButton(b, text="Réapprendre les chiffres", width=180, fg_color=BTN2, text_color=P["text"], hover_color=BTN2_HOVER,
                      command=self._reset_digits).pack(anchor="w", pady=4)
        b = self._section(page, "Sauvegarde", "Réglages, profils (avec leurs personnages et couleurs), "
                                              "calibration et chiffres appris, dans un seul fichier.",
                          tip="Pour changer de PC ou réinstaller. Restaurer remplace les réglages actuels "
                              "(ils sont d'abord gardés dans le dossier « sauvegardes ») puis redémarre l'outil.")
        r = self._row(b)
        ctk.CTkButton(r, text="💾 Sauvegarder…", width=150, command=self._backup).pack(side="left")
        ctk.CTkButton(r, text="Restaurer…", width=120, fg_color=BTN2, text_color=P["text"], hover_color=BTN2_HOVER,
                      command=self._restore).pack(side="left", padx=8)
        b = self._section(page, "Mises à jour et journal", f"Version {core.app_version()}.",
                          tip="Le journal (fichier) garde l'historique des messages et des erreurs : à "
                              "joindre quand tu signales un problème.")
        self._switch(b, "Vérifier au démarrage si une nouvelle version est publiée (GitHub)", "check_updates")
        if core.parse_version(core.app_version()):
            ctk.CTkButton(b, text="Quoi de neuf dans cette version ?", width=240, fg_color=BTN2, text_color=P["text"],
                          hover_color=BTN2_HOVER, command=lambda: self._whats_new(force=True)
                          ).pack(anchor="w", pady=(4, 2))
        ctk.CTkButton(b, text="Revoir la visite guidée", width=240, fg_color=BTN2, text_color=P["text"],
                      hover_color=BTN2_HOVER, command=self._tour_start).pack(anchor="w", pady=(2, 2))
        r = self._row(b)
        ctk.CTkButton(r, text="Ouvrir le dossier du journal", width=200, fg_color=BTN2, text_color=P["text"], hover_color=BTN2_HOVER,
                      command=self._open_log_dir).pack(side="left")
        ctk.CTkButton(r, text="Page des versions", width=150, fg_color=BTN2, text_color=P["text"], hover_color=BTN2_HOVER,
                      command=lambda: self._open_url(core.RELEASES_URL)).pack(side="left", padx=8)
        r = self._row(b)
        self._tip(ctk.CTkButton(r, text="📦 Rapport de problème", width=200,
                                command=lambda: self._countdown("rapport", self._make_report)),
                  "Crée un zip à envoyer quand quelque chose ne marche pas : journal, réglages, captures "
                  "de diagnostic et une image de l'HDV (affiche-le pendant le compte à rebours). Rien "
                  "n'est envoyé tout seul ; ton historique de ventes n'est pas inclus.").pack(side="left")
        ctk.CTkButton(r, text="Signaler sur GitHub", width=150, fg_color=BTN2, text_color=P["text"], hover_color=BTN2_HOVER,
                      command=lambda: self._open_url(dofus_update.ISSUES_URL)).pack(side="left", padx=8)

    # ---- apparence : thème, couleur d'accent (appliqués au redémarrage, avec un aperçu)
    def _pick_theme(self, label: str):
        self._look["theme"] = next((k for k, v in style.THEMES.items() if v == label), "dark")
        self._refresh_look()

    def _pick_accent(self, key: str):
        self._look["accent"] = key
        self._refresh_look()

    def _refresh_look(self):
        for key, sw in self.accent_btns.items():
            sw.configure(border_color=P["text"] if key == self._look["accent"] else P["card"])
        self._render_look_preview()
        pending = (self._look["theme"], self._look["accent"]) != (self.cfg.theme, self.cfg.accent)
        if pending and not self.look_apply.winfo_manager():
            self.look_apply.pack(fill="x", pady=(4, 2), after=self.look_preview)
        elif not pending:
            self.look_apply.pack_forget()

    def _render_look_preview(self):
        """Aperçu du thème et de la couleur choisis, avec leurs vraies couleurs."""
        box = self.look_preview
        for w in box.winfo_children():
            w.destroy()
        pal = style.palette(**self._look)
        chip = style.chips(self._look["theme"])
        outer = ctk.CTkFrame(box, fg_color=pal["bg"], corner_radius=12, border_width=1, border_color=pal["border"])
        outer.pack(fill="x")
        card = ctk.CTkFrame(outer, fg_color=pal["card"], corner_radius=10, border_width=1,
                            border_color=pal["border"])
        card.pack(fill="x", padx=10, pady=10)
        r1 = ctk.CTkFrame(card, fg_color="transparent")
        r1.pack(fill="x", padx=12, pady=(10, 2))
        ctk.CTkLabel(r1, text="◆", text_color=pal["gold"], font=ctk.CTkFont(size=16)).pack(side="left")
        ctk.CTkLabel(r1, text=" Aperçu", text_color=pal["text"], font=ctk.CTkFont(size=14, weight="bold")
                     ).pack(side="left")
        ctk.CTkLabel(r1, text="● Actif", fg_color=chip["green"][0], text_color=chip["green"][1], corner_radius=11,
                     height=22, font=ctk.CTkFont(size=11, weight="bold")).pack(side="right", ipadx=8)
        r2 = ctk.CTkFrame(card, fg_color="transparent")
        r2.pack(fill="x", padx=12)
        ctk.CTkLabel(r2, text="Lot 10 → 9 499", text_color=pal["gold"], font=ctk.CTkFont(size=13, weight="bold")
                     ).pack(side="left")
        ctk.CTkLabel(r2, text="  Mis en vente", text_color=pal["green"]).pack(side="left")
        ctk.CTkLabel(r2, text="12:41", text_color=pal["muted"]).pack(side="right")
        r3 = ctk.CTkFrame(card, fg_color="transparent")
        r3.pack(fill="x", padx=12, pady=(6, 12))
        ctk.CTkButton(r3, text="Vendre", width=80, height=26, fg_color=pal["accent"], hover_color=pal["accent_hover"],
                      text_color=pal["on_accent"]).pack(side="left")
        ctk.CTkButton(r3, text="Annuler", width=80, height=26, fg_color=pal["btn2"], hover_color=pal["btn2_hover"],
                      text_color=pal["text"]).pack(side="left", padx=6)
        sw = ctk.CTkSwitch(r3, text="Option", fg_color=pal["track"], progress_color=pal["accent"],
                           button_color=pal["knob"], button_hover_color=pal["knob_hover"], text_color=pal["text"])
        sw.select()
        sw.pack(side="left", padx=6)
        pb = ctk.CTkProgressBar(r3, width=110, height=8, fg_color=pal["track"], progress_color=pal["accent"])
        pb.set(0.6)
        pb.pack(side="left", padx=6)

    def _apply_look(self):
        if self.engine._lock.locked() or self._loop is not None:
            self._log("[Apparence] Une action est en cours : applique le thème quand elle est finie.", "WARN")
            return
        self.cfg.theme, self.cfg.accent = self._look["theme"], self._look["accent"]
        self._save_cfg()
        self.restart_requested = True
        self._on_close()

    # ---- sons
    def _set_volume(self, value: float):
        self.cfg.sound_volume = round(float(value), 2)
        self.vol_lbl.configure(text=f"{self.cfg.sound_volume:.0%}")
        if getattr(self, "_vol_save", None):
            self.after_cancel(self._vol_save)
        self._vol_save = self.after(500, self._save_cfg)

    def _test_sound(self):
        kinds = ("ok", "warn", "error", "done")
        kind = kinds[self.sound_test[0] % len(kinds)]
        self.sound_test[0] += 1
        core.beep(kind, self.cfg, force=True)
        names = {"ok": "succès", "warn": "avertissement", "error": "erreur", "done": "fin de parcours"}
        self._log(f"[Sons] Son « {names[kind]} » (re-clique pour le suivant).", "INFO")

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
        self._refresh_character()
        self._refresh_profile_colors()

    def _switch_profile(self, name: str):
        if name == self.cfg.profile:
            return
        if self._busy():
            self.profile_var.set(self.cfg.profile)
            return
        self.cfg.switch_profile(name)
        extra = ""
        if self._char and self.cfg.auto_profile:     # sinon le profil auto le remettrait aussitôt
            self.cfg.character_profiles[self._char] = name
            extra = f" Utilisé désormais pour {self._char}."
        self._after_profile_change(f"[Profil] « {name} » actif.{extra}")

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
        if self._char and self.cfg.auto_profile:
            self.cfg.character_profiles[self._char] = self.cfg.profile
        self._after_profile_change(f"[Profil] « {self.cfg.profile} » créé (copie) et actif : recalibre "
                                   "ce qui change dans cet HDV.")

    def _rename_profile(self):
        if self._busy():
            return
        old = self.cfg.profile
        name = ctk.CTkInputDialog(title="Renommer le profil",
                                  text=f"Nouveau nom pour « {old} » :").get_input()
        if name is None or name.strip() == old:
            return
        with self._profile_lock:
            try:
                self.cfg.rename_profile(old, name)
            except (ValueError, KeyError) as e:
                self._log(f"[Profil] {e}.", "ERROR")
                return
            except OSError as e:
                self._log(f"[Profil] Repère non renommé ({e}) : recalibre le repère de ce profil.", "WARN")
        self._after_profile_change(f"[Profil] « {old} » renommé en « {self.cfg.profile} ».")

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

    ICON_COLORS = {"sale": "gold", "update": "cyan", "warn": "orange", "error": "red", "cal": "cyan",
                   "ok": "green", "info": "log_time"}

    def _setup_log_tags(self):
        t = self.log_text
        for tag, color in TAG_COLORS.items():
            t.tag_configure(tag, foreground=color)
        for kind, color in self.ICON_COLORS.items():
            t.tag_configure(f"I_{kind}", foreground=P[color])
        t.tag_configure("HDR", foreground=P["cyan"], font=(style.MONO, self._log_font_size(), "bold"))
        t.tag_configure("FOCUS", background=P["track"])
        t.tag_bind("PRICE", "<Button-1>", self._on_log_click)
        t.tag_bind("PRICE", "<Enter>", lambda _e: t.configure(cursor="hand2"))
        t.tag_bind("PRICE", "<Leave>", lambda _e: t.configure(cursor=""))

    def _on_log_click(self, e):
        """Clic sur une ligne qui contient un prix : le prix est copié (à coller dans le jeu)."""
        t = self.log_text
        ids = [n for n in t.tag_names(t.index(f"@{e.x},{e.y}")) if n[:1] == "e" and n[1:].isdigit()]
        if not ids:
            return
        k = int(ids[0][1:])
        entry = next((x for x in reversed(self.log_entries) if x.get("id") == k), None)
        if entry is None or entry.get("price") is None:
            return
        self.clipboard_clear()
        self.clipboard_append(str(entry["price"]))
        self.log_hint.configure(text=f"{fmt(entry['price'])} copié ✓", text_color=P["green"])
        if getattr(self, "_hint_after", None):
            self.after_cancel(self._hint_after)
        self._hint_after = self.after(1800, lambda: self.log_hint.configure(
            text="Clic sur une ligne avec un prix = le copier", text_color=MUTED))

    def _log(self, msg: str, tag: str = "INFO", price: Optional[int] = None):
        core.log_line(msg, tag)
        self._log_seq += 1
        e = {"t": time.strftime("%H:%M:%S"), "msg": msg, "tag": tag, "cat": log_category(msg, tag),
             "block": self._block, "header": False, "id": self._log_seq, "price": price,
             "kind": log_kind(msg, tag)}
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
            kind = e.get("kind", "info")
            t.insert("end", ("   " if e["block"] is not None else "") + LOG_ICONS[kind] + " ", (f"I_{kind}",))
            tags = (e["tag"],) + ((f"e{e['id']}",) if e.get("id") else ()) + (
                ("PRICE",) if e.get("price") is not None else ())
            t.insert("end", e["msg"].lstrip() + "\n", tags)
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

    def _block_start(self, kind: str = "relist_all"):
        """Début d'un parcours (Ctrl+F3, F2) : ses lignes vont dans un bloc repliable du journal."""
        self._block_seq += 1
        self._block = self._block_seq
        key = self.cfg.hotkeys.get(kind, "").upper()
        self.log_blocks[self._block] = {
            "title": f"{key} · {self.LOOP_NAMES.get(kind, 'Parcours')} · {time.strftime('%H:%M:%S')} · en cours…",
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
        for name in ("auto_paste", "click_field", "auto_validate", "require_focus", "sound",
                     "relist_auto", "relist_confirm_enter", "relist_summary", "fast_digits", "auto_recalibrate",
                     "verify_before_enter", "smart_f1", "always_on_top", "check_updates", "notify",
                     "animations", "tray", "tray_minimize", "auto_profile", "hud"):
            setattr(c, name, bool(v[name].get()))
        ANIMATE["on"] = c.animations
        self._apply_hud()
        self._apply_tray()
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
            core.HOTKEYS.add(hk["hud"], lambda: self.ui_events.put(("hud", None)))
            core.HOTKEYS.add(hk["toggle_window"], lambda: self.ui_events.put(("toggle_window", None)))
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
                # dans la file. L'exécuter après coup agirait sur un écran
                # qui a changé depuis -> ignorée.
                waited = time.time() - pressed[0]
                if waited > STALE_JOB_S:
                    self.ui_events.put(("log", (f"[Hotkeys] Raccourci ignoré (appuyé il y a {waited:.0f} s, "
                                                "pendant une autre action).", "WARN")))
                    continue
                try:                     # autre personnage au premier plan : son profil d'abord
                    msg = self._auto_profile()
                    if msg:
                        self.ui_events.put(("profile_auto", msg))
                except Exception:
                    pass
            try:
                if name == "sell":
                    res = self.engine.sell(optimize=True) if arg else self.engine.smart()
                    self.ui_events.put(("result", res))
                elif name == "sell_all":
                    self.ui_events.put(("block_start", "sell_all"))
                    self.ui_events.put(("loop_start", "sell_all"))
                    res = None
                    try:
                        res = self.engine.sell_all()
                        self.ui_events.put(("result", res))
                    finally:
                        self.ui_events.put(("block_end", res))
                        self.ui_events.put(("loop_end", res))
                elif name == "relist":
                    self.ui_events.put(("result", self.engine.relist()))
                elif name == "relist_all":
                    self.ui_events.put(("block_start", "relist_all"))
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
                elif name == "wiz_zone":
                    self.ui_events.put(("wiz_zone", self._zone_check(arg)))
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
        """Traite les événements du fil de travail. Une erreur sur un événement est notée et
        les suivants sont traités : avant, une seule erreur arrêtait cette boucle pour de bon
        (interface figée : fin de « Tout vendre » jamais affichée, « Arrêt… » bloqué)."""
        try:
            while True:
                try:
                    name, arg = self.ui_events.get_nowait()
                except queue.Empty:
                    break
                try:
                    self._handle_ui_event(name, arg)
                except Exception as e:
                    import traceback
                    core.log_line("Erreur interface :\n" + traceback.format_exc(), "ERROR")
                    self._log(f"[Erreur] {e}", "ERROR")
        finally:
            self.after(30, self._poll_ui)

    def _handle_ui_event(self, name, arg):
        if name == "result":
            self._on_result(arg)
        elif name == "row":
            self._log("   " + arg.message, {"warn": "WARN", "error": "ERROR"}.get(arg.level, "OK"), arg.new_price)
            self._push_history(arg)
        elif name == "block_start":
            self._block_start(arg or "relist_all")
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
        elif name == "hud":
            self._toggle_hud()
        elif name == "toggle_window":
            self._toggle_window()
        elif name == "profile_auto":
            self._on_auto_profile(arg)
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
            self._on_pause_key()
        elif name == "refresh":
            self._refresh_status()
        elif name == "wizard_test":
            self._wiz_report_show(arg)
        elif name == "wiz_zone":
            self._wiz_zone_show(arg)
        elif name == "tray":
            self._on_tray(arg)
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

    # ------------------------------------------------------------- results
    def _on_result(self, res: core.Result):
        self._show_screen(res.screen)
        self._count_stats(res)
        tag = {"warn": "WARN", "error": "ERROR"}.get(res.level) or (
            "OPT" if res.message.startswith("[OPT]") else "OK")
        self._log(res.message, tag, res.new_price)
        if res.message.startswith("[MAJ TOUT]"):
            self._relist_summary(res)
        if self._loop is None or res.level != "ok":
            core.beep(res.level, self.cfg)       # fin d'une boucle réussie : son « fin de parcours »
        head = (f"Lot {res.lot} → {fmt(res.new_price)}" if res.new_price is not None
                else "Liste mise à jour" if res.message.startswith("[MAJ TOUT]") else "Pas de prix")
        self.last_action = (head, res.hint or res.level, LEVEL_COLORS[res.level])
        remind = validate_reminder(res, self.cfg)
        if remind:                                   # prix prêt mais pas mis en vente : à toi de valider
            self.last_action = (head, remind, P["gold"])
        self._add_activity(res)
        self._push_history(res, refresh=False)
        if res.level == "ok" and res.message.startswith(("[VENTE]", "[OPT]", "[TOUT]", "[MAJ]")) \
                and ("mis en vente" in res.message or "modifié" in res.message or res.message.startswith("[TOUT]")):
            self._mark_step("sell")
        self._refresh_hud()
        self._hud_flash(P["gold"] if remind else LEVEL_COLORS[res.level])   # le HUD remplace l'ancien popup

    # ---- résumé de fin de Ctrl+F3
    def _relist_summary(self, res: core.Result):
        """Journal : une ligne par prix modifié / ligne à revoir. Historique (onglet Mes ventes) et
        fenêtre : la même chose avec l'image du nom de chaque objet (le nom n'est pas lu en texte)."""
        ids = []                                     # lignes du journal : clic dans le récap = y aller
        for c in res.changes:
            self._log("   " + c.text(), "OK" if c.modified else "WARN", c.new if c.modified else None)
            ids.append(self._log_seq)
        run = {"time": time.time(), "changes": list(res.changes), "summary": dict(res.summary), "log_ids": ids}
        if res.changes:
            self.runs = (self.runs + [run])[-MAX_RUNS:]
            try:
                save_runs(self.runs)
            except OSError as e:
                self._log(f"[Résumé] Historique non enregistré : {e}", "WARN")
            self._refresh_runs()
        if self.cfg.relist_summary and (res.changes or res.summary):
            self._summary_window(run)

    def _summary_window(self, run: dict):
        changes = run["changes"]
        mod = [c for c in changes if c.modified]
        bad = [c for c in changes if not c.modified]
        w = getattr(self, "_summary_win", None)
        if w is not None and w.winfo_exists():
            w.destroy()
        w = ctk.CTkToplevel(self)
        brand(w)
        self._summary_win = w
        w.title("Résumé de la mise à jour (Ctrl+F3) · "
                + time.strftime("%d/%m %H:%M", time.localtime(run["time"])))
        w.geometry("560x560")
        w.attributes("-topmost", True)
        summary = run.get("summary") or {}
        if summary:
            self._summary_tiles(w, summary, len(mod), len(bad))
        else:                                        # ancien parcours (avant le récap)
            ctk.CTkLabel(w, text=f"{len(mod)} prix modifié{'s' if len(mod) > 1 else ''}"
                                 + (f"  ·  {len(bad)} ligne{'s' if len(bad) > 1 else ''} à revoir avec "
                                    f"{self.cfg.hotkeys['relist'].upper()}" if bad else ""),
                         font=ctk.CTkFont(size=15, weight="bold")).pack(anchor="w", padx=14, pady=(12, 4))
        ids = dict(zip(map(id, changes), run.get("log_ids") or []))
        hint = ctk.CTkLabel(w, text="Clic sur une ligne = la retrouver dans le journal" if ids else "",
                            text_color=MUTED, font=ctk.CTkFont(size=11))
        if ids:
            hint.pack(anchor="w", padx=14)
        body = ctk.CTkScrollableFrame(w, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=8, pady=4)
        if not changes:
            ctk.CTkLabel(body, text="Rien à modifier : tes ventes sont déjà au bon prix.",
                         text_color=MUTED).pack(anchor="w", padx=8, pady=8)
        self._summary_imgs = []                     # garder les images (sinon effacées par Tk)
        for c in bad + mod:                          # à revoir en premier
            r = ctk.CTkFrame(body, fg_color=CARD)
            r.pack(fill="x", pady=2)
            img = self._name_thumb(c.img)
            if img is not None:
                self._summary_imgs.append(img)
                ctk.CTkLabel(r, text="", image=img).pack(side="left", padx=6, pady=4)
            if id(c) in ids:
                self._clickable(r, lambda k=ids[id(c)]: self._jump_to_log(k, w, hint))
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
        w.bind("<Escape>", lambda _e: w.destroy())

    def _summary_tiles(self, w, s: dict, mod: int, bad: int):
        """Récap en tête du résumé : modifiés, à revoir, déjà au bon prix, durée, et pourquoi ça s'est arrêté."""
        row = ctk.CTkFrame(w, fg_color="transparent")
        row.pack(fill="x", padx=10, pady=(12, 2))
        tiles = ((mod, "modifiés" if mod > 1 else "modifié", P["green"] if mod else MUTED),
                 (bad, "à revoir", P["orange"] if bad else MUTED),
                 (s.get("same", 0), "déjà au bon prix", P["text"]),
                 (duration_text(s.get("seconds")), "durée", P["text"]))
        for i, (value, label, color) in enumerate(tiles):
            row.grid_columnconfigure(i, weight=1, uniform="tile")
            t = ctk.CTkFrame(row, fg_color=CARD, corner_radius=10)
            t.grid(row=0, column=i, sticky="ew", padx=4)
            ctk.CTkLabel(t, text=str(value), text_color=color,
                         font=ctk.CTkFont(size=20, weight="bold")).pack(pady=(6, 0))
            ctk.CTkLabel(t, text=label, text_color=MUTED, font=ctk.CTkFont(size=11)).pack(pady=(0, 6))
        seen = s.get("seen", 0)
        if s.get("complete", True):
            end, color = f"{seen} ligne{'s' if seen > 1 else ''} vue{'s' if seen > 1 else ''} · toute la liste", MUTED
        else:
            end, color = f"{seen} ligne{'s' if seen > 1 else ''} vue{'s' if seen > 1 else ''} · arrêté : " \
                         f"{s.get('stop', '?')}", P["orange"]
        if bad:
            end += f"  ·  lignes à revoir : {self.cfg.hotkeys['relist'].upper()} une par une"
        ctk.CTkLabel(w, text=end, text_color=color, anchor="w", justify="left",
                     wraplength=520).pack(anchor="w", padx=14, pady=(4, 2))

    @staticmethod
    def _clickable(frame, command):
        """Tout le cadre (et ce qu'il contient) réagit au clic."""
        for wdg in [frame] + list(frame.winfo_children()):
            try:
                wdg.configure(cursor="hand2")
            except (tk.TclError, ValueError):
                pass
            wdg.bind("<Button-1>", lambda _e: command())

    def _jump_to_log(self, entry_id: int, win=None, hint=None) -> bool:
        """Résumé -> journal : la ligne est affichée (bloc déplié, filtre « Tout » si besoin) et surlignée."""
        entry = next((e for e in self.log_entries if e.get("id") == entry_id), None)
        if entry is None:
            if hint is not None:
                hint.configure(text="Cette ligne n'est plus dans le journal (effacé).", text_color=P["orange"])
            return False
        b = self.log_blocks.get(entry["block"]) if entry["block"] is not None else None
        if b is not None:
            b["collapsed"] = False
        if not self._entry_visible(entry):
            self.log_filter.set("Tout")
        self._render_log()
        t = self.log_text
        rng = t.tag_ranges(f"e{entry_id}")
        if not rng:
            return False
        t.tag_remove("FOCUS", "1.0", "end")
        t.tag_add("FOCUS", f"{rng[0]} linestart", f"{rng[-1]} lineend")
        t.tag_raise("FOCUS")
        t.see(rng[0])
        if getattr(self, "_focus_after", None):
            self.after_cancel(self._focus_after)
        self._focus_after = self.after(3000, lambda: t.tag_remove("FOCUS", "1.0", "end"))
        if win is not None:
            try:
                win.attributes("-topmost", False)      # le journal passe devant le résumé
            except tk.TclError:
                pass
        self._show_main()
        self.lift()
        return True

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
            # winfo_manager (placé ?) et non winfo_ismapped (visible ?) : fenêtre réduite pendant
            # Tout vendre, le tableau déjà placé était « non visible » -> pack(before=…) sur un
            # widget retiré -> TclError, et toute l'interface se figeait (« Arrêt… » bloqué).
            if not self.read_grid.winfo_manager():
                if self.read_empty.winfo_manager():
                    self.read_grid.pack(fill="x", padx=12, pady=6, before=self.read_empty)
                    self.read_empty.pack_forget()
                else:
                    self.read_grid.pack(fill="x", padx=12, pady=6)
        self.qty_var.set(str(sr.selected) if sr.selected else "?")
        qcolors = {"good": P["green"], "doubt": P["orange"], "bad": P["red"]}
        for lot, var in self.read_vars.items():
            r = sr.prices.get(lot)
            level, why = reading_quality(r, self.cfg.min_confidence)
            if sr.engine and level:
                why += " · " + {"chiffres": "lecture rapide", "tesseract": "Tesseract"}.get(sr.engine, sr.engine)
            self.read_dots[lot].configure(text="●" if level else "", text_color=qcolors.get(level, MUTED))
            for tip in self.read_tips[lot]:
                tip.text = why
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

    RECT_KEYS = ("anchor", "table", "qty", "avg", "count", "name", "mine")

    def _open_wizard(self):
        w = getattr(self, "_wiz", None)
        if w is not None and w.winfo_exists():
            w.lift()
            return
        w = ctk.CTkToplevel(self)
        brand(w)
        w.title("Assistant de calibration")
        w.geometry("940x660")
        w.minsize(860, 600)
        w.attributes("-topmost", True)
        self._wiz, self._wiz_i = w, 0
        self._wiz_seen = dict(self._wiz_values())   # pour voir quand une zone vient d'être calibrée
        self._wiz_img = None
        # à gauche : toutes les étapes, cliquables, avec leur état
        side = ctk.CTkFrame(w, fg_color=CARD, corner_radius=12, border_width=1, border_color=P["border"], width=270)
        side.pack(side="left", fill="y", padx=(12, 6), pady=12)
        side.pack_propagate(False)
        ctk.CTkLabel(side, text="Étapes", font=ctk.CTkFont(size=14, weight="bold"), anchor="w"
                     ).pack(fill="x", padx=12, pady=(10, 4))
        self._wiz_steps = []
        for i in range(len(self.WIZ_STEPS) + 1):
            sb = ctk.CTkButton(side, text="", anchor="w", height=26, fg_color="transparent",
                               hover_color=P["btn2_hover"], text_color=P["text"], font=ctk.CTkFont(size=12),
                               command=lambda k=i: self._wiz_jump(k))
            sb.pack(fill="x", padx=6, pady=1)
            self._wiz_steps.append(sb)
        auto = ctk.CTkButton(side, text="✨ Tout placer automatiquement", height=34,
                             command=lambda: self._countdown("automatique", self._calib_auto_ui))
        auto.pack(side="bottom", fill="x", padx=10, pady=10)
        self._tip(auto, "HDV ouvert sur l'onglet « Vente » : l'outil place toutes les zones, puis tu "
                        "vérifies chaque étape ici (capture + lecture).")
        main = ctk.CTkFrame(w, fg_color="transparent")
        main.pack(side="left", fill="both", expand=True, padx=(6, 12), pady=12)
        self._wiz_title = ctk.CTkLabel(main, text="", font=ctk.CTkFont(size=16, weight="bold"), anchor="w")
        self._wiz_title.pack(fill="x", pady=(2, 4))
        self._wiz_prep = ctk.CTkLabel(main, text="", wraplength=600, justify="left", anchor="w",
                                      text_color=P["cyan"])
        self._wiz_prep.pack(fill="x")
        self._wiz_text = ctk.CTkLabel(main, text="", wraplength=600, justify="left", anchor="w")
        self._wiz_text.pack(fill="x", pady=(8, 0))
        # ce que l'outil voit dans la zone : capture + verdict, refait après chaque calibration
        self._wiz_check = ctk.CTkFrame(main, fg_color=CARD, corner_radius=12, border_width=1,
                                       border_color=P["border"])
        hr = ctk.CTkFrame(self._wiz_check, fg_color="transparent")
        hr.pack(fill="x", padx=12, pady=(8, 2))
        ctk.CTkLabel(hr, text="Ce que l'outil voit", font=ctk.CTkFont(size=13, weight="bold")).pack(side="left")
        self._wiz_state = ctk.CTkLabel(hr, text="", font=ctk.CTkFont(weight="bold"))
        self._wiz_state.pack(side="right")
        ctk.CTkButton(hr, text="↻ Relire", width=70, height=22, fg_color=BTN2, text_color=P["text"], hover_color=BTN2_HOVER,
                      command=self._wiz_zone_check).pack(side="right", padx=8)
        self._wiz_cap = ctk.CTkLabel(self._wiz_check, text="")
        self._wiz_cap.pack(padx=12, pady=4)
        self._wiz_verdict = ctk.CTkLabel(self._wiz_check, text="", anchor="w", justify="left", wraplength=580)
        self._wiz_verdict.pack(fill="x", padx=12, pady=(0, 10))
        self._wiz_msg = ctk.CTkLabel(main, text="", anchor="w", text_color=P["gold"], wraplength=600,
                                     justify="left")
        self._wiz_report = ctk.CTkTextbox(main, height=150, font=(style.MONO, 11))
        bar = ctk.CTkFrame(main, fg_color="transparent")
        bar.pack(side="bottom", fill="x", pady=(8, 0))
        self._wiz_back = ctk.CTkButton(bar, text="← Retour", width=90, fg_color=BTN2, text_color=P["text"], hover_color=BTN2_HOVER,
                                       command=lambda: self._wiz_go(-1))
        self._wiz_back.pack(side="left")
        ctk.CTkButton(bar, text="Voir zones", width=90, fg_color=BTN2, text_color=P["text"], hover_color=BTN2_HOVER,
                      command=self._show_zones).pack(side="left", padx=8)
        self._wiz_next = ctk.CTkButton(bar, text="Suivant →", width=110, command=lambda: self._wiz_go(1))
        self._wiz_next.pack(side="right")
        self._wiz_do = ctk.CTkButton(bar, text="Calibrer", width=150, command=self._wiz_calibrate)
        self._wiz_do.pack(side="right", padx=8)
        self._wiz_show()
        self._wiz_tick()

    def _wiz_values(self):
        c = self.cfg
        return {"anchor": c.anchor_region, "table": c.table_region, "qty": c.qty_region,
                "price_field": c.price_field, "avg": c.avg_region, "count": c.count_region,
                "modify_button": c.modify_button, "rows": c.relist_row, "sell_button": c.sell_button,
                "name": c.name_region, "mine": c.mine_region}

    def _wiz_refresh_steps(self):
        vals = self._wiz_values()
        for i, sb in enumerate(self._wiz_steps):
            if i < len(self.WIZ_STEPS):
                key, _k, title, optional = self.WIZ_STEPS[i][:4]
                done = bool(vals.get(key))
                mark, col = ("✓", P["green"]) if done else (("–", MUTED) if optional else ("✗", P["red"]))
                text = f"{mark}  {i + 1}. {title}"
            else:
                text, col = f"▶  {i + 1}. Vérification finale", P["text"]
            sb.configure(text=text if len(text) < 38 else text[:36] + "…", text_color=col,
                         fg_color=P["btn2"] if i == self._wiz_i else "transparent")

    def _wiz_jump(self, i: int):
        self._wiz_i = i
        self._wiz_show()

    def _wiz_show(self):
        n = len(self.WIZ_STEPS)
        self._wiz_msg.configure(text="")
        self._wiz_refresh_steps()
        self._wiz_back.configure(state="normal" if self._wiz_i > 0 else "disabled")
        if self._wiz_i >= n:
            self._wiz_prep.configure(text="")
            self._wiz_title.configure(text=f"Vérification finale ({n + 1}/{n + 1})")
            self._wiz_text.configure(text="L'outil lit tout une fois et dit ce qui va et ce qui ne va pas. "
                                          "Sélectionne un objet de ton inventaire (ou une de tes ventes) "
                                          "dans l'HDV ; « Relancer » refait la lecture.")
            self._wiz_check.pack_forget()
            self._wiz_msg.pack_forget()
            self._wiz_do.configure(text="Relancer le test", command=self._wiz_test)
            self._wiz_next.configure(text="Terminer", command=self._wiz.destroy)
            self._wiz_report.pack(fill="both", expand=True, pady=(8, 0))
            self._wiz_test()                     # lancée toute seule en arrivant ici
            return
        self._wiz_report.pack_forget()
        self._wiz_check.pack(fill="x", pady=(10, 0))
        self._wiz_msg.pack(fill="x", pady=(6, 0))
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
                        f"(sans cliquer). Raccourci en jeu : {self.cfg.hotkeys[hot].upper()}.")
        self._wiz_next.configure(text="Suivant →" if not optional else "Suivant / passer →",
                                 command=lambda: self._wiz_go(1))
        self._wiz_update_state()
        if self._wiz_values().get(key):
            self._wiz_zone_check()
        else:
            self._wiz_cap.configure(image=None, text="")
            self._wiz_img = None
            self._wiz_verdict.configure(text="Pas encore calibré : clique « Calibrer »"
                                             + (" ou passe cette étape." if optional else "."),
                                        text_color=MUTED)

    def _wiz_update_state(self):
        if self._wiz_i >= len(self.WIZ_STEPS):
            return
        ok = bool(self._wiz_values().get(self.WIZ_STEPS[self._wiz_i][0]))
        self._wiz_state.configure(text="✓ Calibré" if ok else "✗ Pas encore calibré",
                                  text_color=P["green"] if ok else P["red"])
        self._wiz_do.configure(text="↺ Refaire cette zone" if ok else "Calibrer", command=self._wiz_calibrate)

    def _wiz_tick(self):
        w = getattr(self, "_wiz", None)
        if w is None or not w.winfo_exists():
            return
        vals = self._wiz_values()
        if vals != self._wiz_seen:               # une zone vient d'être (re)calibrée
            changed = {k for k in vals if vals[k] != self._wiz_seen.get(k)}
            self._wiz_seen = dict(vals)
            self._wiz_refresh_steps()
            if self._wiz_i < len(self.WIZ_STEPS):
                self._wiz_update_state()
                key = self.WIZ_STEPS[self._wiz_i][0]
                if key in changed and vals.get(key):
                    self._wiz_zone_check()
        msg = self.status_var.get()
        if self._wiz_i < len(self.WIZ_STEPS):
            self._wiz_msg.configure(text=msg if msg.startswith("Calibration") else "")
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

    def _wiz_zone_check(self):
        if self._wiz_i >= len(self.WIZ_STEPS):
            return
        self._wiz_verdict.configure(text="Lecture…", text_color=MUTED)
        self.jobs.put(("wiz_zone", self.WIZ_STEPS[self._wiz_i][0]))

    def _zone_check(self, key: str) -> dict:
        """(thread de travail) Capture de la zone + ce que l'outil y lit, pour l'assistant."""
        val = self._wiz_values().get(key)
        out = {"key": key, "img": None, "ok": None, "lines": ["Pas encore calibré."]}
        if not val:
            return out
        try:
            from PIL import Image, ImageDraw
            bx, by, bw, bh = core.screen_bounds()
            mark = None
            if key in self.RECT_KEYS:
                x, y, w, h = val
            else:                                  # point : la zone autour, avec une cible
                px, py = val[0], val[1]
                hw, hh = (160, max(14, int(self.cfg.relist_step or 30))) if key == "rows" else (110, 35)
                x, y, w, h = px - hw, py - hh, 2 * hw, 2 * hh + (hh if key == "rows" else 0)
                mark = (px, py)
            x0, y0 = max(bx, x), max(by, y)
            x1, y1 = min(bx + bw, x + w), min(by + bh, y + h)
            if x1 - x0 < 2 or y1 - y0 < 2:
                return {"key": key, "img": None, "ok": False, "lines": ["✗ Zone hors de l'écran : refais-la."]}
            pil = Image.fromarray(core.grab_screen((x0, y0, x1 - x0, y1 - y0))[:, :, ::-1].copy())
            if mark:
                d = ImageDraw.Draw(pil)
                mx, my = mark[0] - x0, mark[1] - y0
                d.ellipse((mx - 9, my - 9, mx + 9, my + 9), outline="#ff3b5c", width=2)
                d.line((mx - 14, my, mx + 14, my), fill="#ff3b5c", width=1)
                d.line((mx, my - 14, mx, my + 14), fill="#ff3b5c", width=1)
            out["img"] = pil
            out["ok"], out["lines"] = self._zone_verdict(key)
        except Exception as e:
            out["ok"], out["lines"] = False, [f"✗ Erreur : {e}"]
        return out

    def _zone_verdict(self, key: str) -> tuple:
        """(ok : True / False / None = impossible à vérifier maintenant, lignes)."""
        c = self.cfg
        warn = []
        if key in core.CUT_CHECK_ZONES and core.cut_text_hint(key, getattr(c, f"{key}_region")):
            warn = ["⚠ Le texte touche le bord de la zone (chiffre coupé ?) : refais-la avec 3-4 px de "
                    "marge en haut et en bas."]
        if key == "anchor":
            tpl = core.load_anchor(core.anchor_path(c))
            if tpl is None:
                return False, ["✗ Image du repère absente : refais la zone."]
            score = core.anchor_score(core.grab_screen(tuple(c.anchor_region)), tpl)
            if score >= core.ANCHOR_FOUND:
                return True, [f"✓ Titre « Hôtel de vente » reconnu ({score:.0%})."]
            return False, [f"✗ Titre pas reconnu ici ({score:.0%}) : HDV fermé ou déplacé, ou zone mal placée."]
        if key == "rows":
            return True, [f"✓ 1re ligne enregistrée (la cible), hauteur d'une ligne : {c.relist_step} px."]
        if key == "sell_button":
            return True, ["✓ Position enregistrée : la cible montre où l'outil cliquera."]
        if key == "modify_button":
            if core.detect_panel(c) == "relist":
                return True, ["✓ Bouton « Modifier » vu sous la cible."]
            return None, ["– Bouton pas visible maintenant : sélectionne une de TES ventes, puis « Relire »."]
        if key == "name":
            if core.item_key(core.grab_name(c)) is not None:
                return True, ["✓ Nom de l'objet lisible."]
            return False, ["✗ Rien de lisible dans la zone du nom (objet sélectionné ?)."]
        sr = self.engine.read_only()
        if key == "table":
            got = [(l, r.value) for l, r in sorted(sr.prices.items()) if r and r.value is not None]
            if got:
                return True, [f"✓ {len(got)} prix lus : " + ", ".join(f"lot {l} = {fmt(v)}" for l, v in got)] + warn
            return False, ["✗ Aucun prix lu : sélectionne un objet de ton inventaire, ou refais la zone."]
        if key == "qty":
            if sr.selected:
                return True, [f"✓ Quantité lue : {sr.selected}."] + warn
            return False, ["✗ Quantité illisible : objet sélectionné ? Sinon refais la zone."] + warn
        if key == "avg":
            if sr.avg:
                return True, [f"✓ Prix moyen lu : {fmt(sr.avg)} par objet."] + warn
            return False, ["✗ Prix moyen illisible : objet sélectionné ? Sinon refais la zone."] + warn
        if key == "count":
            if sr.listed:
                return True, [f"✓ Compteur lu : {sr.listed[0]}/{sr.listed[1]} lots en vente."] + warn
            return False, ["✗ Compteur illisible : refais la zone (toute la ligne, avec de la marge)."] + warn
        if key in ("price_field", "mine"):
            if sr.mine:
                return True, [f"✓ Prix du lot lu : {fmt(sr.mine)}."]
            return None, ["– Champ vide ou illisible pour l'instant (normal sans objet sélectionné). "
                          "Sélectionne une de tes ventes, puis « Relire »."]
        return None, ["Position enregistrée."]

    def _wiz_zone_show(self, res: dict):
        w = getattr(self, "_wiz", None)
        if w is None or not w.winfo_exists() or self._wiz_i >= len(self.WIZ_STEPS) \
                or self.WIZ_STEPS[self._wiz_i][0] != res["key"]:
            return
        img = res.get("img")
        if img is not None:
            scale = min(3.0, 580 / img.width, 170 / img.height)    # petites zones agrandies
            size = (max(1, int(img.width * scale)), max(1, int(img.height * scale)))
            self._wiz_img = ctk.CTkImage(light_image=img, dark_image=img, size=size)
            self._wiz_cap.configure(image=self._wiz_img, text="")
        else:
            self._wiz_img = None
            self._wiz_cap.configure(image=None, text="")
        col = {True: P["green"], False: P["red"]}.get(res["ok"], P["orange"])
        self._wiz_verdict.configure(text="\n".join(res["lines"]), text_color=col)

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
            self._remember_game_window()
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
        self._remember_game_window()
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
        self._remember_game_window()
        self._sync_vars_from_cfg()
        self._refresh_status()

    # ---------------------------------------------------------------- misc
    def _on_pause_key(self):
        """Touche d'arrêt (Ctrl+Alt+P) : arrête le parcours en cours (Tout vendre, Toute la liste),
        comme « Arrêter ». Il n'y a plus de pause : hors parcours, elle ne fait rien."""
        if self._loop is not None:
            self._stop_loop()
        else:
            self._hud_message("Aucun parcours en cours", f"{self.cfg.hotkeys['pause'].upper()} arrête "
                              "Tout vendre / Toute la liste", MUTED, 1800)

    CHIP_GREEN, CHIP_ORANGE, CHIP_RED, CHIP_GREY = "green", "orange", "red", "grey"   # dofus_style.CHIP

    def _set_hdv(self, state: Optional[str]):
        if state != self.hdv_state:
            self.hdv_state = state
            if state == "ok":
                self._remember_game_window()     # la calibration marche avec cette fenêtre du jeu
            self._refresh_status()

    def _chip_values(self) -> dict:
        """Texte et couleur de chaque pastille de la barre d'état."""
        c = self.cfg
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
            "state": ("■ Arrêter le parcours", self.CHIP_ORANGE) if self._loop is not None
                     else ("● Actif", self.CHIP_GREEN),
            "profile": (f"Profil : {c.profile}", self.CHIP_GREY),
            "calib": ("Calibration OK" if calib else "Calibration à faire",
                      self.CHIP_GREEN if calib else self.CHIP_RED),
            "hdv": hdv,
        }

    def _refresh_status(self):
        c = self.cfg
        for key, (text, color) in self._chip_values().items():
            bg, fg = style.CHIP[color]
            if key == "profile":                     # couleur du profil
                bg, fg = self._profile_color(), style.ON_PROFILE
            self.chips[key].configure(text=text, fg_color=bg, text_color=fg)
        self._refresh_hud()
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
        self._tray_update()

    # ---- style : classique ou verre
    def _glass_on(self) -> bool:
        return self.cfg.ui_style == "glass" and style.glass_supported() and style.is_dark()

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
        self._tray_update()
        self._refresh_status()               # pastille d'état : « ■ Arrêter le parcours »

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
                self.loop_pb.set(0)
            self._pb_set(self.loop_pb, lp["frac"])
        if not self.loop_bar.winfo_manager():
            self.loop_bar.pack(side="right", padx=(8, 0))
        self._refresh_hud()

    def _pb_set(self, pb, frac: float):
        """Barre de progression : glisse vers la nouvelle valeur au lieu de sauter."""
        if not ANIMATE["on"]:
            pb.set(frac)
            return
        pb._dph_target = frac
        if getattr(pb, "_dph_anim", None):
            return

        def step():
            try:
                cur, tgt = pb.get(), pb._dph_target
                nxt = cur + (tgt - cur) * 0.25
                if abs(tgt - nxt) < 0.004:
                    pb.set(tgt)
                    pb._dph_anim = None
                    return
                pb.set(nxt)
                pb._dph_anim = pb.after(16, step)
            except (tk.TclError, AttributeError):
                pb._dph_anim = None
        pb._dph_anim = pb.after(16, step)

    def _stop_loop(self):
        if self._loop is not None:
            self.engine.stop_requested = True
            self.loop_stop.configure(text="Arrêt…", state="disabled")
            self._log("[Boucle] Arrêt demandé : fin après la ligne en cours.", "WARN")
            self._refresh_hud()

    def _loop_end(self, res: Optional[core.Result]):
        lp, self._loop = self._loop, None
        self.loop_pb.stop()
        self.loop_bar.pack_forget()
        self._refresh_status()
        self._tray_update()
        if lp is not None and res is not None and res.level == "ok":
            core.beep("done", self.cfg)
        if lp is None or not self.cfg.notify or time.time() - lp["t0"] < LONG_LOOP_S:
            return
        try:
            game = core.game_has_focus(self.cfg)
            mine = self.focus_displayof() is not None
        except Exception:
            game, mine = True, True
        if game or mine:
            return                       # le résultat est déjà visible (HUD / fenêtre)
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
                  "pause": "Arrêter le parcours", "cheatsheet": "Fermer cet aide-mémoire"}

    def _toggle_cheatsheet(self, ms: int = 10000):
        w = self._cheat
        if w is not None and w.winfo_exists():
            w.destroy()
            self._cheat = None
            return
        t, card = rounded_popup(self)
        head = ctk.CTkFrame(card, fg_color="transparent")
        head.pack(fill="x", padx=(14, 8), pady=(8, 4))
        ctk.CTkLabel(head, text="◆  Raccourcis", text_color=P["gold"], anchor="w",
                     font=ctk.CTkFont(size=14, weight="bold")).pack(side="left")
        ctk.CTkButton(head, text="✕", width=24, height=22, fg_color="transparent", hover_color=P["btn2_hover"],
                      text_color=MUTED, command=lambda: self._cheat_close(t)).pack(side="right")
        ctk.CTkLabel(head, text="⠿ déplacer", text_color=MUTED, font=ctk.CTkFont(size=11)
                     ).pack(side="right", padx=6)
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
        pos = self.cfg.cheatsheet_pos
        try:
            ok = bool(pos) and geometry_on_screen(f"300x200+{pos[0]}+{pos[1]}", core.screen_bounds())
        except Exception:
            ok = False
        x, y = (pos[0], pos[1]) if ok else self._overlay_anchor()   # là où tu l'as laissé la dernière fois
        t.geometry(f"+{max(0, int(x))}+{max(0, int(y))}")
        self._cheat = t
        timer = {"id": t.after(ms, lambda: close_popup(t))}

        def moved(nx, ny):
            # déplacé : reste affiché jusqu'au ✕ (ou la touche), à cet endroit les prochaines fois
            if timer["id"]:
                t.after_cancel(timer["id"])
                timer["id"] = None
            self.cfg.cheatsheet_pos = [nx, ny]
            self._save_cfg()
        make_draggable(t, moved)

    def _cheat_close(self, t):
        close_popup(t)
        self._cheat = None

    def _overlay_anchor(self):
        """Où afficher l'aide-mémoire : au-dessus de l'HDV si on sait où il est."""
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
        brand(d)
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
        kw = dict(fg_color=style.CHIP["red"][0], hover_color=P["red_hover"],
                  text_color=style.CHIP["red"][1]) if danger else {}
        ctk.CTkButton(bar, text=ok, width=110, command=lambda: done(True), **kw).pack(side="right")
        ctk.CTkButton(bar, text="Annuler", width=100, fg_color=BTN2, text_color=P["text"], hover_color=BTN2_HOVER,
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

    # ---- calibration décalée (fenêtre du jeu ou écran changés depuis la calibration)
    OFF_LABELS = dict(ZONE_LABELS, price_field="Prix du lot", sell_button="Mettre en vente",
                      modify_button="Modifier", relist_row="Lignes de mes ventes")

    def _remember_game_window(self):
        try:
            rect = core.game_window_rect(self.cfg)
        except Exception:
            rect = None
        if rect and list(rect) != self.cfg.calib_window:
            self.cfg.calib_window = list(rect)
            self._save_cfg()
        if rect:
            self._hide_drift()

    def _check_calibration(self, tries: int = 0):
        """Au démarrage : écran changé (zones hors de l'écran) ou fenêtre du jeu redimensionnée
        depuis la calibration ? -> bandeau avec « Recalibrer »."""
        c = self.cfg
        if not self._calibrated():
            return
        try:
            off = core.zones_off_screen(c, core.screen_bounds())
        except Exception:
            off = []
        if off:
            names = ", ".join(dict.fromkeys(self.OFF_LABELS.get(z, z) for z in off))
            self._show_drift(f"Calibration à refaire : des zones sont hors de l'écran ({names}). Écran "
                             "débranché ou résolution changée ?")
            return
        try:
            rect = core.game_window_rect(c)
        except Exception:
            rect = None
        if rect is None:                       # jeu pas encore lancé (ou réduit) : on réessaie
            if tries < 120:
                self.after(5000, lambda: self._check_calibration(tries + 1))
            return
        why = core.calib_drift(c.calib_window, rect, bool(c.anchor_region))
        if why:
            self._show_drift(f"La calibration semble décalée : {why}.")

    def _show_drift(self, text: str):
        self.drift_lbl.configure(text="⚠  " + text)
        if not self.drift_bar.winfo_manager():
            self.drift_bar.pack(fill="x", padx=12, pady=(0, 6))
            self._log(f"[Calib] {text}", "WARN")

    def _hide_drift(self):
        if self.drift_bar.winfo_manager():
            self.drift_bar.pack_forget()

    def _ignore_drift(self):
        try:
            rect = core.game_window_rect(self.cfg)
        except Exception:
            rect = None
        if rect:
            self.cfg.calib_window = list(rect)    # nouvelle référence : plus d'alerte pour cette fenêtre
            self._save_cfg()
        self._hide_drift()

    # ---- profil automatique selon le personnage
    def _auto_profile(self) -> Optional[str]:
        """Le jeu au premier plan montre un personnage qui a un autre profil : on le prend.
        Appelé par la surveillance (thread UI) et avant chaque touche de jeu (thread de travail).
        Retourne le message à afficher, ou None."""
        c = self.cfg
        info = core.foreground_info()
        if not info or not core.is_game_window(*info, c):
            return None
        char = core.character_from_title(info[0])
        if not char:
            return None
        self._char = char
        if not c.auto_profile:
            return None
        with self._profile_lock:
            target = core.profile_for_character(char, c.character_profiles, c.profile_names())
            if not target or target == c.profile:
                return None
            c.switch_profile(target)
            c.character_profiles[char] = target
            c.save()
        return f"[Profil] « {target} » activé pour {char}."

    def _on_auto_profile(self, msg: str):
        self.profile_menu.configure(values=self.cfg.profile_names())
        self.profile_var.set(self.cfg.profile)
        self.hdv_state = None
        self._log(msg, "CAL")
        self._refresh_status()
        self._refresh_character()
        self._refresh_profile_colors()
        self._hud_message(f"Profil « {self.cfg.profile} »", self._char or "", P["cyan"])

    def _refresh_character(self):
        lbl = getattr(self, "char_lbl", None)
        if lbl is None:
            return
        c, char = self.cfg, self._char
        if not char:
            return
        linked = core.profile_for_character(char, c.character_profiles, c.profile_names())
        if linked:
            lbl.configure(text=f"Personnage : {char}  →  profil « {linked} »", text_color=P["text"])
        else:
            lbl.configure(text=f"Personnage : {char}  —  aucun profil associé", text_color=MUTED)
        if linked != c.profile:
            self.char_btn.configure(text=f"Associer à « {c.profile} »")
            if not self.char_btn.winfo_ismapped():
                self.char_btn.pack(side="right")
        else:
            self.char_btn.pack_forget()

    def _link_character(self):
        if self._char:
            self.cfg.character_profiles[self._char] = self.cfg.profile
            self._save_cfg()
            self._log(f"[Profil] « {self.cfg.profile} » associé à {self._char}.", "CAL")
            self._refresh_character()

    def _watch_game(self):
        """Toutes les 0,7 s : personnage au premier plan (profil auto) et visibilité du HUD."""
        try:
            info = core.foreground_info()
            self._game_fg = bool(info and core.is_game_window(*info, self.cfg))
            if self._game_fg:
                before = self._char
                if not self.engine._lock.locked() and self._loop is None:
                    msg = self._auto_profile()
                    if msg:
                        self._on_auto_profile(msg)
                else:
                    self._char = core.character_from_title(info[0]) or self._char
                if self._char != before:
                    self._refresh_character()
            self._hud_visibility()
        except Exception:
            pass
        self.after(700, self._watch_game)

    # ---- HUD discret par-dessus le jeu (les clics le traversent)
    def _toggle_hud(self):
        self.cfg.hud = not self.cfg.hud
        self.v["hud"].set(self.cfg.hud)
        self._apply_hud()
        self._save_cfg()

    def _apply_hud(self):
        w = self._hud
        if self.cfg.hud:
            if w is None or not w.winfo_exists():
                self._hud_create()
            self._refresh_hud()
            self._hud_visibility()
        elif w is not None:
            if w.winfo_exists():
                w.destroy()
            self._hud = None
            self._hud_moving = False

    def _hud_create(self):
        c = self.cfg
        size = HUD_SIZES.get(c.hud_size, HUD_SIZES["normal"])[1]
        t, card = rounded_popup(self, radius=10, alpha=min(1.0, max(0.5, c.hud_opacity)))
        self._hud, self._hud_card = t, card
        row = ctk.CTkFrame(card, fg_color="transparent")
        row.pack(padx=(10, 14), pady=max(3, size // 2 - 1))
        ctk.CTkLabel(row, text="", image=self._logo_img_small()).pack(side="left", padx=(0, 8))
        self._hud_profile = ctk.CTkLabel(row, text="", corner_radius=8, height=size + 6, text_color=style.ON_PROFILE,
                                         font=ctk.CTkFont(size=size - 1, weight="bold"))
        self._hud_state = ctk.CTkLabel(row, text="", font=ctk.CTkFont(size=size, weight="bold"))
        self._hud_state.pack(side="left")
        self._hud_head = ctk.CTkLabel(row, text="", text_color=P["text"], font=ctk.CTkFont(size=size, weight="bold"))
        self._hud_head.pack(side="left", padx=(10, 0))
        self._hud_sub = ctk.CTkLabel(row, text="", font=ctk.CTkFont(size=size))
        self._hud_sub.pack(side="left", padx=(8, 0))
        self._hud_hist = ctk.CTkFrame(card, fg_color="transparent")       # derniers prix (option)
        self._hud_hist_lbls = [ctk.CTkLabel(self._hud_hist, text="", anchor="w", height=size + 4,
                                            font=ctk.CTkFont(family=style.MONO, size=size - 1))
                               for _ in range(HUD_HISTORY_N)]
        pos = self.cfg.hud_pos
        try:
            ok = bool(pos) and geometry_on_screen(f"300x40+{pos[0]}+{pos[1]}", core.screen_bounds())
        except Exception:
            ok = False
        if ok:
            x, y = pos
        else:                                   # en haut, au centre de l'écran principal
            x, y = self.winfo_screenwidth() // 2 - 170, 8
        t.geometry(f"+{int(x)}+{int(y)}")
        make_draggable(t, self._hud_dropped)
        t.after(150, lambda: t.winfo_exists() and style.set_click_through(t, not self._hud_moving))
        t.withdraw()

    def _logo_img_small(self):
        if getattr(self, "_logo16", None) is None:
            img = dofus_logo.logo_image(32)
            self._logo16 = ctk.CTkImage(light_image=img, dark_image=img, size=(16, 16))
        return self._logo16

    def _refresh_hud(self):
        w = self._hud
        if w is None or not w.winfo_exists():
            return
        c = self.cfg
        state = "loop" if self._loop is not None else "calib" if not self._calibrated() else "ok"
        color, text = TRAY_STATES[state]
        chip = {"ok": "green", "loop": "grey", "calib": "red"}[state]
        if len(c.profile_names()) > 1:          # multi-compte : profil actif dans sa couleur
            self._hud_profile.configure(text=f" {c.profile} ", fg_color=self._profile_color())
            if not self._hud_profile.winfo_ismapped():
                self._hud_profile.pack(side="left", padx=(0, 8), before=self._hud_state)
        else:
            self._hud_profile.pack_forget()
        show_state = c.hud_content != "action" or self._hud_moving
        show_action = c.hud_content != "state" or self._loop is not None or self._hud_moving
        self._hud_state.configure(text=f"● {text}" if show_state else "●",
                                  text_color=P["cyan"] if state == "loop" else style.CHIP[chip][1])
        lp = self._loop
        if self._hud_moving:
            head, sub, col = "Glisse-moi où tu veux", "(lâche pour terminer)", MUTED
        elif lp is not None:                    # parcours : progression + comment l'arrêter
            stop = "arrêt demandé…" if self.engine.stop_requested else f"{c.hotkeys['pause'].upper()} = arrêter"
            head, sub, col = self.LOOP_NAMES.get(lp["kind"], ""), f"{lp['text']} · {stop}", P["text"]
        else:
            note = self._hud_note
            head, sub, col = note[:3] if note and time.time() < note[3] else self.last_action
            if head.startswith("En attente"):
                head = ""
        self._hud_head.configure(text=head if show_action else "")
        self._hud_sub.configure(text=sub if show_action else "", text_color=col)
        self._refresh_hud_history()

    def _refresh_hud_history(self):
        """Sous la ligne du HUD : les derniers prix traités (option « 3 derniers prix »)."""
        lines = self.hud_recent if self.cfg.hud_history and not self._hud_moving else []
        hist = self._hud_hist
        for i, lbl in enumerate(self._hud_hist_lbls):
            if i < len(lines):
                text, level, hhmm = lines[i]
                lbl.configure(text=f"{hhmm}  {text}", text_color=LEVEL_COLORS.get(level, MUTED) if i == 0 else MUTED)
                if not lbl.winfo_ismapped():
                    lbl.pack(anchor="w", fill="x")
            else:
                lbl.pack_forget()
        if lines and not hist.winfo_ismapped():
            hist.pack(anchor="w", fill="x", padx=(34, 14), pady=(0, 6))
        elif not lines:
            hist.pack_forget()

    def _push_history(self, res, refresh: bool = True):
        line = hud_history_line(res)
        if line is None:
            return
        self.hud_recent = ([line] + self.hud_recent)[:HUD_HISTORY_N]
        if refresh:
            self._refresh_hud()

    def _set_hud_history(self):
        self.cfg.hud_history = bool(self.hud_hist_var.get())
        self._save_cfg()
        self._refresh_hud()

    def _hud_rebuild(self):
        """Taille / contenu changés : le HUD est recréé."""
        w = self._hud
        if w is not None and w.winfo_exists():
            w.destroy()
        self._hud = None
        self._apply_hud()

    def _set_hud_size(self, label: str):
        self.cfg.hud_size = next((k for k, (lbl, _s) in HUD_SIZES.items() if lbl == label), "normal")
        self._save_cfg()
        self._hud_rebuild()

    def _set_hud_content(self, label: str):
        self.cfg.hud_content = next((k for k, lbl in HUD_CONTENTS.items() if lbl == label), "both")
        self._save_cfg()
        self._refresh_hud()

    def _set_hud_opacity(self, value: float):
        self.cfg.hud_opacity = round(float(value), 2)
        self.hud_op_lbl.configure(text=f"{self.cfg.hud_opacity:.0%}")
        w = self._hud
        if w is not None and w.winfo_exists():
            try:
                w.attributes("-alpha", self.cfg.hud_opacity)
            except tk.TclError:
                pass
        if getattr(self, "_hud_op_save", None):
            self.after_cancel(self._hud_op_save)
        self._hud_op_save = self.after(500, self._save_cfg)

    # ---- couleur du profil
    def _profile_color(self, name: str = None) -> str:
        return style.profile_color(name or self.cfg.profile, self.cfg.profile_colors)

    def _set_profile_color(self, key: str):
        self.cfg.profile_colors[self.cfg.profile] = key
        self._save_cfg()
        self._refresh_profile_colors()
        self._refresh_status()

    def _refresh_profile_colors(self):
        btns = getattr(self, "pcolor_btns", None)
        if not btns:
            return
        current = self._profile_color()
        for key, sw in btns.items():
            sw.configure(border_color=P["text"] if style.PROFILE_COLORS[key][1] == current else P["card"])

    def _hud_flash(self, color: str, ms: int = 1800):
        """Nouveau résultat : le bord du HUD prend sa couleur un instant."""
        w = self._hud
        if w is None or not w.winfo_exists() or self._hud_moving:
            return
        self._hud_card.configure(border_color=color, border_width=2)
        if getattr(self, "_hud_flash_after", None):
            self.after_cancel(self._hud_flash_after)

        def back():
            self._hud_flash_after = None
            if self._hud is not None and self._hud.winfo_exists() and not self._hud_moving:
                self._hud_card.configure(border_color=P["border"], border_width=1)
        self._hud_flash_after = self.after(ms, back)

    def _hud_message(self, head: str, sub: str, color: str, ms: int = 2500):
        """Message temporaire dans le HUD (ex. changement de profil), puis la dernière action."""
        self._hud_note = (head, sub, color, time.time() + ms / 1000)
        self._refresh_hud()
        self._hud_flash(color, ms)
        self.after(ms + 50, self._refresh_hud)

    def _hud_visibility(self):
        w = self._hud
        if w is None or not w.winfo_exists():
            return
        want = self.cfg.hud and (self._game_fg or self._hud_moving)
        shown = w.winfo_ismapped()
        if want and not shown:
            w.deiconify()
            w.attributes("-topmost", True)
            w.after(50, lambda: w.winfo_exists() and style.set_click_through(w, not self._hud_moving))
        elif not want and shown:
            w.withdraw()

    def _hud_move(self):
        """« Déplacer » : le HUD devient cliquable le temps de le poser ailleurs."""
        if not self.cfg.hud:
            self._toggle_hud()
        w = self._hud
        if w is None or not w.winfo_exists():
            return
        self._hud_moving = True
        self._hud_card.configure(border_color=P["accent"], border_width=2)
        style.set_click_through(w, False)
        self._refresh_hud()
        self._hud_visibility()
        self.hud_move_btn.configure(text="Glisse le HUD…", state="disabled")
        self._hud_move_after = self.after(30000, self._hud_move_end)    # oublié : fin au bout de 30 s

    def _hud_dropped(self, x: int, y: int):
        self.cfg.hud_pos = [x, y]
        self._save_cfg()
        if self._hud_moving:
            self._hud_move_end()

    def _hud_move_end(self):
        if getattr(self, "_hud_move_after", None):
            self.after_cancel(self._hud_move_after)
            self._hud_move_after = None
        self._hud_moving = False
        w = self._hud
        if w is not None and w.winfo_exists():
            self._hud_card.configure(border_color=P["border"], border_width=1)
            style.set_click_through(w, True)
        self.hud_move_btn.configure(text="Déplacer", state="normal")
        self._refresh_hud()
        self._hud_visibility()

    # ---- visite guidée (1er lancement, ou bouton « Visite guidée »)
    def _tour_start(self, first: bool = False):
        if self._tour is not None:
            return
        self._show_main()
        self._tour = {"i": 0, "first": first, "steps": tour_steps(self.cfg.hotkeys), "win": None, "ring": None,
                      "geo": None}
        self._tour_show(0)
        self._tour_watch()

    def _tour_target(self, step: dict):
        """Rectangle (x, y, l, h) à l'écran du widget visé, s'il est affiché dans la fenêtre."""
        for name in step["targets"]:
            w = getattr(self, name, None)
            try:
                if w is None or not w.winfo_ismapped():
                    continue
                x0, y0 = w.winfo_rootx(), w.winfo_rooty()
                x1, y1 = x0 + w.winfo_width(), y0 + w.winfo_height()
                p = w.master                       # partie visible : coupée par les cadres qui défilent
                while p is not None:
                    px, py = p.winfo_rootx(), p.winfo_rooty()
                    x0, y0 = max(x0, px), max(y0, py)
                    x1, y1 = min(x1, px + p.winfo_width()), min(y1, py + p.winfo_height())
                    p = None if p is self else p.master
            except tk.TclError:
                continue
            if x1 - x0 > 4 and y1 - y0 > 8:
                return x0, y0, x1 - x0, y1 - y0
        return None

    def _tour_clear(self):
        t = self._tour
        for key in ("win", "ring"):
            w = t.get(key) if t else None
            if w is not None:
                try:
                    w.destroy()
                except tk.TclError:
                    pass
                t[key] = None

    def _tour_show(self, i: int):
        t = self._tour
        if t is None:
            return
        self._tour_clear()
        t["i"] = i
        step, n = t["steps"][i], len(t["steps"])
        try:
            self.tabs.set(step["tab"])
        except Exception:
            pass
        win, card = rounded_popup(self, radius=12, alpha=1.0, border=P["accent"])
        t["win"] = win
        ctk.CTkLabel(card, text=f"Visite guidée · {i + 1}/{n}", text_color=MUTED,
                     font=ctk.CTkFont(size=11)).pack(anchor="w", padx=16, pady=(12, 0))
        ctk.CTkLabel(card, text=step["title"], font=ctk.CTkFont(size=15, weight="bold"), anchor="w"
                     ).pack(anchor="w", padx=16)
        ctk.CTkLabel(card, text=step["text"], wraplength=330, justify="left", anchor="w"
                     ).pack(anchor="w", fill="x", padx=16, pady=(4, 10))
        bar = ctk.CTkFrame(card, fg_color="transparent")
        bar.pack(fill="x", padx=12, pady=(0, 12))
        last = i == n - 1
        if not last:
            ctk.CTkButton(bar, text="Passer", width=70, height=28, fg_color="transparent", text_color=MUTED,
                          hover_color=BTN2, command=self._tour_end).pack(side="left")
        ctk.CTkButton(bar, text="Terminer" if last else "Suivant →", width=100, height=28,
                      command=self._tour_end if last else lambda: self._tour_show(i + 1)).pack(side="right")
        if i > 0:
            ctk.CTkButton(bar, text="← Précédent", width=100, height=28, fg_color=BTN2, text_color=P["text"],
                          hover_color=BTN2_HOVER, command=lambda: self._tour_show(i - 1)).pack(side="right", padx=6)
        self.after(120, self._tour_place)          # onglet changé : attendre qu'il soit dessiné

    def _tour_place(self):
        t = self._tour
        if t is None or t["win"] is None:
            return
        win = t["win"]
        try:
            self.update_idletasks()
            target = self._tour_target(t["steps"][t["i"]])
            mx, my = self.winfo_rootx(), self.winfo_rooty()
            area = (mx, my, mx + self.winfo_width(), my + self.winfo_height())
            x, y = tour_place(target, (win.winfo_reqwidth(), win.winfo_reqheight()), area)
            win.geometry(f"+{int(x)}+{int(y)}")
            win.lift()
        except tk.TclError:
            return
        ring = t.get("ring")
        if target is None:
            if ring is not None:
                ring.withdraw()
            return
        pad = 5
        tx, ty, tw, th = target
        tw, th = tw + 2 * pad, th + 2 * pad
        if ring is None:                            # cadre autour du widget visé (les clics le traversent)
            ring = tk.Toplevel(self)
            ring.overrideredirect(True)
            ring.attributes("-topmost", True)
            ring.configure(bg=POPUP_KEY)
            try:
                ring.attributes("-transparentcolor", POPUP_KEY)
            except tk.TclError:
                pass
            cv = tk.Canvas(ring, bg=POPUP_KEY, highlightthickness=0, bd=0)
            cv.pack(fill="both", expand=True)
            ring._cv = cv
            t["ring"] = ring
            ring.after(60, lambda: ring.winfo_exists() and style.set_click_through(ring, True))
        ring.geometry(f"{tw}x{th}+{tx - pad}+{ty - pad}")
        ring.deiconify()
        cv = ring._cv
        cv.delete("all")
        cv.create_rectangle(2, 2, tw - 2, th - 2, outline=P["accent"], width=3)
        win.lift()

    def _tour_watch(self):
        """Pendant la visite : la bulle suit la fenêtre (déplacée, redimensionnée, cachée)."""
        t = self._tour
        if t is None:
            return
        try:
            hidden = self.state() in ("withdrawn", "iconic")
            geo = self.geometry()
        except tk.TclError:
            return
        for key in ("win", "ring"):
            w = t.get(key)
            if w is not None and hidden and w.winfo_ismapped():
                w.withdraw()
        if hidden:
            t["geo"] = None
        elif geo != t["geo"]:
            t["geo"] = geo
            if t["win"] is not None:
                t["win"].deiconify()
            self._tour_place()
        self.after(300, self._tour_watch)

    def _tour_end(self):
        t = self._tour
        if t is None:
            return
        self._tour_clear()
        self._tour = None
        try:
            self.tabs.set("Accueil")
        except Exception:
            pass
        if not self.cfg.tour_done:
            self.cfg.tour_done = True
            self._save_cfg()
        if t["first"] and not self._calibrated():
            self.after(300, self._first_launch)    # puis : calibration automatique proposée

    # ---- « Quoi de neuf » après une mise à jour
    def _whats_new(self, force: bool = False):
        c, cur = self.cfg, core.app_version()
        if core.parse_version(cur) is None:
            return                                 # version de développement
        if force:
            items = whats_new("", cur)[-1:]
        else:
            if c.last_seen_version == cur:
                return
            # 1re installation (rien de calibré) : rien à annoncer
            items = whats_new(c.last_seen_version, cur) if (c.last_seen_version or self._calibrated()) else []
            c.last_seen_version = cur
            self._save_cfg()
        if not items:
            return
        w = ctk.CTkToplevel(self)
        brand(w)
        w.title("Quoi de neuf")
        w.resizable(False, False)
        w.attributes("-topmost", True)
        w.transient(self)
        hr = ctk.CTkFrame(w, fg_color="transparent")
        hr.pack(fill="x", padx=18, pady=(16, 4))
        ctk.CTkLabel(hr, text="", image=self._logo_img).pack(side="left", padx=(0, 10))
        ctk.CTkLabel(hr, text=f"Quoi de neuf dans la {cur}", font=ctk.CTkFont(size=17, weight="bold")
                     ).pack(side="left")
        keys = {"pause": c.hotkeys["pause"].upper(), "hud": c.hotkeys["hud"].upper(),
                "window": c.hotkeys["toggle_window"].upper()}
        for version, lines in reversed(items):
            if len(items) > 1:
                ctk.CTkLabel(w, text=f"v{version}", text_color=P["gold"], anchor="w",
                             font=ctk.CTkFont(size=13, weight="bold")).pack(fill="x", padx=18, pady=(10, 2))
            for line in lines:
                r = ctk.CTkFrame(w, fg_color="transparent")
                r.pack(fill="x", padx=18, pady=2)
                ctk.CTkLabel(r, text="•", text_color=P["accent"], width=14, anchor="n").pack(side="left", anchor="n")
                ctk.CTkLabel(r, text=line.format(**keys), anchor="w", justify="left", wraplength=470
                             ).pack(side="left", fill="x")
        bar = ctk.CTkFrame(w, fg_color="transparent")
        bar.pack(fill="x", padx=18, pady=(16, 16))
        ctk.CTkButton(bar, text="OK", width=100, command=w.destroy).pack(side="right")
        ctk.CTkButton(bar, text="Page de la version", width=150, fg_color=BTN2, text_color=P["text"],
                      hover_color=BTN2_HOVER, command=lambda: self._open_url(
                          f"https://github.com/{core.GITHUB_REPO}/releases/tag/v{cur.lstrip('v')}")
                      ).pack(side="right", padx=8)
        w.bind("<Escape>", lambda _e: w.destroy())
        w.update_idletasks()
        x = self.winfo_rootx() + (self.winfo_width() - w.winfo_reqwidth()) // 2
        y = self.winfo_rooty() + (self.winfo_height() - w.winfo_reqheight()) // 3
        w.geometry(f"+{max(0, x)}+{max(0, y)}")

    # ---- sauvegarde / restauration
    def _backup(self):
        from tkinter import filedialog
        path = filedialog.asksaveasfilename(
            parent=self, title="Sauvegarder les réglages", defaultextension=".zip",
            initialfile=f"DofusPriceHelper-sauvegarde-{time.strftime('%Y-%m-%d')}.zip",
            filetypes=[("Sauvegarde Dofus Price Helper", "*.zip")])
        if not path:
            return
        self._apply_settings()                     # réglages en cours d'édition compris
        try:
            dofus_backup.make_backup(path)
        except (OSError, ValueError) as e:
            self._log(f"[Sauvegarde] Impossible : {e}", "ERROR")
            return
        self._log(f"[Sauvegarde] Créée : {path}", "OK")
        dofus_update.reveal(path)

    def _restore(self):
        from tkinter import filedialog
        if self.engine._lock.locked() or self._loop is not None:
            self._log("[Sauvegarde] Une action est en cours : restaure quand elle est finie.", "WARN")
            return
        path = filedialog.askopenfilename(parent=self, title="Restaurer une sauvegarde",
                                          filetypes=[("Sauvegarde Dofus Price Helper", "*.zip")])
        if not path:
            return
        try:
            info = dofus_backup.read_backup(path)
        except ValueError as e:
            self._log(f"[Sauvegarde] {e}.", "ERROR")
            return
        profiles = ", ".join(info["profiles"][:6]) + ("…" if len(info["profiles"]) > 6 else "")
        if not self._confirm("Restaurer la sauvegarde",
                             f"Sauvegarde du {info['date']} (version {info['version']}).\nProfils : {profiles}.\n\n"
                             "Tes réglages, profils et calibration actuels seront remplacés. Ils sont d'abord "
                             "gardés dans le dossier « sauvegardes ». L'outil redémarre ensuite.",
                             ok="Restaurer", danger=True):
            return
        try:
            keep = dofus_backup.restore_backup(path)
        except (OSError, ValueError) as e:
            self._log(f"[Sauvegarde] Restauration impossible : {e}", "ERROR")
            return
        core.log_line(f"[Sauvegarde] Restaurée depuis {path} ; anciens réglages dans {keep}", "OK")
        self._restored = True                      # ne pas réécrire la config en fermant
        self.restart_requested = True
        self._on_close()

    # ---- zone de notification
    def _tray_update(self):
        if self._loop is not None:
            state = "loop"
        elif not self._calibrated():
            state = "calib"
        else:
            state = "ok"
        multi = len(self.cfg.profile_names()) > 1     # couleur du profil : utile seulement s'il y en a plusieurs
        self.tray.update(state, ring=self._profile_color() if multi else None,
                         profile=self.cfg.profile if multi else "")

    def _apply_tray(self):
        if self.cfg.tray:
            self.tray.start()
            self._tray_update()
        else:
            self.tray.stop()

    def _show_main(self):
        self.deiconify()
        self.lift()
        self._apply_topmost()
        try:
            self.focus_force()
        except tk.TclError:
            pass

    def _toggle_window(self):
        """Touche « afficher / cacher » : depuis le jeu, sans passer par la barre des tâches."""
        try:
            hidden = self.state() in ("withdrawn", "iconic")
        except tk.TclError:
            return
        if hidden:
            self._show_main()
        elif self.tray.icon is not None:
            self.withdraw()                        # l'icône près de l'horloge permet aussi de la rouvrir
        else:
            self.iconify()

    def _on_tray(self, action: str):
        if action == "open":
            self._show_main()
        elif action == "cheatsheet":
            self._toggle_cheatsheet()
        elif action == "stop":
            self._stop_loop()
        elif action == "hud":
            self._toggle_hud()
        elif action == "quit":
            self._on_close()

    def _on_unmap(self, e):
        """Fenêtre réduite + option « réduire dans la zone de notification » : on la cache."""
        if e.widget is not self or not self.cfg.tray_minimize or self.tray.icon is None:
            return

        def hide():
            try:
                if self.state() == "iconic":
                    self.withdraw()
                    if not self.tray.told:
                        self.tray.told = True
                        self.tray.notify("L'outil continue ici. Clic sur l'icône pour le rouvrir.")
            except tk.TclError:
                pass
        self.after(50, hide)

    # ---- raccourcis de la fenêtre de l'outil
    def _on_ctrl_key(self, e):
        idx = tab_index_for_key(e.keycode, e.keysym)
        if idx is not None:
            self.tabs.set(TAB_NAMES[idx])
            return "break"
        if e.keycode == 76 or e.keysym.lower() == "l":      # Ctrl+L
            self._clear_log()
            return "break"
        return None

    def _on_escape(self, _e=None):
        if self._tour is not None:
            self._tour_end()
            return
        for name in ("_cheat", "_summary_win"):
            w = getattr(self, name, None)
            if w is not None and w.winfo_exists():
                if name == "_summary_win":
                    w.destroy()
                else:
                    close_popup(w)
        self._cheat = None

    def _on_close(self):
        self.closing = True
        self.tray.stop()
        try:
            self.cfg.window_geometry = "zoomed" if self.state() == "zoomed" else self.geometry()
        except tk.TclError:
            pass
        if not getattr(self, "_restored", False):      # réglages restaurés : ne pas les écraser
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
    # --relance : l'ancien exemplaire (changement de thème) finit de se fermer : on l'attend.
    if not dofus_update.single_instance(wait=10.0 if RELAUNCH_FLAG in sys.argv else 0.0):
        raise SystemExit(0)            # déjà ouvert : sa fenêtre est ramenée devant
    try:
        core.setup_file_log()
    except OSError:
        pass   # dossier non accessible : l'outil marche sans fichier journal
    app = App()
    app.mainloop()
    app.tray.stop()
    if app.restart_requested:            # thème / couleur changés : l'outil se relance
        import subprocess
        subprocess.Popen(relaunch_command(), close_fds=True)
    import logging
    logging.shutdown()
    # Fin garantie : un fil resté actif (icône, bibliothèque) ne doit pas garder l'outil
    # ouvert sans fenêtre (et bloquer la relance ou une mise à jour).
    os._exit(0)
