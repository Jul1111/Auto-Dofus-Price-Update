"""Fenêtre principale : App rassemble les morceaux de l'interface (un fichier par thème)."""
from __future__ import annotations

import os
import queue
import sys
import threading
import time
import tkinter as tk
from typing import Optional

import customtkinter as ctk

from dofus_helper import core
from dofus_helper import update as dofus_update
from dofus_helper import backup as dofus_backup
from dofus_helper.gui import logo as dofus_logo
from dofus_helper.gui import style
from dofus_helper.gui.style import P

from .common import (
    BTN2,
    BTN2_HOVER,
    CARD,
    faded,
    FLOOR_LABELS,
    fmt,
    ico,
    keyboard,
    KEYBOARD_AVAILABLE,
    mix_color,
    MUTED,
    ROUNDING_LABELS,
    STALE_JOB_S,
    UNDERCUT_LABELS,
)
from .popups import ANIMATE, close_popup, Tooltip
from .helpers import (
    geometry_on_screen,
    layout_for,
    load_runs,
    LOG_FILTERS,
    relaunch_command,
    RELAUNCH_FLAG,
    scale_label,
    tab_index_for_key,
    TAB_NAMES,
)
from .tray import brand, Tray

from .home import HomeMixin
from .tabs import TabsMixin
from .options import OptionsMixin
from .journal import JournalMixin
from .results import ResultsMixin
from .wizard import CalibrationMixin
from .loops import LoopsMixin
from .watch import GameWatchMixin
from .hud import HudMixin
from .tour import TourMixin


