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

import customtkinter as ctk

try:
    import keyboard
    KEYBOARD_AVAILABLE = True
except Exception:  # pas installé / pas les droits
    KEYBOARD_AVAILABLE = False

TAG_COLORS = {
    "TIME": "#7f8c8d", "INFO": "#bdc3c7", "ERROR": "#ff6b6b", "WARN": "#f1c40f",
    "OK": "#a6e22e", "OPT": "#ae81ff", "CAL": "#66d9ef",
}
STALE_JOB_S = 1.5   # s : un raccourci de jeu qui a attendu plus longtemps dans la file est ignoré
LEVEL_COLORS = {"ok": "#2ecc71", "warn": "#f1c40f", "error": "#e74c3c"}
ZONE_COLORS = {"table": "#66d9ef", "qty": "#ae81ff", "avg": "#a6e22e", "count": "#fd971f",
               "mine": "#f92672", "anchor": "#ffffff", "name": "#e6db74"}
ZONE_LABELS = {"table": "Tableau", "qty": "Quantité", "avg": "Prix moyen", "count": "Compteur",
               "mine": "Ton prix", "anchor": "Repère HDV", "name": "Nom"}
FLOOR_LABELS = {"floor": "au plancher", "keep": "garder mon prix", "stop": "arrêt (suspect)"}
UNDERCUT_LABELS = {"fixed": "kamas", "percent": "%"}
ROUNDING_LABELS = {"none": "aucun", "down_10": "dizaine inférieure", "down_100": "centaine inférieure",
                   "end_9": "finit par 9"}
CARD = "#202227"
MUTED = "#9aa0a6"
BTN2 = "#3a3f47"
ORANGE = "#e67e22"
# Tableau de bord : une couleur par graphique (une seule série chacun), palette sombre validée
DASH_COLORS = {"ventes": "#3987e5", "kamas": "#199e70", "modifs": "#d95926", "heures": "#3987e5",
               "lots": "#3987e5"}


def _fmt_num(n) -> str:
    return f"{n:,}".replace(",", " ")


def _nice_step(vmax: int) -> int:
    if vmax <= 5:
        return 1
    raw = vmax / 4
    mag = 10 ** (len(str(int(raw))) - 1)
    for m in (1, 2, 5, 10):
        if raw <= m * mag:
            return int(m * mag)
    return int(10 * mag)
POINT_COLORS = {"price_field": "#e74c3c", "sell_button": "#2ecc71", "modify_button": "#3498db"}
POINT_LABELS = {"price_field": "Champ « Prix du lot »", "sell_button": "Bouton « Mettre en vente »",
                "modify_button": "Bouton « Modifier »"}


def fmt(n: Optional[int]) -> str:
    return "-" if n is None else f"{n:,}".replace(",", " ")


