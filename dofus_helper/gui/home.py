"""Onglet Accueil et panneau Activité."""
from __future__ import annotations

import customtkinter as ctk

from dofus_helper import core
from dofus_helper.gui import style
from dofus_helper.gui.style import P

from .common import BTN2, BTN2_HOVER, ico, MUTED
from .helpers import action_entry, FIRST_STEPS


class HomeMixin:
    """Onglet Accueil et panneau Activité. (partie de App)"""

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
            mark.configure(text="", image=ico("check", P["green"], 18) if done else ico("circle", MUTED, 16))
            if btn is not None:
                btn.configure(fg_color=BTN2 if done else P["accent"],
                              hover_color=BTN2_HOVER if done else P["accent_hover"],
                              text_color=P["text"] if done else P["on_accent"])
        if all_done:
            self.steps_outer.pack_forget()
        for key, lbl in self.tiles.items():
            self._count_to(lbl, self.stats[key])
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
        for i, (r, t, txt, hint, icon, delta) in enumerate(self.act_rows):
            if i < len(self.activity):
                e = self.activity[i]
                t.configure(text=e["time"])
                txt.configure(text=e["text"])
                hint.configure(text=e["hint"], text_color=colors.get(e["level"], MUTED))
                icon.configure(image=ico(e.get("icon", "dot"), colors.get(e["level"], MUTED), 14))
                d = e.get("delta")
                if d:                       # baisse = cyan (le cas normal), hausse = or
                    delta.configure(text=d[0], text_color=P["cyan"] if d[1] == "down" else P["gold"])
                    delta.pack(side="right", padx=(6, 0), ipadx=4, after=hint)
                else:
                    delta.pack_forget()
                r.pack(fill="x", padx=4, pady=1)
            else:
                r.pack_forget()