class App(HomeMixin, TabsMixin, OptionsMixin, JournalMixin, ResultsMixin, CalibrationMixin, LoopsMixin, GameWatchMixin, HudMixin, TourMixin,
          ctk.CTk):
    def __init__(self):
        super().__init__()
        self.cfg = core.Config.load()
        style.apply_theme(ctk)
        style.smooth_hover(ctk, lambda: ANIMATE["on"])      # survol des boutons en fondu
        self.configure(fg_color=P["bg"])
        self.title(f"Dofus Price Helper {core.app_version()}")
        brand(self)
        ctk.set_widget_scaling(self.cfg.ui_scale if 0.5 <= self.cfg.ui_scale <= 2 else 1.0)
        self.geometry("1120x800")
        self.minsize(640, 540)
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
        self.hud_sel: Optional[dict] = None   # HUD : prix (lots 1, 10, 100) de l'objet sélectionné
        self._sel_sig = None                  # empreinte du tableau de l'HDV (changement d'objet)
        self._sel_pending = False
        self._last_price: Optional[int] = None   # HUD cliquable : « Copier »
        self._hud_active = time.time()       # dernière activité (masquage automatique)
        self._hud_expand_until = 0.0         # mode pastille : agrandi jusqu'à
        self._hud_alt = False                # Alt maintenu : HUD cliquable
        self._alt_since: Optional[float] = None
        self._hud_layout_key = None
        self._hud_fading = False
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
        self._hud_shape = "card"
        self._hud_ticker: Optional[dict] = None    # prix qui défile dans le HUD
        self._hud_tick_after = None
        self._hud_resize_anim = None
        self._hud_pulse: Optional[tuple] = None    # (couleur, début) : éclat du rond d'état
        self._hud_tinted = False
        self._drift_text: Optional[str] = None     # problème de calibration affiché (bandeau + HUD)
        self._drift_ignored: Optional[str] = None  # « Ignorer » : ce texte-là ne revient plus
        self._calib_alert_t = 0.0                  # début de l'alerte (le HUD la montre jusqu'au résultat suivant)
        self._last_action_t = 0.0
        self.restart_requested = False
        self.closing = False
        ANIMATE["on"] = bool(self.cfg.animations)

        self._build_vars()
        self._build_ui()
        self._setup_log_tags()
        self._render_log()                  # journal vide : message d'accueil

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
        self.after(2500, self._check_calibration)   # fenêtre du jeu / écran changés ? (toutes les 5 s)
        self.tray.start()                         # icône près de l'horloge : toujours (réduire l'y range)
        self.after(400, self._apply_hud)          # HUD activé : créé dès le lancement (caché hors du jeu)
        self.after(1500, self._hud_alt_poll)
        self.after(1600, self._hud_anim_tick)
        self.after(2000, self._sel_watch)
        self.after(1800, self._whats_new)         # 1er lancement d'une nouvelle version
        self.after(1200, self._watch_game)
        self.bind("<Control-KeyPress>", self._on_ctrl_key)
        self.bind("<Escape>", self._on_escape)
        self.bind("<Unmap>", self._on_unmap)
        self._layout = None
        self.bind("<Configure>", self._on_resize, add="+")
        self.after(600, self._autowrap_all)
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

        ctk.CTkButton(w, text="Calibration automatique", height=40, font=ctk.CTkFont(size=14, weight="bold"),
                      image=ico("spark", P["on_accent"], 18),
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
            "relist_force_suspect": ctk.BooleanVar(value=c.relist_force_suspect),
            "relist_summary": ctk.BooleanVar(value=c.relist_summary),
            "auto_recalibrate": ctk.BooleanVar(value=c.auto_recalibrate),
            "fast_digits": ctk.BooleanVar(value=c.fast_digits),
            "verify_before_enter": ctk.BooleanVar(value=c.verify_before_enter),
            "smart_f1": ctk.BooleanVar(value=c.smart_f1),
            "always_on_top": ctk.BooleanVar(value=c.always_on_top),
            "check_updates": ctk.BooleanVar(value=c.check_updates),
            "notify": ctk.BooleanVar(value=c.notify),
            "animations": ctk.BooleanVar(value=c.animations),
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
        band = ctk.CTkFrame(wrap, fg_color=CARD, corner_radius=14, border_width=1, border_color=P["border"])
        band.pack(fill="x", padx=12, pady=(8, 4))
        self.head_band = band
        head = ctk.CTkFrame(band, fg_color="transparent")
        head.pack(fill="x", padx=(10, 8), pady=(8, 0))
        logo = dofus_logo.logo_image(128, glow=style.is_dark())   # halo doré : seulement sur fond sombre
        self._logo_img = ctk.CTkImage(light_image=logo, dark_image=logo, size=(50, 50))
        ctk.CTkLabel(head, text="", image=self._logo_img).pack(side="left", padx=(0, 8))
        titles = ctk.CTkFrame(head, fg_color="transparent")
        titles.pack(side="left")
        tl = ctk.CTkFrame(titles, fg_color="transparent")
        tl.pack(anchor="w")
        ctk.CTkLabel(tl, text="Dofus Price Helper", font=ctk.CTkFont(size=20, weight="bold"), height=26
                     ).pack(side="left")
        ctk.CTkLabel(tl, text=core.app_version(), text_color=MUTED, fg_color=P["card2"], corner_radius=8,
                     height=20, font=ctk.CTkFont(size=11, weight="bold")).pack(side="left", padx=(10, 0), ipadx=4)
        self.head_sub = ctk.CTkLabel(titles, text="Tes prix au plus juste à l'hôtel de vente", text_color=MUTED,
                                     font=ctk.CTkFont(size=12), height=18)
        self.head_sub.pack(anchor="w")
        info = ctk.CTkFrame(band, fg_color="transparent")
        info.pack(fill="x", padx=8, pady=(8, 2))
        # fin liseré dégradé (couleur d'accent -> or -> fond de la carte)
        self._head_strip = tk.Canvas(band, height=3, highlightthickness=0, borderwidth=0, bg=CARD)
        self._head_strip.pack(fill="x", padx=18, pady=(6, 10))
        self._head_strip.bind("<Configure>", lambda _e: self._draw_head_strip(), add="+")
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
        self.loop_stop = ctk.CTkButton(self.loop_bar, text="Arrêter", width=92, height=24,
                                       image=ico("stop", style.CHIP["red"][1], 12),
                                       fg_color=style.CHIP["red"][0], hover_color=P["red_hover"],
                                       text_color=style.CHIP["red"][1], command=self._stop_loop)
        self.loop_stop.pack(side="left", padx=(8, 4), pady=3)
        # calibration décalée (fenêtre du jeu redimensionnée, écran changé) : affiché au besoin
        ob, of = style.CHIP["orange"]
        self.drift_bar = ctk.CTkFrame(wrap, fg_color=ob, corner_radius=10)
        ctk.CTkLabel(self.drift_bar, text="", image=ico("warn", of, 18)).pack(side="left", padx=(12, 0))
        self.drift_lbl = ctk.CTkLabel(self.drift_bar, text="", text_color=of, anchor="w", justify="left",
                                      wraplength=620, font=ctk.CTkFont(size=12, weight="bold"))
        self.drift_lbl.pack(side="left", fill="x", expand=True, padx=(8, 12), pady=6)
        ctk.CTkButton(self.drift_bar, text="Ignorer", width=80, height=26, fg_color=BTN2, hover_color=BTN2_HOVER,
                      text_color=P["text"], command=self._ignore_drift).pack(side="right", padx=(4, 8), pady=6)
        ctk.CTkButton(self.drift_bar, text="Voir zones", width=108, height=26, fg_color=BTN2, image=ico("eye"),
                      hover_color=BTN2_HOVER, text_color=P["text"], command=self._show_zones
                      ).pack(side="right", padx=4, pady=6)
        self._tip(ctk.CTkButton(self.drift_bar, text="Recalibrer", width=118, height=26,
                                image=ico("spark", P["on_accent"]),
                                command=lambda: (self.tabs.set("Calibration"),
                                                 self._countdown("automatique", self._calib_auto_ui))),
                  "Calibration automatique : affiche l'HDV (onglet Vente) pendant le compte à rebours."
                  ).pack(side="right", padx=4, pady=6)
        self.pin_btn = ctk.CTkButton(head, text="", width=36, height=36, corner_radius=10, border_width=1,
                                     command=lambda: self.v["always_on_top"].set(not self.v["always_on_top"].get()))
        self._tip(self.pin_btn, "Fenêtre de l'outil toujours au-dessus du jeu (clic = activer / couper)."
                  ).pack(side="right", padx=(8, 4))
        self.v["always_on_top"].trace_add("write", lambda *_: self._refresh_pin())
        self._refresh_pin()
        self.update_btn = ctk.CTkButton(head, text="", width=150, fg_color=style.CHIP["green"][0],
                                        hover_color=P["green_hover"], text_color=style.CHIP["green"][1])   # affiché si une version plus récente existe

        # ---------------- onglets
        tabs = ctk.CTkTabview(self, anchor="nw", fg_color="transparent", corner_radius=12,
                              command=lambda: self._on_tab_change())
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
        self.side = side
        ctk.CTkLabel(side, text="Activité", font=ctk.CTkFont(size=15, weight="bold")
                     ).pack(anchor="w", padx=14, pady=(12, 2))
        self.act_box = ctk.CTkFrame(side, fg_color="transparent")
        self.act_box.pack(fill="x", padx=10)
        self.act_empty = self._empty_state(
            self.act_box, "Aucune action pour l'instant",
            f"Ouvre l'HDV, sélectionne un objet de ton inventaire et appuie sur {self.cfg.hotkeys['sell'].upper()}.")
        self.act_rows = []
        for _ in range(self.ACTIVITY_ROWS):
            r = ctk.CTkFrame(self.act_box, fg_color="transparent")
            t = ctk.CTkLabel(r, text="", text_color=MUTED, width=40, anchor="w", font=ctk.CTkFont(size=12))
            t.pack(side="left")
            icon = ctk.CTkLabel(r, text="", width=22)
            icon.pack(side="left", padx=(0, 4))
            hint = ctk.CTkLabel(r, text="", anchor="e", font=ctk.CTkFont(size=12))
            hint.pack(side="right", padx=(6, 2))
            delta = ctk.CTkLabel(r, text="", height=20, corner_radius=8, fg_color=P["card2"],
                                 font=ctk.CTkFont(size=11, weight="bold"))
            txt = ctk.CTkLabel(r, text="", anchor="w", font=ctk.CTkFont(size=12, weight="bold"))
            txt.pack(side="left", fill="x", expand=True)
            self.act_rows.append((r, t, txt, hint, icon, delta))
        ctk.CTkFrame(side, fg_color=P["border"], height=1).pack(fill="x", padx=14, pady=(8, 6))
        hr = ctk.CTkFrame(side, fg_color="transparent")
        hr.pack(fill="x", padx=14)
        ctk.CTkLabel(hr, text="Dernière lecture", font=ctk.CTkFont(size=13, weight="bold")).pack(side="left")
        self.read_info = ctk.CTkLabel(hr, text="", text_color=MUTED, font=ctk.CTkFont(size=12))
        self.read_info.pack(side="right")
        self.read_empty = self._empty_state(side, "Pas encore de lecture",
                                            "Les prix lus s'affichent ici à chaque vente, ou avec « Lire (test) » "
                                            "(onglet Calibration).", icon="eye")
        self.read_grid = grid = ctk.CTkFrame(side, fg_color=P["card2"], corner_radius=8)
        # pastille devant chaque prix : vert = lecture sûre, orange = moyenne, rouge = douteuse
        coin = dofus_logo.logo_image(64)
        self._coin_img = ctk.CTkImage(light_image=coin, dark_image=coin, size=(14, 14))
        for c, t in ((0, "Lot"), (2, "Prix"), (3, "Par objet")):
            ctk.CTkLabel(grid, text=(" " + t) if c == 2 else t, text_color=MUTED, height=22,
                         image=self._coin_img if c == 2 else None, compound="left").grid(
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
        ctk.CTkButton(top, text="Effacer", width=88, height=24, fg_color=BTN2, text_color=P["text"], hover_color=BTN2_HOVER,
                      image=ico("trash", size=14),
                      command=self._clear_log).pack(side="right")
        self.copy_btn = self._tip(ctk.CTkButton(top, text="Copier", width=86, height=24, fg_color=BTN2, text_color=P["text"], hover_color=BTN2_HOVER,
                                                image=ico("copy", size=14),
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
                     "relist_auto", "relist_confirm_enter", "relist_force_suspect", "relist_summary", "fast_digits", "auto_recalibrate",
                     "verify_before_enter", "smart_f1", "always_on_top", "check_updates", "notify",
                     "animations", "auto_profile", "hud"):
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
                elif name == "peek":
                    self.ui_events.put(("peek", self.engine.peek()))
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
        elif name == "peek":
            self._sel_pending = False
            if arg is not None and any(v is not None for v in arg.values.values()):
                self._set_hud_selected(arg)
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

    # ---------------------------------------------------------------- misc
    def _on_pause_key(self):
        """Touche d'arrêt (Ctrl+Alt+P) : arrête le parcours en cours (Tout vendre, Toute la liste),
        comme « Arrêter ». Il n'y a plus de pause : hors parcours, elle ne fait rien."""
        if self._loop is not None:
            self._stop_loop()
        else:
            self._hud_message("Aucun parcours en cours", f"{self.cfg.hotkeys['pause'].upper()} arrête "
                              "Tout vendre / Toute la liste", MUTED, 1800)

    CHIP_GREEN, CHIP_ORANGE, CHIP_RED, CHIP_GREY = "green", "orange", "red", "grey"   # gui/style.py : CHIP

    def _set_hdv(self, state: Optional[str]):
        if state != self.hdv_state:
            self.hdv_state = state
            if state == "lost":
                self.hud_sel = None
                self._calib_alert_t = time.time()
                self._hud_flash(style.CHIP["orange"][1], 2500)
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
            chip = self.chips[key]
            changed = getattr(chip, "_last_text", None) not in (None, text)
            chip._last_text = text
            chip.configure(text=text, fg_color=bg, text_color=fg)
            if changed:
                self._pulse(chip, bg, fg)
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
        style.set_titlebar(self, P["caption"], P["text"], P["border"])

    # ---- micro-animations (option « Animations »)
    def _on_tab_change(self):
        """Nouvel onglet : son contenu glisse de quelques pixels vers le haut en s'installant."""
        if not ANIMATE["on"]:
            return
        try:
            page = self.tabs.tab(self.tabs.get()).winfo_children()[0]
        except (IndexError, ValueError, tk.TclError):
            return
        token = object()
        self._tab_anim = token
        steps = 11

        def tick(i=0):
            if getattr(self, "_tab_anim", None) is not token:
                return
            try:
                page.pack_configure(pady=(round(18 * (1 - style.ease_out(i / steps))), 0))
            except tk.TclError:
                return
            if i < steps:
                self.after(16, lambda: tick(i + 1))
        tick()

    def _count_to(self, label, value: int, ms: int = 450):
        """Le nombre d'une tuile monte (ou descend) jusqu'à sa nouvelle valeur."""
        start = getattr(label, "_count", None)
        label._count = value
        if start is None or start == value or not ANIMATE["on"]:
            label.configure(text=str(value))
            return
        token = object()
        label._count_anim = token
        steps = max(1, ms // 16)

        def tick(i=1):
            if getattr(label, "_count_anim", None) is not token:
                return
            v = round(start + (value - start) * style.ease_out(i / steps))
            try:
                label.configure(text=str(v))
            except tk.TclError:
                return
            if i < steps:
                self.after(16, lambda: tick(i + 1))
        tick()

    def _pulse(self, widget, bg: str, fg: str, ms: int = 520):
        """Éclat bref d'une pastille dont l'état vient de changer (sa couleur s'éclaircit puis revient)."""
        if not ANIMATE["on"]:
            return
        token = object()
        widget._pulse_anim = token
        steps = max(1, ms // 16)
        hot = style.blend(widget, bg, fg, 0.45)

        def tick(i=1):
            if getattr(widget, "_pulse_anim", None) is not token:
                return
            try:
                widget.configure(fg_color=style.blend(widget, hot, bg, style.ease_out(i / steps)))
            except tk.TclError:
                return
            if i < steps:
                self.after(16, lambda: tick(i + 1))
        tick()

    def _draw_head_strip(self):
        """Liseré dégradé sous l'en-tête : accent -> or -> fond de la carte."""
        cv = self._head_strip
        w = cv.winfo_width()
        cv.delete("all")
        if w < 4:
            return
        stops = ((0.0, P["accent"]), (0.55, P["gold"]), (1.0, CARD))
        for x in range(0, w, 2):
            f = x / max(1, w - 1)
            for (a, ca), (b, cb) in zip(stops, stops[1:]):
                if a <= f <= b:
                    cv.create_line(x, 0, x, 4, fill=mix_color(ca, cb, (f - a) / (b - a)), width=2)
                    break

    def _refresh_pin(self):
        on = bool(self.v["always_on_top"].get())
        self.pin_btn.configure(image=ico("pin", P["on_accent"] if on else MUTED, 18),
                               fg_color=P["accent"] if on else "transparent",
                               hover_color=P["accent_hover"] if on else BTN2_HOVER,
                               border_color=P["accent"] if on else P["border"])

    def _empty_state(self, parent, title: str, text: str, icon: Optional[str] = None):
        """Bloc « rien ici pour l'instant » : pièce du logo estompée (ou icône), titre, aide."""
        f = ctk.CTkFrame(parent, fg_color="transparent")
        if icon is None:
            if getattr(self, "_faded_logo", None) is None:
                img = faded(dofus_logo.logo_image(96), 0.45)
                self._faded_logo = ctk.CTkImage(light_image=img, dark_image=img, size=(40, 40))
            image = self._faded_logo
        else:
            image = ico(icon, MUTED, 30)
        ctk.CTkLabel(f, text="", image=image).pack(side="left", padx=(4, 12), pady=6)
        col = ctk.CTkFrame(f, fg_color="transparent")
        col.pack(side="left", fill="x", expand=True)
        ctk.CTkLabel(col, text=title, anchor="w", font=ctk.CTkFont(size=13, weight="bold")).pack(fill="x")
        ctk.CTkLabel(col, text=text, anchor="w", justify="left", wraplength=300, text_color=MUTED,
                     font=ctk.CTkFont(size=12)).pack(fill="x")
        return f

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
        self.tray.start()
        self._tray_update()

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
        """Fenêtre réduite : elle se range près de l'horloge (icône de la zone de notification)."""
        if e.widget is not self or self.tray.icon is None:
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

    # ---- mise en page qui s'adapte à la taille de la fenêtre
    def _on_resize(self, e):
        if e.widget is not self:
            return
        if getattr(self, "_resize_after", None):
            self.after_cancel(self._resize_after)
        self._resize_after = self.after(60, self._apply_layout)

    def _apply_layout(self):
        """Fenêtre étroite : le panneau Activité se retire et les onglets prennent toute la largeur ;
        très étroite : sous-titre et aide du journal masqués ; peu haute : journal plus court."""
        self._resize_after = None
        try:
            scale = ctk.ScalingTracker.get_window_scaling(self) or 1.0
        except Exception:
            scale = 1.0
        w, h = self.winfo_width() / scale, self.winfo_height() / scale
        layout = layout_for(w, h)
        if layout == self._layout:
            return
        old, self._layout = self._layout or {}, layout
        if layout["side"] != old.get("side"):
            if layout["side"]:
                self.side.grid()
                self.tabs.grid_configure(columnspan=1, padx=(8, 4))
            else:
                self.side.grid_remove()
                self.tabs.grid_configure(columnspan=2, padx=(8, 12))
        if layout["subtitle"] != old.get("subtitle"):
            if layout["subtitle"]:
                self.head_sub.pack(anchor="w")
            else:
                self.head_sub.pack_forget()
        if layout["log_hint"] != old.get("log_hint"):
            self.log_hint.configure(text="Clic sur une ligne avec un prix = le copier" if layout["log_hint"] else "")
        if layout["log_lines"] != old.get("log_lines"):
            self.log_text.configure(height=layout["log_lines"])

    def _autowrap_all(self):
        """Les textes sur toute la largeur de leur carte se replient selon la largeur réelle
        (au lieu d'une largeur fixe) : rien n'est coupé quand la fenêtre rétrécit."""
        def walk(wdg):
            for c in wdg.winfo_children():
                if isinstance(c, ctk.CTkLabel):
                    self._autowrap(c)
                walk(c)
        walk(self)

    def _autowrap(self, label):
        try:
            if not label.cget("wraplength") or label.winfo_manager() != "pack":
                return
            info = label.pack_info()
        except (tk.TclError, ValueError):
            return
        if info.get("fill") not in ("x", "both"):
            return
        padx = info.get("padx", 0)
        pad = sum(padx) if isinstance(padx, (tuple, list)) else int(padx) * 2
        master = label.master

        def fit(_e=None):
            try:
                scale = ctk.ScalingTracker.get_widget_scaling(label) or 1.0
                width = master.winfo_width()
                if width > 50:
                    label.configure(wraplength=max(140, int((width - pad) / scale) - 8))
            except (tk.TclError, ValueError):
                pass
        master.bind("<Configure>", fit, add="+")
        fit()

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


def main() -> None:
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
