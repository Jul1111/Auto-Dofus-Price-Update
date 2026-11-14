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
LEVEL_COLORS = {"ok": "#2ecc71", "warn": "#f1c40f", "error": "#e74c3c"}
ZONE_COLORS = {"table": "#66d9ef", "qty": "#ae81ff", "avg": "#a6e22e", "count": "#fd971f",
               "mine": "#f92672"}
ZONE_LABELS = {"table": "Tableau", "qty": "Quantité", "avg": "Prix moyen", "count": "Compteur",
               "mine": "Ton prix"}
FLOOR_LABELS = {"floor": "au plancher", "keep": "garder mon prix", "stop": "arrêt (suspect)"}
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
        self.geometry("1040x700")

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
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    # ------------------------------------------------------------------ UI
    def _build_vars(self):
        c = self.cfg
        self.v = {
            "undercut_mode": ctk.StringVar(value=c.undercut_mode),
            "undercut_value": ctk.StringVar(value=f"{c.undercut_value:g}"),
            "rounding": ctk.StringVar(value=c.rounding),
            "min_price": ctk.StringVar(value=str(c.min_price)),
            "floor_mode": ctk.StringVar(value=FLOOR_LABELS.get(c.floor_mode, FLOOR_LABELS["floor"])),
            "floor_ratio": ctk.StringVar(value=f"{c.floor_ratio * 100:g}"),
            "auto_paste": ctk.BooleanVar(value=c.auto_paste),
            "click_field": ctk.BooleanVar(value=c.click_field),
            "auto_validate": ctk.BooleanVar(value=c.auto_validate),
            "require_focus": ctk.BooleanVar(value=c.require_focus),
            "sound": ctk.BooleanVar(value=c.sound),
            "toast": ctk.BooleanVar(value=c.toast),
            "relist_auto": ctk.BooleanVar(value=c.relist_auto),
        }
        for var in self.v.values():
            var.trace_add("write", lambda *_: self._schedule_save())
        self.status_var = ctk.StringVar(value="")
        self.qty_var = ctk.StringVar(value="-")
        self.read_vars = {lot: ctk.StringVar(value="-") for lot in self.cfg.lots}

    def _build_ui(self):
        hk = self.cfg.hotkeys

        # --- Prix
        top = ctk.CTkFrame(self)
        top.pack(fill="x", padx=12, pady=(12, 4))
        ctk.CTkLabel(top, text="Undercut").pack(side="left", padx=(8, 4))
        ctk.CTkOptionMenu(top, values=["fixed", "percent"], variable=self.v["undercut_mode"],
                          width=100).pack(side="left")
        ctk.CTkEntry(top, textvariable=self.v["undercut_value"], width=60).pack(side="left", padx=(4, 14))
        ctk.CTkLabel(top, text="Arrondi").pack(side="left", padx=(0, 4))
        ctk.CTkOptionMenu(top, values=["none", "down_10", "down_100", "end_9"],
                          variable=self.v["rounding"], width=110).pack(side="left", padx=(0, 14))
        ctk.CTkLabel(top, text="Prix min").pack(side="left", padx=(0, 4))
        ctk.CTkEntry(top, textvariable=self.v["min_price"], width=70).pack(side="left", padx=(0, 14))

        fl = ctk.CTkFrame(self)
        fl.pack(fill="x", padx=12, pady=4)
        ctk.CTkLabel(fl, text="Prix plancher :", font=ctk.CTkFont(weight="bold")).pack(side="left", padx=8)
        ctk.CTkEntry(fl, textvariable=self.v["floor_ratio"], width=50).pack(side="left")
        ctk.CTkLabel(fl, text="% du prix moyen  |  concurrent en dessous :").pack(side="left", padx=(4, 4))
        ctk.CTkOptionMenu(fl, values=list(FLOOR_LABELS.values()), variable=self.v["floor_mode"],
                          width=150).pack(side="left")
        ctk.CTkLabel(fl, text="(nécessite la zone Prix moyen)", text_color="#888").pack(side="left", padx=8)

        # --- Vente rapide
        fast = ctk.CTkFrame(self)
        fast.pack(fill="x", padx=12, pady=4)
        ctk.CTkLabel(fast, text="Vente rapide :", font=ctk.CTkFont(weight="bold")).pack(side="left", padx=8)
        ctk.CTkSwitch(fast, text="Coller auto", variable=self.v["auto_paste"]).pack(side="left", padx=6)
        ctk.CTkSwitch(fast, text="Cliquer « Prix du lot »", variable=self.v["click_field"]).pack(side="left", padx=6)
        ctk.CTkSwitch(fast, text="Mettre en vente auto", variable=self.v["auto_validate"],
                      progress_color="#e67e22").pack(side="left", padx=6)

        opts = ctk.CTkFrame(self)
        opts.pack(fill="x", padx=12, pady=4)
        ctk.CTkSwitch(opts, text="Actif seulement quand Dofus a le focus",
                      variable=self.v["require_focus"]).pack(side="left", padx=8)
        ctk.CTkSwitch(opts, text="Sons", variable=self.v["sound"]).pack(side="left", padx=6)
        ctk.CTkSwitch(opts, text="Popup près de la souris", variable=self.v["toast"]).pack(side="left", padx=6)

        # --- Calibration
        cal = ctk.CTkFrame(self)
        cal.pack(fill="x", padx=12, pady=4)
        ctk.CTkLabel(cal, text=f"Calibration ({self.cfg.calib_countdown}s pour placer la souris) :"
                     ).pack(side="left", padx=8)
        ctk.CTkButton(cal, text="Tableau (2 coins)", width=130,
                      command=lambda: self._calib_rect_ui("table", "tableau")).pack(side="left", padx=3)
        ctk.CTkButton(cal, text="Quantité (2 coins)", width=130,
                      command=lambda: self._calib_rect_ui("qty", "quantité")).pack(side="left", padx=3)
        ctk.CTkButton(cal, text="Prix moyen", width=90,
                      command=lambda: self._calib_rect_ui("avg", "prix moyen")).pack(side="left", padx=3)
        ctk.CTkButton(cal, text="Compteur lots", width=105,
                      command=lambda: self._calib_rect_ui("count", "compteur")).pack(side="left", padx=3)
        ctk.CTkButton(cal, text="Prix du lot", width=95,
                      command=lambda: self._countdown("champ Prix du lot",
                                                      lambda: self._calib_point("price_field"))
                      ).pack(side="left", padx=3)
        ctk.CTkButton(cal, text="Mettre en vente", width=115,
                      command=lambda: self._countdown("bouton Mettre en vente",
                                                      lambda: self._calib_point("sell_button"))
                      ).pack(side="left", padx=3)
        ctk.CTkButton(cal, text="Voir zones", width=90, fg_color="#555",
                      command=self._show_zones).pack(side="left", padx=3)

        rl = ctk.CTkFrame(self)
        rl.pack(fill="x", padx=12, pady=4)
        ctk.CTkLabel(rl, text="Mes ventes (F3) :").pack(side="left", padx=8)
        ctk.CTkButton(rl, text="Ton prix (optionnel)", width=140,
                      command=lambda: self._calib_rect_ui("mine", "ton prix")).pack(side="left", padx=3)
        ctk.CTkButton(rl, text="Modifier", width=90,
                      command=lambda: self._countdown("bouton Modifier",
                                                      lambda: self._calib_point("modify_button"))
                      ).pack(side="left", padx=3)
        ctk.CTkButton(rl, text="Lignes (1re puis 2e)", width=140,
                      command=self._calib_rows_ui).pack(side="left", padx=3)
        ctk.CTkSwitch(rl, text=f"{self.cfg.hotkeys['relist_all'].upper()} : toute la liste ⚠️",
                      variable=self.v["relist_auto"]).pack(side="left", padx=10)

        # --- Statut + dernières lectures
        st = ctk.CTkFrame(self)
        st.pack(fill="x", padx=12, pady=4)
        ctk.CTkLabel(st, textvariable=self.status_var).pack(side="left", padx=8)
        ctk.CTkButton(st, text="Pause", width=70, command=self._toggle_pause).pack(side="left", padx=4)
        ctk.CTkButton(st, text="Lire (test)", width=90, fg_color="#555",
                      command=lambda: self.jobs.put(("read", None))).pack(side="left", padx=4)

        rd = ctk.CTkFrame(self)
        rd.pack(fill="x", padx=12, pady=4)
        ctk.CTkLabel(rd, text="Quantité affichée :").pack(side="left", padx=(8, 4))
        ctk.CTkLabel(rd, textvariable=self.qty_var, font=ctk.CTkFont(size=15, weight="bold"),
                     text_color="#ae81ff").pack(side="left", padx=(0, 16))
        for lot in self.cfg.lots:
            ctk.CTkLabel(rd, text=f"Lot {lot} :").pack(side="left", padx=(8, 2))
            ctk.CTkLabel(rd, textvariable=self.read_vars[lot], text_color="#66d9ef").pack(side="left")

        # --- Log
        lf = ctk.CTkFrame(self)
        lf.pack(fill="both", expand=True, padx=12, pady=(4, 6))
        self.log_text = tk.Text(lf, wrap="word", bg="#111418", fg="#EDEDED", relief="flat")
        self.log_text.configure(state="disabled")
        self.log_text.pack(side="left", fill="both", expand=True, padx=(6, 0), pady=6)
        sb = ctk.CTkScrollbar(lf, command=self.log_text.yview)
        sb.pack(side="right", fill="y", padx=(0, 6), pady=6)
        self.log_text.configure(yscrollcommand=sb.set)

        ctk.CTkLabel(self, text_color="#AFAFAF", text=(
            f"{hk['sell'].upper()}=vendre  |  {hk['sell_all'].upper()}=tout vendre  |  {hk['optimize'].upper()}=meilleur lot  |  "
            f"même touche 2× = forcer  |  {hk['show_zones']}=voir zones  |  {hk['pause']}=pause"
        )).pack(pady=(0, 8))

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
        c.undercut_mode = v["undercut_mode"].get()
        c.rounding = v["rounding"].get()
        c.floor_mode = {lbl: k for k, lbl in FLOOR_LABELS.items()}.get(v["floor_mode"].get(), "floor")
        was_auto = c.relist_auto
        for name in ("auto_paste", "click_field", "auto_validate", "require_focus", "sound", "toast",
                     "relist_auto"):
            setattr(c, name, bool(v[name].get()))
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
                self.jobs.put(job)
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
            name, arg = self.jobs.get()
            try:
                if name == "sell":
                    self.ui_events.put(("result", self.engine.sell(optimize=arg)))
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
                elif name == "calib_rect":
                    self.ui_events.put(("calib_rect", (arg, self.engine.calibrate_rect(arg))))
                elif name == "calib_point":
                    self.ui_events.put(("calib_point", (arg, self.engine.calibrate_point(arg))))
            except Exception as e:
                self.ui_events.put(("log", (f"[Erreur] {e}", "ERROR")))

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
                    if self.cfg.mine_region:
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
        except queue.Empty:
            pass
        self.after(30, self._poll_ui)

    # ------------------------------------------------------------- results
    def _on_result(self, res: core.Result):
        self._show_screen(res.screen)
        tag = {"warn": "WARN", "error": "ERROR"}.get(res.level) or (
            "OPT" if res.message.startswith("[OPT]") else "OK")
        self._log(res.message, tag)
        core.beep(res.level, self.cfg)
        if self.cfg.toast:
            head = f"Lot {res.lot} → {fmt(res.new_price)}" if res.new_price is not None else "Pas de prix"
            if res.message.startswith("[TOUT]"):
                head += f"  {res.hint}"
            self._toast(head, res.hint or res.level, LEVEL_COLORS[res.level])

    def _show_screen(self, sr: core.ScreenRead):
        if not sr.prices and sr.selected is None:
            return
        self.qty_var.set(str(sr.selected) if sr.selected else "?")
        for lot, var in self.read_vars.items():
            r = sr.prices.get(lot)
            if r and r.value is not None:
                var.set(f"{fmt(r.value)} ({r.value / lot:,.0f}/u)".replace(",", " "))
            else:
                var.set("—")

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
        marks = [("Tableau", c.table_region), ("Quantité", c.qty_region),
                 ("Prix du lot", c.price_field), ("Mettre en vente", c.sell_button),
                 ("Prix moyen", c.avg_region), ("Compteur", c.count_region),
                 ("Ton prix", c.mine_region)]
        state = "⏸ PAUSE" if self.engine.paused else "● Actif"
        self.status_var.set(state + "  |  " + "  ".join(f"{n} {'✓' if v else '✗'}" for n, v in marks))

    def _on_close(self):
        self._apply_settings()
        if KEYBOARD_AVAILABLE:
            try:
                keyboard.unhook_all()
            except Exception:
                pass
        self.destroy()


if __name__ == "__main__":
    App().mainloop()
