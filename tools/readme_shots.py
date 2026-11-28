#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Captures d'écran du README, générées avec des données d'exemple
----------------------------------------------------------------
Lance la vraie interface avec une configuration de démonstration (dossier temporaire : tes
réglages, ta calibration et ton historique ne sont ni lus ni modifiés), la remplit avec des
ventes d'exemple, puis capture les fenêtres. Le décor « HDV » vient de tests/fixtures.

Sans danger pendant que tu joues :
- aucun raccourci enregistré, clavier et souris neutralisés (rien n'est envoyé au jeu) ;
- les fenêtres restent sous les autres et ne prennent jamais le focus.

Utilisation (Windows) :
    python tools/readme_shots.py                         # tout, style « night », dans docs/img
    python tools/readme_shots.py --look amber            # captures principales dans un autre style
    python tools/readme_shots.py --styles night,light    # styles de la mosaïque (« all » = tous)
    python tools/readme_shots.py --out C:/tmp/shots

Images produites :
    hud.png          HUD par-dessus l'HDV (image principale du README)
    resume.png       résumé de fin de « Toute la liste » (Ctrl+F3)
    accueil.png      fenêtre principale : activité, dernière lecture, journal
    prix.png         onglet Prix : réglages et aperçu du prix calculé
    calibration.png  zones placées par la calibration automatique, sur l'HDV
    styles.png       mosaïque des styles (une capture de l'Accueil par style)
"""
from __future__ import annotations

import argparse
import ctypes
import ctypes.wintypes as W
import random
import subprocess
import sys
import tempfile
import time
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
FX = ROOT / "tests" / "fixtures"
BACKDROP = FX / "hdv_echelles" / "2560x1440_90.png"   # HDV, une de tes ventes sélectionnée (lot 1 à 1 989)
NAMES = sorted(FX.glob("nom_*.png"))                   # noms d'objets réels (résumé Ctrl+F3)

WINDOW_SIZE = (1120, 780)     # taille logique de la fenêtre principale
# Styles : chaque ambiance de dofus_style.AMBIENCES (thème sombre), plus « light » (thème clair).
ACCENT_FOR = {"night": "blue", "amber": "amber", "forest": "green", "ocean": "cyan"}   # sinon : bleu
DEFAULT_STYLES = ("night", "amber", "forest", "ocean", "light")


def looks() -> dict:
    """style -> (thème, accent, ambiance, titre), comme dans Options › Apparence."""
    import dofus_style as style
    out = {k: ("dark", ACCENT_FOR.get(k, "blue"), k, v[0]) for k, v in style.AMBIENCES.items()}
    out["light"] = ("light", "violet", "night", "Clair")
    return out

u32 = ctypes.windll.user32
gdi = ctypes.windll.gdi32


# =====================================================================================
# Fenêtres : jamais au premier plan, capturées même cachées sous le jeu
# =====================================================================================
HWND_BOTTOM = 1
SWP_NOSIZE, SWP_NOMOVE, SWP_NOACTIVATE = 0x1, 0x2, 0x10
SW_SHOWNOACTIVATE = 4
WS_EX_NOACTIVATE = 0x08000000
GWL_EXSTYLE = -20


def _hwnd(win) -> int:
    return int(win.wm_frame(), 16)


def send_to_back(win) -> None:
    try:
        u32.SetWindowPos(_hwnd(win), HWND_BOTTOM, 0, 0, 0, 0, SWP_NOSIZE | SWP_NOMOVE | SWP_NOACTIVATE)
    except Exception:
        pass


def show_quietly(win) -> None:
    """Affiche la fenêtre SOUS toutes les autres, sans l'activer (le jeu garde le focus)."""
    win.update_idletasks()
    if win.winfo_width() <= 1:                 # née cachée : sa taille n'a jamais été appliquée
        win.geometry(f"{win.winfo_reqwidth()}x{win.winfo_reqheight()}")
        win.update_idletasks()
    h = _hwnd(win)
    u32.SetWindowLongW(h, GWL_EXSTYLE, u32.GetWindowLongW(h, GWL_EXSTYLE) | WS_EX_NOACTIVATE)
    u32.SetWindowPos(h, HWND_BOTTOM, 0, 0, 0, 0, SWP_NOSIZE | SWP_NOMOVE | SWP_NOACTIVATE)
    u32.ShowWindow(h, SW_SHOWNOACTIVATE)
    u32.SetWindowPos(h, HWND_BOTTOM, 0, 0, 0, 0, SWP_NOSIZE | SWP_NOMOVE | SWP_NOACTIVATE)


class _BIH(ctypes.Structure):
    _fields_ = [("biSize", W.DWORD), ("biWidth", W.LONG), ("biHeight", W.LONG), ("biPlanes", W.WORD),
                ("biBitCount", W.WORD), ("biCompression", W.DWORD), ("biSizeImage", W.DWORD),
                ("biXPelsPerMeter", W.LONG), ("biYPelsPerMeter", W.LONG), ("biClrUsed", W.DWORD),
                ("biClrImportant", W.DWORD)]


def grab(win):
    """Image (PIL, RGBA) de la fenêtre telle que Windows la compose, même recouverte.
    Recadrée sur son cadre visible (sans la bordure invisible de redimensionnement)."""
    from PIL import Image
    h = _hwnd(win)
    r = W.RECT()
    u32.GetWindowRect(h, ctypes.byref(r))
    w, hh = r.right - r.left, r.bottom - r.top
    hdc = u32.GetWindowDC(h)
    mdc = gdi.CreateCompatibleDC(hdc)
    bmp = gdi.CreateCompatibleBitmap(hdc, w, hh)
    gdi.SelectObject(mdc, bmp)
    u32.PrintWindow(h, mdc, 2)                 # PW_RENDERFULLCONTENT
    bi = _BIH(biSize=ctypes.sizeof(_BIH), biWidth=w, biHeight=-hh, biPlanes=1, biBitCount=32)
    buf = ctypes.create_string_buffer(w * hh * 4)
    gdi.GetDIBits(mdc, bmp, 0, hh, buf, ctypes.byref(bi), 0)
    gdi.DeleteObject(bmp)
    gdi.DeleteDC(mdc)
    u32.ReleaseDC(h, hdc)
    img = Image.frombuffer("RGBA", (w, hh), buf, "raw", "BGRA", 0, 1).copy()
    img.putalpha(255)
    vis = W.RECT()                             # DWMWA_EXTENDED_FRAME_BOUNDS
    if ctypes.windll.dwmapi.DwmGetWindowAttribute(h, 9, ctypes.byref(vis), ctypes.sizeof(vis)) == 0:
        img = img.crop((vis.left - r.left, vis.top - r.top, vis.right - r.left, vis.bottom - r.top))
    return img


def grab_widget(win, widget, pad: int = 0):
    """Seulement la zone d'un widget de la fenêtre (ex. le contenu d'un onglet)."""
    img = grab(win)
    vis = W.RECT()
    ctypes.windll.dwmapi.DwmGetWindowAttribute(_hwnd(win), 9, ctypes.byref(vis), ctypes.sizeof(vis))
    x, y = widget.winfo_rootx() - vis.left, widget.winfo_rooty() - vis.top
    return img.crop((max(0, x - pad), max(0, y - pad), min(img.width, x + widget.winfo_width() + pad),
                     min(img.height, y + widget.winfo_height() + pad)))


def scroll_to(widget, margin: int = 12) -> None:
    """Fait défiler l'onglet (CTkScrollableFrame) jusqu'à ce widget."""
    page = widget
    while page is not None and not hasattr(page, "_parent_canvas"):
        page = page.master
    if page is None:
        return
    page.update_idletasks()
    total = max(1, page.winfo_height())
    page._parent_canvas.yview_moveto(max(0.0, (widget.winfo_rooty() - page.winfo_rooty() - margin) / total))


# =====================================================================================
# Bac à sable : clavier, souris, fichiers et fenêtres sous contrôle
# =====================================================================================
def _fake_input_modules() -> None:
    """keyboard : tout est sans effet. pyautogui : lecture possible, aucun clic ni touche."""
    kb = types.ModuleType("keyboard")
    kb.__getattr__ = lambda name: (lambda *a, **k: None)
    sys.modules["keyboard"] = kb
    blocked = {"click", "doubleClick", "tripleClick", "rightClick", "middleClick", "moveTo", "moveRel",
               "move", "dragTo", "dragRel", "drag", "scroll", "hscroll", "vscroll", "mouseDown",
               "mouseUp", "press", "keyDown", "keyUp", "hotkey", "typewrite", "write"}
    try:
        import pyautogui as real
    except Exception:
        real = None
    pg = types.ModuleType("pyautogui")
    pg.__getattr__ = lambda name: ((lambda *a, **k: None) if name in blocked or real is None
                                   else getattr(real, name))
    sys.modules["pyautogui"] = pg


def _quiet_windows() -> None:
    """Toute fenêtre Tk naît cachée, ne passe jamais devant et n'est jamais « toujours au-dessus »."""
    import tkinter as tk
    import customtkinter as ctk

    ctk.CTk._deactivate_windows_window_header_manipulation = True       # pas de masquer / réafficher
    ctk.CTkToplevel._deactivate_windows_window_header_manipulation = True

    tk_init, top_init = tk.Tk.__init__, tk.Toplevel.__init__

    def tk_born_hidden(self, *a, **k):
        tk_init(self, *a, **k)
        tk.Wm.wm_withdraw(self)

    def top_born_hidden(self, *a, **k):
        top_init(self, *a, **k)
        tk.Wm.wm_withdraw(self)

    tk.Tk.__init__, tk.Toplevel.__init__ = tk_born_hidden, top_born_hidden

    def quiet_deiconify(self):
        self.update_idletasks()
        show_quietly(self)

    tk.Wm.deiconify = tk.Wm.wm_deiconify = quiet_deiconify

    attrs = tk.Wm.wm_attributes

    def no_topmost(self, *args, **kw):
        if len(args) >= 2 and args[0] == "-topmost":
            args = ("-topmost", False) + args[2:]
        return attrs(self, *args, **kw)

    tk.Wm.attributes = tk.Wm.wm_attributes = no_topmost

    raise_ = tk.Misc.tkraise

    def no_raise(self, *a, **k):
        if isinstance(self, (tk.Tk, tk.Toplevel)):
            return send_to_back(self)
        return raise_(self, *a, **k)

    tk.Misc.lift = tk.Misc.tkraise = no_raise
    tk.Misc.focus_force = lambda self: None


def autocal_backdrop():
    """Zones trouvées par la VRAIE calibration automatique sur la capture de l'HDV
    (coordonnées dans l'image)."""
    import cv2
    import numpy as np
    import dofus_autocal as ac
    img = cv2.imread(str(BACKDROP))
    pad = 60
    screen = np.full((img.shape[0] + 2 * pad, img.shape[1] + 2 * pad, 3), 18, np.uint8)
    screen[pad:pad + img.shape[0], pad:pad + img.shape[1]] = img
    res = ac.locate(screen, origin=(-pad, -pad))
    if not res.ok:
        raise SystemExit(f"Calibration automatique du décor impossible : {res.message}")
    return res, screen, (-pad, -pad)


# =====================================================================================
# Données d'exemple
# =====================================================================================
def demo_config(core, look: tuple):
    import dofus_autocal as ac
    theme, accent, ambience = look
    cfg = core.Config()
    res, screen, origin = autocal_backdrop()
    ac.apply(cfg, res, screen, origin)
    cfg.theme, cfg.accent, cfg.ambience = theme, accent, ambience
    cfg.tour_done = True
    cfg.check_updates = False
    cfg.last_seen_version = core.app_version()
    cfg.first_steps = ["read", "sell"]
    cfg.always_on_top = False
    cfg.sound = False
    cfg.notify = False
    cfg.animations = False                    # pas de fondu : l'image est prise d'un coup
    cfg.auto_profile = False
    cfg.relist_auto = True
    cfg.auto_paste = cfg.auto_validate = True
    cfg.undercut_mode, cfg.undercut_value = "fixed", 1.0
    cfg.rounding = "end_9"
    cfg.floor_ratio = 0.7
    cfg.relist_summary = True
    cfg.hud = True
    cfg.hud_history = True
    cfg.window_geometry = f"{WINDOW_SIZE[0]}x{WINDOW_SIZE[1]}+80+60"
    cfg.save(core.CONFIG_PATH)
    return cfg


def demo_sales(core, gui, app) -> None:
    """Une petite session de vente : actions, dernière lecture, journal, puis un Ctrl+F3."""
    import cv2
    R, SR, Rd = core.Result, core.ScreenRead, core.Reading
    read = SR(prices={1: Rd(1989, 97), 10: Rd(39999, 96), 100: Rd(159996, 94), 1000: Rd(1599960, 71)},
              selected=1, avg=2092, mine=1989, engine="chiffres")
    app._log("[Hotkeys] Prêt.", "INFO")
    app._log("[Calibration] HDV trouvé (taille ×1.00, 9/9 textes fixes retrouvés) : toutes les zones "
             "sont placées.", "CAL")
    results = [
        R(10, "ok", "[VENTE] Lot 10 | moins cher 1 662 -> 1 661 | mis en vente", SR(), 1661,
          hint="Mis en vente"),
        R(100, "ok", "[VENTE] Lot 100 | moins cher 22 294 -> 22 289 | mis en vente", SR(), 22289,
          hint="Mis en vente"),
        R(10, "ok", "[TOUT] 6×lot 10 à 6 989 | arrêt : stock épuisé", SR(), 6989, hint="6 ventes"),
        R(100, "warn", "[VENTE] Lot 100 | moins cher 8 000 -> 7 999 | SUSPECT (80/u < 50 % du prix "
                       "moyen 282/u). Copié seulement. Ré-appuie dans 3s pour forcer.", SR(), 7999,
          hint="Suspect"),
        R(10, "ok", "[MAJ] Lot 10 | ton prix 6 999 | moins cher 6 990 -> 6 989 | modifié", SR(), 6989,
          old_price=6999, hint="Modifié : 6989"),
    ]
    for res in results:
        app._on_result(res)

    rng = random.Random(7)
    imgs = [cv2.imread(str(p)) for p in NAMES]
    changes = []
    for row in range(1, 15):
        lot = rng.choice((1, 1, 10, 10, 100))
        old = rng.choice({1: (429, 599, 1189, 1989), 10: (3999, 6999, 14990),
                          100: (22294, 83199, 159996)}[lot])
        new = int(old * (1 - rng.choice((0.006, 0.012, 0.025, 0.04, 0.07)))) // 10 * 10 - 1   # finit par 9
        changes.append(core.RowChange(row=row * 3 + rng.randint(0, 2), lot=lot, old=old, new=new,
                                      modified=True, img=imgs[row % len(imgs)]))
    changes[4] = core.RowChange(row=changes[4].row, lot=10, old=6999, new=2100, modified=False,
                                note="baisse énorme : 6999 -> 2100", img=imgs[4 % len(imgs)])
    changes[9] = core.RowChange(row=changes[9].row, lot=1, old=1189, new=None, modified=False,
                                note="ton prix illisible", img=imgs[9 % len(imgs)])
    mod = sum(c.modified for c in changes)
    summary = {"seen": 48, "changed": mod, "same": 48 - len(changes), "bad": len(changes) - mod,
               "stop": "fin de la liste", "complete": True, "seconds": 31.4}
    app._on_result(R(None, "ok", f"[MAJ TOUT] 48 lignes vues (5 pages, 0 identiques sautées) : {mod} "
                                 f"modifiées, {summary['same']} déjà au bon prix | arrêt : fin de la liste "
                                 "| lecture rapide 46/48 | durée 31,4 s, 0,65 s/ligne", SR(),
                     hint=f"{mod} modifiées", changes=changes, summary=summary))

    app._show_screen(read)                    # dernière lecture : l'objet sélectionné dans l'HDV
    # heures étalées sur la session (sinon tout est à la même minute)
    now = time.time()
    for i, e in enumerate(app.activity):
        e["time"] = time.strftime("%H:%M", time.localtime(now - 60 * (3 * i + 1)))
    app._refresh_activity()
    n = len(app.log_entries)
    for i, e in enumerate(app.log_entries):
        e["t"] = time.strftime("%H:%M:%S", time.localtime(now - 900 + i * 900 / max(1, n)))
    app._render_log()


# =====================================================================================
# Un style : lance l'interface, capture, quitte
# =====================================================================================
def pump(app, seconds: float) -> None:
    end = time.time() + seconds
    while time.time() < end:
        app.update()
        time.sleep(0.015)


def _release_version() -> str:
    """Dernier tag vX.Y.Z du dépôt (« » si introuvable)."""
    try:
        tags = subprocess.run(["git", "tag", "--list", "v*", "--sort=-v:refname"], cwd=str(ROOT),
                              capture_output=True, text=True, timeout=10).stdout.split()
        return tags[0] if tags else ""
    except Exception:
        return ""


def run_worker(look_key: str, out: Path, only_home: bool, version: str = "") -> None:
    u32.LockSetForegroundWindow(1)            # ce processus ne peut pas passer au premier plan
    _fake_input_modules()
    tmp = Path(tempfile.mkdtemp(prefix="dph-captures-"))

    import dofus_core as core
    core.BASE_DIR = tmp
    for name in ("CONFIG_PATH", "HISTORY_PATH", "DIGITS_PATH", "ANCHOR_PATH", "MY_PRICES_PATH"):
        setattr(core, name, tmp / getattr(core, name).name)
    core.DEBUG_DIR, core.LOG_DIR = tmp / "captures", tmp / "journaux"
    load, save = core.Config.load.__func__, core.Config.save      # chemin par défaut figé à l'import
    core.Config.load = classmethod(lambda cls, path=None: load(cls, path or core.CONFIG_PATH))
    core.Config.save = lambda self, path=None: save(self, path or core.CONFIG_PATH)
    core.beep = lambda *a, **k: None
    if version:                               # code source : « dev » -> dernière version publiée
        core.app_version = lambda: version
    demo_config(core, looks()[look_key][:3])

    _quiet_windows()
    import dofus_price_helper_psg as gui
    gui.RUNS_PATH = tmp / "dofus_relist_runs.json"
    gui.windows_notify = lambda *a, **k: False
    gui.Tray.start = lambda self: None
    A = gui.App
    for name in ("_unstick_keys", "_check_calibration", "_watch_game", "_sel_watch", "_hud_alt_poll",
                 "_whats_new", "_first_launch", "_apply_topmost"):
        setattr(A, name, lambda self, *a, **k: None)
    A._tour_start = lambda self, *a, **k: None
    A._register_hotkeys = lambda self: None
    A._hud_wanted = lambda self: (True, False)           # HUD visible même sans le jeu au premier plan

    app = gui.App()
    pump(app, 0.8)
    demo_sales(core, gui, app)
    show_quietly(app)
    pump(app, 1.5)

    shots = {}
    app.tabs.set("Accueil")
    pump(app, 0.6)
    shots["accueil"] = grab(app)
    if not only_home:
        # onglets : fenêtre plus haute (plus de contenu visible), image recadrée sur l'onglet
        tall = min(1340, u32.GetSystemMetrics(1) - 100)
        app.geometry(f"{WINDOW_SIZE[0]}x{tall}+80+20")
        pump(app, 1.0)
        for tab, name in (("Prix", "onglet_prix"), ("Mes ventes", "onglet_mes_ventes"),
                          ("Calibration", "onglet_calibration"), ("Raccourcis", "onglet_raccourcis"),
                          ("Options", "onglet_options")):
            app.tabs.set(tab)
            app._on_tab_change()
            pump(app, 0.6)
            shots[name] = grab_widget(app, app.tabs)
        seg = getattr(app, "theme_seg", None)               # Options › Apparence
        if seg is not None:
            scroll_to(seg.master.master.master)
            pump(app, 0.6)
            shots["onglet_apparence"] = grab_widget(app, app.tabs)
        app.tabs.set("Accueil")
        app.geometry(f"{WINDOW_SIZE[0]}x{WINDOW_SIZE[1]}+80+60")
        pump(app, 0.6)
        win = getattr(app, "_summary_win", None)
        if win is not None and win.winfo_exists():
            show_quietly(win)
            pump(win, 0.8)
            shots["resume"] = grab(win)
        # HUD : la mise à jour qu'on voit dans l'HDV (lot 1 : 2 150 -> 1 988)
        app._on_result(core.Result(1, "ok", "[MAJ] Lot 1 | ton prix 2 150 | moins cher 1 989 -> 1 988 | "
                                            "modifié", core.ScreenRead(), 1988, old_price=2150,
                                   hint="Modifié : 1988"))
        app._show_screen(core.ScreenRead(prices={1: core.Reading(1989, 97), 10: core.Reading(39999, 96),
                                                 100: core.Reading(159996, 94)}, selected=1))
        def hud(name):
            app._hud_ticker = None
            app._refresh_hud()
            if app._hud is not None and app._hud.winfo_exists():
                show_quietly(app._hud)
                pump(app, 0.8)
                shots[name] = grab(app._hud)

        hud("hud_raw")
        app._set_hud_alt(True)                             # Alt maintenu : boutons d'action
        hud("hud_alt")
        app._set_hud_alt(False)
        for shape in ("pill", "minimal"):                  # autres formes
            app.cfg.hud_shape = shape
            app._hud_rebuild()
            hud(f"hud_{shape}")
        app.cfg.hud_shape = "card"
        app._hud_rebuild()
        app._loop_start("relist_all")                      # pendant « Toute la liste »
        app._loop_progress({"row": 23, "total": 48, "changed": 6, "bad": 1})
        if app._loop is not None:
            app._loop["t0"] = time.time() - 15
        hud("hud_loop")
        app._toggle_cheatsheet(ms=120000)                  # aide-mémoire des touches
        if app._cheat is not None and app._cheat.winfo_exists():
            show_quietly(app._cheat)
            pump(app, 0.8)
            shots["cheat_raw"] = grab(app._cheat)

    out.mkdir(parents=True, exist_ok=True)
    for name, img in shots.items():
        img.save(out / f"{name}.png")
    app.closing = True
    app.destroy()


# =====================================================================================
# Mise en forme : coins arrondis, ombre, compositions
# =====================================================================================
def framed(img, radius: int = 14, margin: int = 36, shadow: int = 22):
    """Fenêtre -> coins arrondis + ombre douce, sur fond transparent (lisible en thème clair et sombre)."""
    from PIL import Image, ImageChops, ImageDraw, ImageFilter
    w, h = img.size
    mask = Image.new("L", (w, h), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, w - 1, h - 1), radius, fill=255)
    win = img.convert("RGBA")
    win.putalpha(ImageChops.multiply(win.getchannel("A"), mask))   # garde la transparence d'origine
    size = (w + 2 * margin, h + 2 * margin)
    sh = Image.new("L", size, 0)
    sh.paste(win.getchannel("A"), (margin, margin + shadow // 3))
    sh = sh.filter(ImageFilter.GaussianBlur(shadow)).point(lambda v: v * 0.55)
    out = Image.new("RGBA", size, (0, 0, 0, 0))
    out.paste((0, 0, 0, 255), (0, 0), sh)
    out.alpha_composite(win, (margin, margin))
    return out


def trim_bottom(img, keep: int = 24):
    """Onglet peu rempli : coupe le fond vide sous le dernier élément (la barre de défilement,
    à droite, n'est pas prise en compte)."""
    import numpy as np
    a = np.asarray(img.convert("RGB")).astype(int)
    body = a[:, 12:max(13, a.shape[1] - 60)]
    busy = np.where(np.abs(body - body[-8, 0]).sum(axis=2).max(axis=1) > 24)[0]
    if not len(busy):
        return img
    bottom = min(img.height, int(busy[-1]) + keep)
    return img.crop((0, 0, img.width, bottom)) if bottom < img.height - 40 else img


def keyed(raw, key=(1, 2, 3), opacity: float = 0.92):
    """Fenêtre flottante (HUD, aide-mémoire) : la couleur clé devient transparente, le reste à son opacité."""
    import numpy as np
    from PIL import Image
    a = np.array(raw.convert("RGBA"))
    transparent = (np.abs(a[:, :, :3].astype(int) - key).sum(axis=2) <= 6)
    a[:, :, 3] = np.where(transparent, 0, int(255 * opacity))
    return Image.fromarray(a)


def game_scene(size):
    """Décor du jeu flouté et assombri (comme le jeu derrière une fenêtre)."""
    from PIL import Image, ImageEnhance, ImageFilter
    bg = Image.open(BACKDROP).convert("RGBA").resize(size).filter(ImageFilter.GaussianBlur(28))
    return ImageEnhance.Brightness(bg).enhance(0.55)


def hud_on_backdrop(hud_raw):
    """Le HUD posé au-dessus de l'HDV, comme en jeu."""
    from PIL import Image
    hud_img = keyed(hud_raw)
    bg = Image.open(BACKDROP).convert("RGBA")
    pad_top = hud_img.height + 30
    canvas = game_scene((bg.width, bg.height + pad_top))
    canvas.alpha_composite(bg, (0, pad_top))
    canvas.alpha_composite(hud_img, ((bg.width - hud_img.width) // 2, 12))
    return canvas


def hud_variants(items, width: int = 760):
    """Plusieurs HUD l'un sous l'autre, chacun avec sa légende, sur le décor du jeu."""
    from PIL import ImageDraw, ImageFont
    try:
        font = ImageFont.truetype("segoeuib.ttf", 15)
    except OSError:
        font = ImageFont.load_default()
    huds = [(keyed(img), label) for img, label in items]
    rows = [max(h.height, 24) + 34 for h, _ in huds]
    canvas = game_scene((width, sum(rows) + 16))
    d = ImageDraw.Draw(canvas)
    y = 16
    for (h, label), rh in zip(huds, rows):
        d.text((22, y), label, font=font, fill=(232, 234, 237, 235))
        canvas.alpha_composite(h, (22, y + 24))
        y += rh
    return canvas


def cheat_on_backdrop(cheat_raw):
    """Aide-mémoire des touches par-dessus l'HDV, côté liste (là où il s'affiche en jeu)."""
    from PIL import Image
    c = keyed(cheat_raw, opacity=0.95)
    bg = Image.open(BACKDROP).convert("RGBA")
    if c.height + 40 > bg.height:
        c = c.resize((int(c.width * (bg.height - 40) / c.height), bg.height - 40), Image.LANCZOS)
    bg.alpha_composite(c, (bg.width - c.width - 24, (bg.height - c.height) // 2))
    return bg


def zones_on_backdrop():
    """Zones de la calibration automatique dessinées sur l'HDV, aux couleurs de l'outil."""
    from PIL import Image, ImageDraw, ImageFont
    res, _screen, _origin = autocal_backdrop()
    f = res.fields
    img = Image.open(BACKDROP).convert("RGBA")
    over = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(over)
    try:
        font = ImageFont.truetype("segoeuib.ttf", 14)
    except OSError:
        font = ImageFont.load_default()
    rects = (("anchor_region", "Repère HDV", "#ffffff"), ("table_region", "Tableau", "#66d9ef"),
             ("qty_region", "Quantité", "#ae81ff"), ("avg_region", "Prix moyen", "#a6e22e"),
             ("count_region", "Compteur", "#fd971f"), ("name_region", "Nom", "#e6db74"))
    points = (("price_field", "Prix du lot", "#f92672"), ("modify_button", "Modifier", "#f92672"),
              ("relist_row", "1re ligne", "#66d9ef"))

    def rgb(h, a):
        return tuple(int(h[i:i + 2], 16) for i in (1, 3, 5)) + (a,)

    def tag(x, y, text, color):
        tw = d.textlength(text, font=font)
        d.rounded_rectangle((x, y - 20, x + tw + 10, y - 2), 4, fill=rgb(color, 235))
        d.text((x + 5, y - 19), text, font=font, fill=(16, 18, 22, 255))

    for key, label, color in rects:
        if f.get(key):
            x, y, w, h = f[key]
            d.rectangle((x, y, x + w, y + h), fill=rgb(color, 60), outline=rgb(color, 255), width=2)
            tag(x, y, label, color)
    for key, label, color in points:
        if f.get(key):
            x, y = f[key][:2]
            d.ellipse((x - 7, y - 7, x + 7, y + 7), fill=rgb(color, 255), outline=(255, 255, 255, 255), width=2)
            tag(x + 10, y + 8, label, color)
    img.alpha_composite(over)
    return img


def mosaic(paths_titles, cols: int = 3, tile_w: int = 560):
    """Captures de l'Accueil, une par style, en grille avec le nom du style."""
    from PIL import Image, ImageDraw, ImageFont
    try:
        font = ImageFont.truetype("segoeuib.ttf", 22)
    except OSError:
        font = ImageFont.load_default()
    tiles = []
    for path, title in paths_titles:
        im = Image.open(path).convert("RGBA")
        im = im.resize((tile_w, int(im.height * tile_w / im.width)), Image.LANCZOS)
        t = framed(im, radius=10, margin=24, shadow=14)
        canvas = Image.new("RGBA", (t.width, t.height + 30), (0, 0, 0, 0))
        canvas.alpha_composite(t, (0, 30))
        d = ImageDraw.Draw(canvas)
        tw = d.textlength(title, font=font)
        d.text(((canvas.width - tw) / 2, 2), title, font=font, fill=(139, 146, 156, 255))
        tiles.append(canvas)
    rows = (len(tiles) + cols - 1) // cols
    tw, th = tiles[0].size
    out = Image.new("RGBA", (tw * cols, th * rows), (0, 0, 0, 0))
    for i, t in enumerate(tiles):
        r, c = divmod(i, cols)
        n_in_row = min(cols, len(tiles) - r * cols)
        x0 = (out.width - n_in_row * tw) // 2           # dernière ligne centrée
        out.alpha_composite(t, (x0 + c * tw, r * th))
    return out


# =====================================================================================
def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    all_looks = looks()
    ap.add_argument("--look", default="night", choices=list(all_looks), help="style des captures principales")
    ap.add_argument("--styles", default=",".join(DEFAULT_STYLES),
                    help="styles de la mosaïque, séparés par des virgules (« all » = tous), "
                         f"parmi : {', '.join(all_looks)}")
    ap.add_argument("--out", default=str(ROOT / "docs" / "img"), help="dossier des images")
    ap.add_argument("--no-styles", action="store_true", help="sans les mosaïques de styles")
    ap.add_argument("--styles-only", action="store_true", help="sans la mosaïque des thèmes Dofus")
    ap.add_argument("--version", default=_release_version(),
                    help="version affichée dans la fenêtre (par défaut : dernier tag vX.Y.Z)")
    ap.add_argument("--worker", help=argparse.SUPPRESS)
    ap.add_argument("--home-only", action="store_true", help=argparse.SUPPRESS)
    a = ap.parse_args()
    if sys.platform != "win32":
        raise SystemExit("Windows seulement (capture des fenêtres).")
    styles = list(all_looks) if a.styles == "all" else [s.strip() for s in a.styles.split(",") if s.strip()]
    unknown = [s for s in styles if s not in all_looks]
    if unknown:
        ap.error(f"style inconnu : {', '.join(unknown)} (choix : {', '.join(all_looks)})")
    if a.worker:
        run_worker(a.look, Path(a.worker), a.home_only, a.version)
        return

    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    raw = Path(tempfile.mkdtemp(prefix="dph-captures-brutes-"))

    def worker(look: str, home_only: bool) -> Path:
        d = raw / look
        cmd = [sys.executable, str(Path(__file__).resolve()), "--look", look, "--worker", str(d),
               "--version", a.version]
        if home_only:
            cmd.append("--home-only")
        print(f"- style {look}...", flush=True)
        subprocess.run(cmd, check=True, cwd=str(ROOT))   # un processus par style (couleurs fixées à l'import)
        return d

    from PIL import Image
    main_dir = worker(a.look, False)

    def raw_img(name):
        p = main_dir / f"{name}.png"
        return Image.open(p) if p.exists() else None

    for name in ("accueil", "resume", "onglet_prix", "onglet_mes_ventes", "onglet_calibration",
                 "onglet_raccourcis", "onglet_options", "onglet_apparence"):
        if raw_img(name):
            img = raw_img(name)
            framed(trim_bottom(img) if name.startswith("onglet_") else img).save(out / f"{name}.png")
    if raw_img("hud_raw"):
        framed(hud_on_backdrop(raw_img("hud_raw")), radius=10).save(out / "hud.png")
    variants = [(raw_img(n), label) for n, label in (
        ("hud_raw", "Carte : l'état et la dernière action, avec les prix de l'objet sélectionné"),
        ("hud_loop", "Pendant « Toute la liste » : progression et temps restant"),
        ("hud_alt", "Alt maintenu : le HUD devient cliquable"),
        ("hud_pill", "Forme « Pilule »"),
        ("hud_minimal", "Forme « Minimal »")) if raw_img(n)]
    if variants:
        framed(hud_variants(variants), radius=10).save(out / "hud_variantes.png")
    if raw_img("cheat_raw"):
        framed(cheat_on_backdrop(raw_img("cheat_raw")), radius=10).save(out / "aide_memoire.png")
    framed(zones_on_backdrop(), radius=10).save(out / "calibration.png")

    if not a.no_styles:
        def tiles(keys):
            return [((main_dir if k == a.look else worker(k, True)) / "accueil.png", all_looks[k][3])
                    for k in keys]
        t = tiles(styles)
        mosaic(t, cols=3 if len(t) <= 6 else 4).save(out / "styles.png")
        dofus = [k for k in all_looks if k.startswith("dofus_")]
        if dofus and not a.styles_only:
            mosaic(tiles(dofus), cols=4, tile_w=480).save(out / "themes_dofus.png")

    print(f"Images : {out}")
    for p in sorted(out.glob("*.png")):
        print(f"  {p.name}")


if __name__ == "__main__":
    main()