class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")
        self.title("Dofus Price Helper")
        self.geometry("1120x800")
        self.minsize(980, 680)

        self.cfg = core.Config.load()
        self.engine = core.PriceEngine(self.cfg)
        self.jobs: "queue.Queue[tuple]" = queue.Queue()
        self.ui_events: "queue.Queue[tuple]" = queue.Queue()
        self._save_after: Optional[str] = None

        self._build_vars()
        self._build_ui()
        self._setup_log_tags()

        threading.Thread(target=self._worker, daemon=True).start()
        self._poll_ui()

        err = core.setup_tesseract(self.cfg)
        if err:
            self._log(err, "ERROR")
        self._register_hotkeys()
        self._refresh_status()
        self._apply_topmost()
        if not (self.cfg.table_region and self.cfg.qty_region and self.cfg.price_field):
            self.after(800, self._open_wizard)   # 1er lancement : calibration guidée
        self.protocol("WM_DELETE_WINDOW", self._on_close)

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
            "fast_digits": ctk.BooleanVar(value=c.fast_digits),
            "read_item_names": ctk.BooleanVar(value=c.read_item_names),
            "banner": ctk.BooleanVar(value=c.banner),
            "verify_before_enter": ctk.BooleanVar(value=c.verify_before_enter),
            "smart_f1": ctk.BooleanVar(value=c.smart_f1),
            "always_on_top": ctk.BooleanVar(value=c.always_on_top),
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
        self.stats_var = ctk.StringVar(value="")
        self.scroll_lbl = ctk.StringVar(value="")
        self.stats = {"ventes": 0, "modifs": 0, "suspects": 0}

    def _section(self, parent, title: str, sub: str = ""):
        f = ctk.CTkFrame(parent, fg_color=CARD)
        f.pack(fill="x", padx=6, pady=(6, 2))
        ctk.CTkLabel(f, text=title, font=ctk.CTkFont(size=13, weight="bold")).pack(anchor="w", padx=10, pady=(8, 0))
        if sub:
            ctk.CTkLabel(f, text=sub, text_color=MUTED, font=ctk.CTkFont(size=11), anchor="w",
                         wraplength=500, justify="left").pack(anchor="w", fill="x", padx=10)
        body = ctk.CTkFrame(f, fg_color="transparent")
        body.pack(fill="x", padx=8, pady=(4, 8))
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
        wrap = ctk.CTkFrame(self, fg_color=CARD, corner_radius=0)
        wrap.grid(row=0, column=0, columnspan=2, sticky="ew")
        head = ctk.CTkFrame(wrap, fg_color="transparent")
        head.pack(fill="x")
        ctk.CTkLabel(head, text="Dofus Price Helper", font=ctk.CTkFont(size=18, weight="bold")
                     ).pack(side="left", padx=(14, 10), pady=10)
        self.state_pill = ctk.CTkLabel(head, text="● Actif", corner_radius=10, fg_color="#1e5631",
                                       font=ctk.CTkFont(weight="bold"), width=90)
        self.state_pill.pack(side="left", padx=4)
        info = ctk.CTkFrame(wrap, fg_color="transparent")
        info.pack(fill="x", padx=14, pady=(0, 6))
        ctk.CTkLabel(info, textvariable=self.digits_var, text_color=MUTED, font=ctk.CTkFont(size=12)
                     ).pack(side="left")
        ctk.CTkLabel(info, textvariable=self.stats_var, text_color=MUTED, font=ctk.CTkFont(size=12)
                     ).pack(side="left", padx=16)
        ctk.CTkButton(head, text="Voir zones", width=90, fg_color=BTN2,
                      command=self._show_zones).pack(side="right", padx=(4, 12))
        ctk.CTkButton(head, text="📊 Tableau de bord", width=140, fg_color=BTN2,
                      command=lambda: (self.tabs.set("Tableau de bord"), self._on_tab())
                      ).pack(side="right", padx=4)
        ctk.CTkButton(head, text="Lire (test)", width=90, fg_color=BTN2,
                      command=lambda: self.jobs.put(("read", None))).pack(side="right", padx=4)
        ctk.CTkCheckBox(head, text="📌", variable=self.v["always_on_top"], width=44
                        ).pack(side="right", padx=(8, 2))
        self.pause_btn = ctk.CTkButton(head, text="⏸ Pause", width=90, command=self._toggle_pause)
        self.pause_btn.pack(side="right", padx=4)

        # ---------------- onglets
        tabs = ctk.CTkTabview(self, anchor="nw", segmented_button_selected_color="#1f6aa5",
                              command=self._on_tab)
        tabs.grid(row=1, column=0, sticky="nsew", padx=(10, 5), pady=(6, 4))
        self.tabs = tabs
        for name in ("Raccourcis", "Tableau de bord", "Prix", "Mes ventes", "Calibration", "Options"):
            tabs.add(name)
        self._tab_dashboard(ctk.CTkScrollableFrame(tabs.tab("Tableau de bord"), fg_color="transparent"))
        self._tab_shortcuts(ctk.CTkScrollableFrame(tabs.tab("Raccourcis"), fg_color="transparent"), hk)
        self._tab_prices(ctk.CTkScrollableFrame(tabs.tab("Prix"), fg_color="transparent"))
        self._tab_relist(ctk.CTkScrollableFrame(tabs.tab("Mes ventes"), fg_color="transparent"), hk)
        self._tab_calibration(ctk.CTkScrollableFrame(tabs.tab("Calibration"), fg_color="transparent"))
        self._tab_options(ctk.CTkScrollableFrame(tabs.tab("Options"), fg_color="transparent"))

        # ---------------- dernière lecture
        side = ctk.CTkFrame(self, fg_color=CARD)
        side.grid(row=1, column=1, sticky="nsew", padx=(5, 10), pady=(12, 4))
        ctk.CTkLabel(side, text="Dernière lecture", font=ctk.CTkFont(size=14, weight="bold")
                     ).pack(anchor="w", padx=12, pady=(10, 4))
        q = ctk.CTkFrame(side, fg_color="transparent")
        q.pack(fill="x", padx=12)
        ctk.CTkLabel(q, text="Quantité", text_color=MUTED).pack(side="left")
        ctk.CTkLabel(q, textvariable=self.qty_var, font=ctk.CTkFont(size=22, weight="bold"),
                     text_color="#ae81ff").pack(side="left", padx=10)
        grid = ctk.CTkFrame(side, fg_color="#1a1c20")
        grid.pack(fill="x", padx=12, pady=6)
        for c, t in enumerate(("Lot", "Prix", "Par objet")):
            ctk.CTkLabel(grid, text=t, text_color=MUTED).grid(row=0, column=c, sticky="w" if c == 0 else "e",
                                                              padx=10, pady=(6, 2))
        for i, lot in enumerate(self.cfg.lots, start=1):
            ctk.CTkLabel(grid, text=str(lot)).grid(row=i, column=0, sticky="w", padx=10, pady=2)
            ctk.CTkLabel(grid, textvariable=self.read_vars[lot], text_color="#66d9ef",
                         font=ctk.CTkFont(size=14, weight="bold")).grid(row=i, column=1, sticky="e", padx=10)
            ctk.CTkLabel(grid, textvariable=self.unit_vars[lot], text_color=MUTED
                         ).grid(row=i, column=2, sticky="e", padx=10)
        grid.grid_columnconfigure(1, weight=1)
        for label, var in (("Prix moyen", self.avg_var), ("Ton prix", self.mine_var), ("Moteur", self.engine_var)):
            r = ctk.CTkFrame(side, fg_color="transparent")
            r.pack(fill="x", padx=12, pady=1)
            ctk.CTkLabel(r, text=label, text_color=MUTED, width=90, anchor="w").pack(side="left")
            ctk.CTkLabel(r, textvariable=var).pack(side="left")
        ctk.CTkLabel(side, textvariable=self.status_var, text_color=MUTED, wraplength=380,
                     justify="left").pack(anchor="w", padx=12, pady=(8, 10))

        # ---------------- journal
        lf = ctk.CTkFrame(self, fg_color=CARD)
        lf.grid(row=2, column=0, columnspan=2, sticky="nsew", padx=10, pady=(4, 10))
        top = ctk.CTkFrame(lf, fg_color="transparent")
        top.pack(fill="x", padx=8, pady=(6, 0))
        ctk.CTkLabel(top, text="Journal", font=ctk.CTkFont(weight="bold")).pack(side="left", padx=4)
        ctk.CTkButton(top, text="Effacer", width=70, height=24, fg_color=BTN2,
                      command=self._clear_log).pack(side="right")
        body = ctk.CTkFrame(lf, fg_color="transparent")
        body.pack(fill="both", expand=True)
        self.log_text = tk.Text(body, wrap="word", bg="#111418", fg="#EDEDED", relief="flat",
                                font=("Consolas", 10), padx=6, pady=4, height=6,
                                highlightthickness=0, borderwidth=0)
        self.log_text.configure(state="disabled")
        self.log_text.pack(side="left", fill="both", expand=True, padx=(8, 0), pady=6)
        sb = ctk.CTkScrollbar(body, command=self.log_text.yview, height=40)
        sb.pack(side="right", fill="y", padx=(0, 6), pady=6)
        self.log_text.configure(yscrollcommand=sb.set)

    # ---- onglets
    def _tab_shortcuts(self, page, hk):
        page.pack(fill="both", expand=True)
        b = self._section(page, "Vendre (onglet Vente de l'HDV)")
        for key, txt in ((hk["sell"], "Vendre (objet de l'inventaire) OU mettre à jour (une de tes ventes)"),
                         (hk["sell_all"], "Tout vendre : répète la mise en vente (Entrée) tant que c'est sûr"),
                         (hk["optimize"], "Meilleur lot (prix par objet le plus haut)")):
            self._hotkey_line(b, key, txt)
        b = self._section(page, "Mes ventes (liste de tes ventes en cours)")
        self._hotkey_line(b, hk["relist"], "Remettre la vente sélectionnée sous le moins cher")
        self._hotkey_line(b, hk["relist_all"], "Toute la liste (interrupteur dans « Mes ventes »)")
        b = self._section(page, "Divers")
        self._hotkey_line(b, "même touche ×2", "Forcer une lecture jugée suspecte")
        self._hotkey_line(b, hk["pause"], "Pause / reprise (arrête aussi les boucles)")
        self._hotkey_line(b, hk["show_zones"], "Afficher les zones calibrées")
        b = self._section(page, "Vente rapide", "Ce que fait F1 après avoir calculé le prix.")
        ctk.CTkSwitch(b, text="Coller le prix automatiquement", variable=self.v["auto_paste"]).pack(anchor="w", pady=2)
        ctk.CTkSwitch(b, text="Cliquer sur « Prix du lot » avant de coller", variable=self.v["click_field"]
                      ).pack(anchor="w", pady=2)
        ctk.CTkSwitch(b, text="Mettre en vente automatiquement (Entrée) ⚠️", variable=self.v["auto_validate"],
                      progress_color=ORANGE).pack(anchor="w", pady=2)

    def _hotkey_line(self, parent, key: str, text: str):
        r = self._row(parent)
        ctk.CTkLabel(r, text=key.upper(), width=120, corner_radius=6, fg_color="#2b2f36",
                     font=ctk.CTkFont(family="Consolas", weight="bold")).pack(side="left", padx=(2, 10))
        ctk.CTkLabel(r, text=text, anchor="w").pack(side="left")

    def _tab_prices(self, page):
        page.pack(fill="both", expand=True)
        b = self._section(page, "Undercut", "De combien passer sous le moins cher.")
        r = self._row(b)
        ctk.CTkSegmentedButton(r, values=list(UNDERCUT_LABELS.values()), variable=self.v["undercut_mode"]
                               ).pack(side="left")
        ctk.CTkEntry(r, textvariable=self.v["undercut_value"], width=70).pack(side="left", padx=8)
        r = self._row(b)
        ctk.CTkLabel(r, text="Arrondi", width=90, anchor="w").pack(side="left")
        ctk.CTkOptionMenu(r, values=list(ROUNDING_LABELS.values()), variable=self.v["rounding"], width=170
                          ).pack(side="left")
        r = self._row(b)
        ctk.CTkLabel(r, text="Prix min", width=90, anchor="w").pack(side="left")
        ctk.CTkEntry(r, textvariable=self.v["min_price"], width=90).pack(side="left")
        b = self._section(page, "Prix plancher",
                          "Plancher = ce % du « Prix moyen » (zone Prix moyen requise). Protège contre un "
                          "vendeur qui brade. 0 = désactivé.")
        r = self._row(b)
        ctk.CTkEntry(r, textvariable=self.v["floor_ratio"], width=60).pack(side="left")
        ctk.CTkLabel(r, text="% du prix moyen").pack(side="left", padx=6)
        r = self._row(b)
        ctk.CTkLabel(r, text="Concurrent en dessous", width=150, anchor="w").pack(side="left")
        ctk.CTkOptionMenu(r, values=list(FLOOR_LABELS.values()), variable=self.v["floor_mode"], width=170
                          ).pack(side="left")

    def _tab_relist(self, page, hk):
        page.pack(fill="both", expand=True)
        b = self._section(page, f"Toute la liste ({hk['relist_all'].upper()})",
                          "Clique chaque ligne, met à jour, défile et continue. Départ à la ligne sous la "
                          "souris. Le mode le plus risqué vis-à-vis des CGU d'Ankama.")
        ctk.CTkSwitch(b, text="Activer le parcours de toute la liste ⚠️", variable=self.v["relist_auto"],
                      progress_color=ORANGE).pack(anchor="w", pady=2)
        ctk.CTkSwitch(b, text="Valider la fenêtre de confirmation avec Entrée",
                      variable=self.v["relist_confirm_enter"]).pack(anchor="w", pady=2)
        r = self._row(b)
        ctk.CTkLabel(r, text="Défilement", width=120, anchor="w").pack(side="left")
        ctk.CTkSlider(r, from_=0.2, to=1.0, number_of_steps=8, variable=self.v["relist_scroll_page"],
                      width=180, command=lambda _v: self._update_scroll_lbl()).pack(side="left")
        ctk.CTkLabel(r, textvariable=self.scroll_lbl, text_color=MUTED).pack(side="left", padx=8)
        self._update_scroll_lbl()
        r = self._row(b)
        ctk.CTkLabel(r, text="Lignes visibles", width=120, anchor="w").pack(side="left")
        ctk.CTkEntry(r, textvariable=self.v["relist_rows"], width=60).pack(side="left")
        r = self._row(b)
        ctk.CTkLabel(r, text="Lignes max / appui", width=120, anchor="w").pack(side="left")
        ctk.CTkEntry(r, textvariable=self.v["relist_max"], width=60).pack(side="left")
        ctk.CTkLabel(r, text="(garde-fou)", text_color=MUTED).pack(side="left", padx=6)

    def _update_scroll_lbl(self):
        try:
            self.scroll_lbl.set(f"{self.v['relist_scroll_page'].get():.0%} d'une page")
        except tk.TclError:
            pass

    def _tab_calibration(self, page):
        page.pack(fill="both", expand=True)
        top = self._section(page, "Assistant", "Pas à pas, avec une vérification à la fin. Conseillé la "
                                               "première fois ou après un changement d'interface.")
        ctk.CTkButton(top, text="🧭 Ouvrir l'assistant de calibration", width=260,
                      command=self._open_wizard).pack(anchor="w", pady=2)
        b = self._section(page, "Zones et points",
                          f"Bouton = compte à rebours de {self.cfg.calib_countdown}s pour placer la souris "
                          "(zones : coin haut-gauche puis bas-droit). Ou utilise le raccourci en jeu.")
        hk = self.cfg.hotkeys
        self.calib_labels = {}
        items = [
            ("anchor", "Repère : titre « Hôtel de vente » (suivi)",
             hk["calibrate_anchor"] + " ×2", False, lambda: self._calib_rect_ui("anchor", "titre de l'HDV")),
            ("table", "Tableau « Actuellement en vente »", hk["calibrate_table"] + " ×2", True,
             lambda: self._calib_rect_ui("table", "tableau")),
            ("qty", "Menu « Quantité »", hk["calibrate_qty"] + " ×2", True,
             lambda: self._calib_rect_ui("qty", "quantité")),
            ("price_field", "Champ « Prix du lot » (sert aussi à lire ton prix)", hk["calibrate_field"], True,
             lambda: self._countdown("champ Prix du lot", lambda: self._calib_point("price_field"))),
            ("avg", "Prix moyen (plancher, garde-fou)", hk["calibrate_avg"] + " ×2", False,
             lambda: self._calib_rect_ui("avg", "prix moyen")),
            ("count", "Compteur « x/100 lots » (F2 vérifié)", hk["calibrate_count"] + " ×2", False,
             lambda: self._calib_rect_ui("count", "compteur")),
            ("modify_button", "Bouton « Modifier » (sinon Entrée)", hk["calibrate_modify"], False,
             lambda: self._countdown("bouton Modifier", lambda: self._calib_point("modify_button"))),
            ("rows", "Lignes de « mes ventes » (1re puis 2e)", hk["calibrate_rows"] + " ×2", False,
             self._calib_rows_ui),
            ("sell_button", "Bouton « Mettre en vente » (si validation au clic)", hk["calibrate_button"], False,
             lambda: self._countdown("bouton Mettre en vente", lambda: self._calib_point("sell_button"))),
            ("name", "Nom de l'objet (optionnel, déduit sinon)", hk["calibrate_name"] + " ×2", False,
             lambda: self._calib_rect_ui("name", "nom de l'objet")),
            ("mine", "Ton prix (secours) : le champ « Prix du lot »", hk["calibrate_mine"] + " ×2", False,
             lambda: self._calib_rect_ui("mine", "ton prix")),
        ]
        for key, label, hot, required, cmd in items:
            r = self._row(b)
            st = ctk.CTkLabel(r, text="", width=26)
            st.pack(side="left")
            ctk.CTkLabel(r, text=label, anchor="w", width=300).pack(side="left")
            ctk.CTkLabel(r, text=hot.upper(), text_color=MUTED, width=120, anchor="w",
                         font=ctk.CTkFont(family="Consolas")).pack(side="left")
            if not required:
                ctk.CTkButton(r, text="✕", width=28, height=26, fg_color=BTN2,
                              command=lambda k=key: self._clear_zone(k)).pack(side="right", padx=(0, 4))
            ctk.CTkButton(r, text="Calibrer", width=80, height=26, command=cmd).pack(side="right", padx=4)
            self.calib_labels[key] = (st, required)

    def _tab_options(self, page):
        page.pack(fill="both", expand=True)
        b = self._section(page, "Général")
        ctk.CTkSwitch(b, text="Raccourcis actifs seulement quand Dofus a le focus",
                      variable=self.v["require_focus"]).pack(anchor="w", pady=2)
        ctk.CTkSwitch(b, text="Sons", variable=self.v["sound"]).pack(anchor="w", pady=2)
        ctk.CTkSwitch(b, text="Afficher le résultat de chaque action", variable=self.v["toast"]).pack(anchor="w", pady=2)
        ctk.CTkSwitch(b, text="… dans un bandeau fixe au-dessus de l'HDV (sinon popup près de la souris)",
                      variable=self.v["banner"]).pack(anchor="w", pady=2)
        ctk.CTkSwitch(b, text="Fenêtre de l'outil toujours au-dessus du jeu (📌 en haut)",
                      variable=self.v["always_on_top"]).pack(anchor="w", pady=2)
        b = self._section(page, "Sécurité et rapidité")
        ctk.CTkSwitch(b, text="Relire « Prix du lot » avant de valider (jamais un mauvais prix)",
                      variable=self.v["verify_before_enter"]).pack(anchor="w", pady=2)
        ctk.CTkSwitch(b, text="F1 intelligent : vend un objet de l'inventaire OU met à jour une de tes ventes",
                      variable=self.v["smart_f1"]).pack(anchor="w", pady=2)
        b = self._section(page, "Lecture rapide des chiffres",
                          "Apprise toute seule à partir de Tesseract. À réapprendre si tu changes de "
                          "résolution ou de taille d'interface.")
        ctk.CTkSwitch(b, text="Utiliser la lecture rapide", variable=self.v["fast_digits"]).pack(anchor="w", pady=2)
        ctk.CTkButton(b, text="Réapprendre les chiffres", width=180, fg_color=BTN2,
                      command=self._reset_digits).pack(anchor="w", pady=4)
        b = self._section(page, "Nom des objets",
                          "Lu en arrière-plan après chaque action (ne ralentit pas la vente) pour "
                          "l'historique et le tableau de bord. Meilleur avec le français de Tesseract.")
        ctk.CTkSwitch(b, text="Lire le nom des objets", variable=self.v["read_item_names"]).pack(anchor="w", pady=2)

    def _on_tab(self):
        if self.tabs.get() == "Tableau de bord":
            self._refresh_dashboard()

    # ---- tableau de bord (intégré)
    def _tab_dashboard(self, page):
        page.pack(fill="both", expand=True)
        top = ctk.CTkFrame(page, fg_color="transparent")
        top.pack(fill="x", padx=6, pady=(4, 0))
        self.dash_sub = ctk.CTkLabel(top, text="", text_color=MUTED, anchor="w")
        self.dash_sub.pack(side="left")
        ctk.CTkButton(top, text="↻ Actualiser", width=100, height=26, fg_color=BTN2,
                      command=self._refresh_dashboard).pack(side="right")
        tiles = ctk.CTkFrame(page, fg_color="transparent")
        tiles.pack(fill="x", padx=2, pady=4)
        self.dash_tiles = {}
        for i, (key, label) in enumerate((("ventes", "Lots en vente"), ("kamas", "Kamas affichés"),
                                          ("modifs", "Prix modifiés"), ("baisse", "Baisse moy."),
                                          ("suspects", "Suspects"))):
            t = ctk.CTkFrame(tiles, fg_color=CARD)
            t.grid(row=0, column=i, sticky="nsew", padx=3, pady=4)
            tiles.grid_columnconfigure(i, weight=1, uniform="tile")
            ctk.CTkLabel(t, text=label, text_color=MUTED, anchor="w", font=ctk.CTkFont(size=11),
                         wraplength=110, justify="left").pack(anchor="w", padx=8, pady=(6, 0))
            v = ctk.CTkLabel(t, text="—", font=ctk.CTkFont(size=19, weight="bold"), anchor="w")
            v.pack(anchor="w", padx=10)
            s = ctk.CTkLabel(t, text="", text_color=MUTED, font=ctk.CTkFont(size=10), anchor="w",
                             wraplength=110, justify="left")
            s.pack(anchor="w", padx=8, pady=(0, 6))
            self.dash_tiles[key] = (v, s)
        # ---- prix par objet
        b = self._section(page, "Prix par objet", "Prix par objet dans le temps : le moins cher lu à l'HDV "
                                                  "et ton prix. Survole la courbe pour le détail.")
        r = self._row(b)
        self.item_var = ctk.StringVar(value="")
        self.item_menu = ctk.CTkOptionMenu(r, values=["—"], variable=self.item_var, width=320,
                                           dynamic_resizing=False, command=lambda _v: self._draw_item_chart())
        self.item_menu.pack(side="left")
        self.item_info = ctk.CTkLabel(r, text="", text_color=MUTED)
        self.item_info.pack(side="left", padx=10)
        self.item_cv = tk.Canvas(b, height=200, bg=CARD, highlightthickness=0)
        self.item_cv.pack(fill="x", expand=True, pady=(4, 0))
        self.item_cv.bind("<Configure>", lambda _e: self._draw_item_chart())
        self.item_cv.bind("<Motion>", self._item_hover)
        self.item_cv.bind("<Leave>", lambda _e: self.item_cv.delete("hover"))
        b = self._section(page, "Objets", "Les plus actifs en premier.")
        self.items_text = tk.Text(b, height=8, bg="#1a1c20", fg="#EDEDED", relief="flat",
                                  font=("Consolas", 9), highlightthickness=0, wrap="none")
        self.items_text.pack(fill="x")
        self.items_text.configure(state="disabled")
        self.dash_items = {}
        self._item_pts = []

        self.dash_charts = {}
        for key, title, note in (("ventes", "Lots mis en vente par jour", "F1 / F2 avec mise en vente"),
                                 ("kamas", "Kamas mis en vente par jour", "Somme des prix affichés"),
                                 ("modifs", "Prix modifiés par jour", "F3 / Ctrl+F3"),
                                 ("heures", "Activité par heure", "Ventes + modifications"),
                                 ("lots", "Mises en vente par taille de lot", "")):
            b = self._section(page, title, note)
            cv = tk.Canvas(b, height=170, bg=CARD, highlightthickness=0)
            cv.pack(fill="x", expand=True)
            cv.bind("<Configure>", lambda _e, k=key: self._redraw_chart(k))
            self.dash_charts[key] = (cv, [], [], "")
        b = self._section(page, "Dernières actions")
        self.dash_recent = tk.Text(b, height=12, bg="#1a1c20", fg="#EDEDED", relief="flat",
                                   font=("Consolas", 9), highlightthickness=0, wrap="none")
        self.dash_recent.pack(fill="x")
        self.dash_recent.configure(state="disabled")

    def _refresh_dashboard(self):
        import dofus_dashboard as dash
        try:
            data = dash.compute(dash.load_rows())
        except Exception as e:
            self.dash_sub.configure(text=f"Historique illisible : {e}")
            return
        c = data["count"]
        f = dash.fmt
        period = (f"Historique du {data['first']:%d/%m/%Y} au {data['last']:%d/%m/%Y} · "
                  f"{f(len(data['rows']))} lignes" if data["first"] else "Pas encore d'historique.")
        self.dash_sub.configure(text=period)
        vals = {
            "ventes": (f(c["vente"]), ""),
            "kamas": (f(data["kamas"]), "prix affichés, pas des ventes conclues"),
            "modifs": (f(c["modif"]), "F3 / Ctrl+F3"),
            "baisse": ((f(data["drop"]) + " %") if data["drop"] is not None else "—", "sous le moins cher lu"),
            "suspects": (f(c["suspect"]), (f(data["suspect_rate"]) + " % des actions")
                         if data["suspect_rate"] is not None else ""),
        }
        for k, (v, s) in vals.items():
            self.dash_tiles[k][0].configure(text=v)
            self.dash_tiles[k][1].configure(text=s)
        days = data["days"]
        dl = [d[8:10] + "/" + d[5:7] for d in days]
        lots = sorted(data["lots"])
        series = {
            "ventes": (dl, [v["ventes"] for v in days.values()], "lots"),
            "kamas": (dl, [v["kamas"] for v in days.values()], "kamas"),
            "modifs": (dl, [v["modifs"] for v in days.values()], "modifications"),
            "heures": ([f"{h}h" for h in range(24)], [data["hours"].get(h, 0) for h in range(24)], "actions"),
            "lots": ([f"lot {l}" for l in lots], [data["lots"][l] for l in lots], "lots"),
        }
        for k, (labels, values, unit) in series.items():
            cv = self.dash_charts[k][0]
            self.dash_charts[k] = (cv, labels, values, unit)
            self._redraw_chart(k)
        # objets
        self.dash_items = data["items"]
        names = list(self.dash_items) or ["—"]
        self.item_menu.configure(values=names)
        if self.item_var.get() not in self.dash_items:
            self.item_var.set(names[0])
        self._draw_item_chart()
        lines = [f"{'Objet':32} {'Ventes':>6} {'Modifs':>6} {'Moins cher (dernier, /u)':>25}"]
        for n, it in list(self.dash_items.items())[:40]:
            low = it["last_low"]
            lines.append(f"{n[:32]:32} {it['ventes']:>6} {it['modifs']:>6} "
                         f"{(f'{low:,.1f}'.replace(',', ' ') if low else '—'):>25}")
        if not self.dash_items:
            lines.append("Aucun nom d'objet encore lu (les prochaines actions le noteront).")
        self.items_text.configure(state="normal")
        self.items_text.delete("1.0", "end")
        self.items_text.insert("end", "\n".join(lines))
        self.items_text.configure(state="disabled")

        rows = [r for r in data["rows"] if dash.kind(r) != "vu"][-60:][::-1]
        lines = [f"{'Date':19}  {'Action':14} {'Objet':24} {'Lot':>4} {'Prix lu':>9} {'Nouveau':>9}  Statut"]
        for r in rows:
            lines.append(f"{r['datetime']:19}  {dash.LABELS[dash.kind(r)]:14} {r.get('item', '')[:24]:24} "
                         f"{r.get('lot', ''):>4} "
                         f"{f(dash._int(r.get('read_price'))):>9} {f(dash._int(r.get('new_price'))):>9}  "
                         f"{r.get('status', '')}")
        self.dash_recent.configure(state="normal")
        self.dash_recent.delete("1.0", "end")
        self.dash_recent.insert("end", "\n".join(lines))
        self.dash_recent.configure(state="disabled")

    def _draw_item_chart(self):
        cv = self.item_cv
        cv.delete("all")
        self._item_pts = []
        it = self.dash_items.get(self.item_var.get())
        w, h = max(240, cv.winfo_width()), int(cv.cget("height"))
        if not it or len(it["points"]) < 1:
            cv.create_text(12, h / 2, text="Pas encore de prix pour cet objet.", fill=MUTED, anchor="w")
            self.item_info.configure(text="")
            return
        pts = it["points"]
        self.item_info.configure(text=f"{len(pts)} relevés · {it['ventes']} ventes · {it['modifs']} modifs")
        vals = [p[1] for p in pts] + [p[2] for p in pts if p[2]]
        lo, hi = min(vals), max(vals)
        pad = (hi - lo) * 0.1 or max(1.0, hi * 0.05)
        lo, hi = max(0.0, lo - pad), hi + pad
        left, right, top, bottom = 60, 120, 24, 24
        pw, ph = w - left - right, h - top - bottom
        t0, t1 = pts[0][0], pts[-1][0]
        span = max(1, t1 - t0)
        X = (lambda t: left + pw * (t - t0) / span) if len(pts) > 1 else (lambda t: left + pw / 2)
        Y = lambda v: top + ph - ph * (v - lo) / (hi - lo)
        for i in range(5):
            v = lo + (hi - lo) * i / 4
            cv.create_line(left, Y(v), left + pw, Y(v), fill="#33332f")
            cv.create_text(left - 6, Y(v), text=f"{v:,.0f}".replace(",", " "), fill=MUTED, anchor="e",
                           font=("Segoe UI", 8))
        from datetime import datetime as _dt
        for t in (t0, t1) if len(pts) > 1 else (t0,):
            cv.create_text(X(t), h - 8, text=_dt.fromtimestamp(t).strftime("%d/%m %Hh"), fill=MUTED,
                           font=("Segoe UI", 8))
        series = (("Moins cher lu", "#3987e5", [(p[0], p[1]) for p in pts]),
                  ("Ton prix", "#d95926", [(p[0], p[2]) for p in pts if p[2]]))
        # légende (2 séries)
        lx = left
        for label, color, _ser in series:
            cv.create_oval(lx, 6, lx + 10, 16, fill=color, outline="")
            cv.create_text(lx + 14, 11, text=label, fill="#c3c2b7", anchor="w", font=("Segoe UI", 9))
            lx += 120
        ends = []
        dots = len(pts) <= 60
        for label, color, ser in series:
            if not ser:
                continue
            xy = [(X(t), Y(v)) for t, v in ser]
            if len(xy) > 1:
                cv.create_line(*[c for p in xy for c in p], fill=color, width=2)
            if dots or len(xy) == 1:
                for x, y in xy:
                    cv.create_oval(x - 4, y - 4, x + 4, y + 4, fill=color, outline=CARD, width=2)
            ends.append([xy[-1][1], f"{label} {ser[-1][1]:,.0f}".replace(",", " ")])
        # libellés directs en bout de courbe, écartés s'ils se chevauchent
        ends.sort()
        for i in range(1, len(ends)):
            if ends[i][0] - ends[i - 1][0] < 14:
                ends[i][0] = ends[i - 1][0] + 14
        for y, text in ends:
            cv.create_text(left + pw + 8, y, text=text, fill="#c3c2b7", anchor="w", font=("Segoe UI", 9))
        self._item_pts = [(X(p[0]), p) for p in pts]

    def _item_hover(self, e):
        cv = self.item_cv
        cv.delete("hover")
        if not self._item_pts:
            return
        x, p = min(self._item_pts, key=lambda q: abs(q[0] - e.x))
        if abs(x - e.x) > 30:
            return
        from datetime import datetime as _dt
        h = int(cv.cget("height"))
        cv.create_line(x, 24, x, h - 24, fill="#8f8e86", dash=(2, 2), tags="hover")
        txt = (f"{_dt.fromtimestamp(p[0]):%d/%m %H:%M} · moins cher {p[1]:,.1f}/u"
               + (f" · toi {p[2]:,.1f}/u" if p[2] else "")).replace(",", " ")
        cv.create_text(min(x + 8, cv.winfo_width() - 8), 26, text=txt, fill="#f0efec",
                       anchor="nw" if x + 8 < cv.winfo_width() - 260 else "ne", font=("Segoe UI", 9, "bold"),
                       tags="hover")

    def _redraw_chart(self, key: str):
        cv, labels, values, unit = self.dash_charts[key]
        color = DASH_COLORS.get(key, "#3987e5")
        cv.delete("all")
        w, h = max(200, cv.winfo_width()), int(cv.cget("height"))
        if not values or max(values) == 0:
            cv.create_text(12, h / 2, text="Pas encore de données.", fill=MUTED, anchor="w")
            return
        left, right, top, bottom = 56, 10, 22, 22
        pw, ph = w - left - right, h - top - bottom
        vmax = max(values)
        step = _nice_step(vmax)
        vmax = step * ((vmax + step - 1) // step)
        for v in range(0, vmax + 1, step):
            y = top + ph - ph * v / vmax
            cv.create_line(left, y, w - right, y, fill="#33332f")
            cv.create_text(left - 6, y, text=_fmt_num(v), fill=MUTED, anchor="e", font=("Segoe UI", 8))
        n = len(values)
        slot = pw / n
        bw = max(3, min(34, slot - 2))
        every = max(1, n // 8)
        tip = cv.create_text(w - right, 4, text="", fill="#f0efec", anchor="ne", font=("Segoe UI", 9, "bold"))
        for i, (lab, v) in enumerate(zip(labels, values)):
            x = left + i * slot + (slot - bw) / 2
            bh = ph * v / vmax
            text = f"{lab} : {_fmt_num(v)} {unit}"
            hit = cv.create_rectangle(left + i * slot, top, left + (i + 1) * slot, top + ph,
                                      fill="", outline="")
            bar = cv.create_rectangle(x, top + ph - bh, x + bw, top + ph, fill=color, outline="") if bh > 0 else None
            for item in (hit, bar):
                if item:
                    cv.tag_bind(item, "<Enter>", lambda _e, t=text: cv.itemconfigure(tip, text=t))
                    cv.tag_bind(item, "<Leave>", lambda _e: cv.itemconfigure(tip, text=""))
            if i % every == 0:
                cv.create_text(x + bw / 2, h - 8, text=lab, fill=MUTED, font=("Segoe UI", 8))
        cv.create_line(left, top + ph, w - right, top + ph, fill="#8f8e86")

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
            if c.read_item_names:
                img = core.grab_name(c)
                name = core.name_reader().read(img) if img is not None else ""
                out.append(f"{'✓' if name else '–'} Nom de l'objet : {name or 'non lu'}")
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

    def _clear_log(self):
        self.log_text.configure(state="normal")
        self.log_text.delete("1.0", "end")
        self.log_text.configure(state="disabled")

    def _setup_log_tags(self):
        for tag, color in TAG_COLORS.items():
            self.log_text.tag_configure(tag, foreground=color)

    def _log(self, msg: str, tag: str = "INFO"):
        self.log_text.configure(state="normal")
        self.log_text.insert("end", time.strftime("%H:%M:%S") + "  ", ("TIME",))
        self.log_text.insert("end", msg + "\n", (tag,))
        if int(self.log_text.index("end-1c").split(".")[0]) > 500:
            self.log_text.delete("1.0", "100.0")
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

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
                     "relist_auto", "relist_confirm_enter", "fast_digits", "read_item_names",
                     "banner", "verify_before_enter", "smart_f1", "always_on_top"):
            setattr(c, name, bool(v[name].get()))
        self._apply_topmost()
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

        def game_job(job):
            def cb():
                if self.engine.paused:
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
            keyboard.add_hotkey(hk["sell"], game_job(("sell", False)))
            keyboard.add_hotkey(hk["optimize"], game_job(("sell", True)))
            keyboard.add_hotkey(hk["sell_all"], game_job(("sell_all", None)))
            keyboard.add_hotkey(hk["relist"], game_job(("relist", None)))
            keyboard.add_hotkey(hk["relist_all"], game_job(("relist_all", None)))
            keyboard.add_hotkey(hk["calibrate_mine"], lambda: self.jobs.put(("calib_rect", "mine")))
            keyboard.add_hotkey(hk["calibrate_modify"], lambda: self.jobs.put(("calib_point", "modify_button")))
            keyboard.add_hotkey(hk["calibrate_rows"], lambda: self.jobs.put(("calib_rows", None)))
            keyboard.add_hotkey(hk["calibrate_anchor"], lambda: self.jobs.put(("calib_rect", "anchor")))
            keyboard.add_hotkey(hk["calibrate_name"], lambda: self.jobs.put(("calib_rect", "name")))
            keyboard.add_hotkey(hk["calibrate_table"], lambda: self.jobs.put(("calib_rect", "table")))
            keyboard.add_hotkey(hk["calibrate_qty"], lambda: self.jobs.put(("calib_rect", "qty")))
            keyboard.add_hotkey(hk["calibrate_avg"], lambda: self.jobs.put(("calib_rect", "avg")))
            keyboard.add_hotkey(hk["calibrate_count"], lambda: self.jobs.put(("calib_rect", "count")))
            keyboard.add_hotkey(hk["calibrate_field"], lambda: self.jobs.put(("calib_point", "price_field")))
            keyboard.add_hotkey(hk["calibrate_button"], lambda: self.jobs.put(("calib_point", "sell_button")))
            keyboard.add_hotkey(hk["show_zones"], lambda: self.ui_events.put(("zones", None)))
            keyboard.add_hotkey(hk["pause"], lambda: self.ui_events.put(("pause", None)))
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
                    self.ui_events.put(("result", self.engine.sell_all()))
                elif name == "relist":
                    self.ui_events.put(("result", self.engine.relist()))
                elif name == "relist_all":
                    self.ui_events.put(("log", ("[MAJ TOUT] Parcours de la liste… "
                                                f"{self.cfg.hotkeys['pause']} pour arrêter.", "WARN")))
                    self.ui_events.put(("result", self.engine.relist_all()))
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
            except Exception as e:
                self.ui_events.put(("log", (f"[Erreur] {e}", "ERROR")))
            msg, self.engine.last_anchor_msg = self.engine.last_anchor_msg, ""
            if msg:
                self.ui_events.put(("log", (f"[Repère] {msg}", "CAL" if "recalées" in msg else "WARN")))
                self.ui_events.put(("refresh", None))

    def _poll_ui(self):
        try:
            while True:
                name, arg = self.ui_events.get_nowait()
                if name == "result":
                    self._on_result(arg)
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
        core.beep(res.level, self.cfg)
        if self.cfg.toast:
            head = f"Lot {res.lot} → {fmt(res.new_price)}" if res.new_price is not None else "Pas de prix"
            if res.message.startswith("[TOUT]"):
                head += f"  {res.hint}"
            if self.cfg.banner:
                self._banner(head, res.hint or res.level, LEVEL_COLORS[res.level])
            else:
                self._toast(head, res.hint or res.level, LEVEL_COLORS[res.level])

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
        if getattr(self, "tabs", None) and self.tabs.get() == "Tableau de bord":
            self._refresh_dashboard()

    def _show_screen(self, sr: core.ScreenRead):
        if not sr.prices and sr.selected is None:
            return
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

    # ------------------------------------------------------------- overlays
    def _toast(self, head: str, sub: str, color: str, ms: int = 1800):
        try:
            x, y = core.mouse_position()
        except Exception:
            x, y = self.winfo_pointerx(), self.winfo_pointery()
        t = tk.Toplevel(self)
        t.overrideredirect(True)
        t.attributes("-topmost", True)
        try:
            t.attributes("-alpha", 0.92)
        except tk.TclError:
            pass
        frame = tk.Frame(t, bg="#1e1f22", highlightbackground=color, highlightthickness=2)
        frame.pack()
        tk.Label(frame, text=head, bg="#1e1f22", fg="#ffffff",
                 font=("Segoe UI", 13, "bold")).pack(padx=10, pady=(6, 0))
        tk.Label(frame, text=sub, bg="#1e1f22", fg=color, font=("Segoe UI", 9)).pack(padx=10, pady=(0, 6))
        t.geometry(f"+{x + 18}+{y + 18}")
        t.after(ms, t.destroy)

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
        if c.anchor_region:
            x, y = c.anchor_region[0] - 40, c.anchor_region[1] - 50
        elif c.price_field:
            x, y = c.price_field[0] - 80, c.price_field[1] - 200
        elif c.table_region:
            x, y = c.table_region[0], c.table_region[1] - 60
        else:
            return self._toast(head, sub, color)
        b = getattr(self, "_banner_win", None)
        if b is None or not b.winfo_exists():
            b = tk.Toplevel(self)
            b.overrideredirect(True)
            b.attributes("-topmost", True)
            frame = tk.Frame(b, bg="#1e1f22")
            frame.pack()
            self._banner_bar = tk.Frame(frame, bg=color, width=6)
            self._banner_bar.pack(side="left", fill="y")
            self._banner_head = tk.Label(frame, bg="#1e1f22", fg="#ffffff", font=("Segoe UI", 12, "bold"))
            self._banner_head.pack(side="left", padx=(10, 6), pady=6)
            self._banner_sub = tk.Label(frame, bg="#1e1f22", font=("Segoe UI", 10))
            self._banner_sub.pack(side="left", padx=(0, 12))
            self._banner_win = b
        try:
            b.attributes("-alpha", 0.95)
        except tk.TclError:
            pass
        self._banner_bar.configure(bg=color)
        self._banner_head.configure(text=head)
        self._banner_sub.configure(text=sub, fg=color)
        b.geometry(f"+{max(0, int(x))}+{max(0, int(y))}")
        b.deiconify()
        b.lift()
        if getattr(self, "_banner_after", None):
            self.after_cancel(self._banner_after)
        self._banner_after = self.after(ms, lambda: b.winfo_exists() and b.withdraw())

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
         "Objet sélectionné. À faire SEULEMENT si les noms sont mal lus dans le tableau de bord : "
         "sinon la zone est déduite du champ « Prix du lot ».",
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
                                      text_color="#66d9ef")
        self._wiz_prep.pack(fill="x", padx=16)
        self._wiz_text = ctk.CTkLabel(w, text="", wraplength=520, justify="left", anchor="w")
        self._wiz_text.pack(fill="x", padx=16, pady=(8, 0))
        self._wiz_state = ctk.CTkLabel(w, text="", anchor="w", font=ctk.CTkFont(weight="bold"))
        self._wiz_state.pack(fill="x", padx=16, pady=(10, 0))
        self._wiz_msg = ctk.CTkLabel(w, text="", anchor="w", text_color="#e6db74", wraplength=520,
                                     justify="left")
        self._wiz_msg.pack(fill="x", padx=16, pady=(4, 0))
        self._wiz_report = ctk.CTkTextbox(w, height=150, font=("Consolas", 11))
        bar = ctk.CTkFrame(w, fg_color="transparent")
        bar.pack(side="bottom", fill="x", padx=16, pady=12)
        self._wiz_back = ctk.CTkButton(bar, text="← Retour", width=90, fg_color=BTN2, command=lambda: self._wiz_go(-1))
        self._wiz_back.pack(side="left")
        self._wiz_next = ctk.CTkButton(bar, text="Suivant →", width=110, command=lambda: self._wiz_go(1))
        self._wiz_next.pack(side="right")
        self._wiz_do = ctk.CTkButton(bar, text="Calibrer", width=130, command=self._wiz_calibrate)
        self._wiz_do.pack(side="right", padx=8)
        ctk.CTkButton(bar, text="Voir zones", width=90, fg_color=BTN2, command=self._show_zones
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
                                      text_color="#2ecc71" if ok else "#e74c3c")
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
        self.status_var.set(f"Calibration {label} dans {n}s… place la souris !")
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
            hint = core.zone_hint(name, val)
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

    def _refresh_status(self):
        c = self.cfg
        paused = self.engine.paused
        self.state_pill.configure(text="⏸ Pause" if paused else "● Actif",
                                  fg_color="#7a4b12" if paused else "#1e5631")
        self.pause_btn.configure(text="▶ Reprendre" if paused else "⏸ Pause")
        try:
            n = len(core.digit_reader().known())
            self.digits_var.set(f"Chiffres appris {n}/10" + ("  ✓" if n == 10 else ""))
        except Exception:
            self.digits_var.set("")
        st = core.ENGINE_STATS
        tot = st.get("chiffres", 0) + st.get("tesseract", 0)
        fast = f"  |  lecture rapide {st.get('chiffres', 0) * 100 // tot}%" if tot else ""
        self.stats_var.set(f"Session : {self.stats['ventes']} ventes  |  {self.stats['modifs']} modifs"
                           f"  |  {self.stats['suspects']} suspects{fast}")
        values = {"table": c.table_region, "qty": c.qty_region, "price_field": c.price_field,
                  "avg": c.avg_region, "count": c.count_region, "modify_button": c.modify_button,
                  "rows": c.relist_row, "sell_button": c.sell_button, "mine": c.mine_region,
                  "anchor": c.anchor_region, "name": c.name_region}
        names = {"table": "tableau", "qty": "quantité", "price_field": "Prix du lot"}
        missing = []
        for key, (lbl, required) in getattr(self, "calib_labels", {}).items():
            ok = bool(values.get(key))
            lbl.configure(text="✓" if ok else ("✗" if required else "–"),
                          text_color="#2ecc71" if ok else ("#e74c3c" if required else MUTED))
            if required and not ok:
                missing.append(names[key])
        self.status_var.set(("À calibrer : " + ", ".join(missing) + " (onglet Calibration)")
                            if missing else "Calibration de base OK.")

    def _on_close(self):
        self._apply_settings()
        core.flush_history(3.0)  # noms d'objets en cours de lecture : on les écrit avant de quitter
        if KEYBOARD_AVAILABLE:
            try:
                keyboard.unhook_all()
            except Exception:
                pass
        self.destroy()


if __name__ == "__main__":
    App().mainloop()
