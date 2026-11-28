"""Onglets Raccourcis, Prix, Mes ventes, Calibration et Options."""
from __future__ import annotations

import threading
import tkinter as tk
from typing import Optional

import customtkinter as ctk

from dofus_helper import core
from dofus_helper import update as dofus_update
from dofus_helper.gui import style
from dofus_helper.gui.style import P

from .common import (
    BTN2,
    BTN2_HOVER,
    CALIB_HOTKEYS,
    FLOOR_LABELS,
    fmt,
    HOTKEY_LABELS,
    hotkey_problem,
    ico,
    keyboard,
    KEYBOARD_AVAILABLE,
    MUTED,
    ORANGE,
    ROUNDING_LABELS,
    UNDERCUT_LABELS,
)
from .helpers import (
    HUD_AUTOHIDE,
    HUD_CONTENTS,
    HUD_SHAPES,
    HUD_SIZES,
    MAX_RUNS,
    PREVIEW_AVG,
    price_preview,
    run_title,
    save_runs,
    UI_SCALES,
)


class TabsMixin:
    """Onglets Raccourcis, Prix, Mes ventes, Calibration et Options. (partie de App)"""

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
        self._switch(b, "Modifier même si le prix est suspect ⚠️", "relist_force_suspect", progress_color=ORANGE,
                     tip="Pour un marché qui chute d'un jour à l'autre : une forte baisse ou un prix loin "
                         "du prix moyen ne bloque plus la mise à jour. Le prix est d'abord relu une 2e fois "
                         "(Tesseract seul) et doit être identique. Une lecture peu fiable reste bloquée.")
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
            self._empty_state(box, "Aucun parcours pour l'instant",
                              "Lance « Toute la liste » : chaque parcours s'ajoute ici avec son récap.",
                              icon="refresh").pack(fill="x", pady=2)
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
        ctk.CTkButton(r, text="Calibration automatique", width=300, height=46, image=ico("spark", P["on_accent"], 20),
                      font=ctk.CTkFont(size=15, weight="bold"),
                      command=lambda: self._countdown("automatique", self._calib_auto_ui)
                      ).pack(side="left", pady=4)
        self._hk_label(r, "calibrate_auto", text_color=MUTED,
                       font=ctk.CTkFont(family="Consolas")).pack(side="left", padx=12)
        r = self._row(ab)
        self._tip(ctk.CTkButton(r, text="Voir zones", width=108, fg_color=BTN2, text_color=P["text"], hover_color=BTN2_HOVER,
                                image=ico("eye"), command=self._show_zones),
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
        ctk.CTkButton(top, text="Ouvrir l'assistant de calibration", width=260, image=ico("compass", P["on_accent"]),
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
                ctk.CTkButton(r, text="", width=28, height=26, fg_color=BTN2, image=ico("close", size=14), hover_color=BTN2_HOVER,
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
        ctk.CTkButton(r, text="Tester", width=84, height=24, fg_color=BTN2, text_color=P["text"], hover_color=BTN2_HOVER,
                      image=ico("play", size=12),
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
        self.hud_move_btn = ctk.CTkButton(r, text="Déplacer", width=104, height=24, fg_color=BTN2, image=ico("move", size=14),
                                          text_color=P["text"], hover_color=BTN2_HOVER, command=self._hud_move)
        self.hud_move_btn.pack(side="left", padx=10)
        r = self._row(b)
        ctk.CTkLabel(r, text="Taille", width=70, anchor="w").pack(side="left", padx=(42, 0))
        seg = ctk.CTkSegmentedButton(r, values=[v[0] for v in HUD_SIZES.values()], command=self._set_hud_size)
        seg.set(HUD_SIZES.get(self.cfg.hud_size, HUD_SIZES["normal"])[0])
        seg.pack(side="left")
        r = self._row(b)
        self._tip(ctk.CTkLabel(r, text="Forme", width=70, anchor="w"),
                  "Carte : la ligne habituelle. Pilule : plus arrondie et compacte. Minimal : le texte seul "
                  "avec un fin liseré de couleur dessous.").pack(side="left", padx=(42, 0))
        seg = ctk.CTkSegmentedButton(r, values=list(HUD_SHAPES.values()), command=self._set_hud_shape)
        seg.set(HUD_SHAPES.get(self.cfg.hud_shape, HUD_SHAPES["card"]))
        seg.pack(side="left")
        r = self._row(b)
        ctk.CTkLabel(r, text="Contenu", width=70, anchor="w").pack(side="left", padx=(42, 0))
        seg = ctk.CTkSegmentedButton(r, values=list(HUD_CONTENTS.values()), command=self._set_hud_content)
        seg.set(HUD_CONTENTS.get(self.cfg.hud_content, HUD_CONTENTS["both"]))
        seg.pack(side="left")
        self._tip(seg, "État : actif, calibration à faire… seulement. Action : la dernière action seulement. "
                       "Pastille : un simple rond de couleur, qui s'agrandit 2 s à chaque action. Pendant un "
                       "parcours, la progression s'affiche toujours (sauf en pastille).")
        r = self._row(b)
        self.hud_hist_var = ctk.BooleanVar(value=self.cfg.hud_history)
        self._tip(ctk.CTkSwitch(r, text="Prix de l'objet sélectionné sous la ligne (lots 1, 10, 100)",
                                variable=self.hud_hist_var,
                                command=self._set_hud_history),
                  "Les trois derniers lots traités (prix lu → prix mis), le plus récent en couleur : "
                  "pour vérifier d'un coup d'œil, aussi pendant un parcours.").pack(side="left", padx=(42, 0))
        r = self._row(b)
        ctk.CTkLabel(r, text="Masquer", width=70, anchor="w").pack(side="left", padx=(42, 0))
        seg = ctk.CTkSegmentedButton(r, values=list(HUD_AUTOHIDE.values()), command=self._set_hud_autohide)
        seg.set(HUD_AUTOHIDE.get(self.cfg.hud_autohide, "Jamais"))
        seg.pack(side="left")
        self._tip(seg, "Sans action pendant ce temps, le HUD s'estompe. Il revient à la prochaine action, "
                       "pendant un parcours, ou en maintenant Alt.")
        r = self._row(b)
        self.hud_alt_var = ctk.BooleanVar(value=self.cfg.hud_alt)
        self._tip(ctk.CTkSwitch(r, text="Alt maintenu : HUD cliquable", variable=self.hud_alt_var,
                                command=self._set_hud_alt_opt),
                  "Dans le jeu, maintiens Alt (seul) : le HUD propose Arrêter le parcours, Copier le dernier "
                  "prix et Ouvrir l'outil. Alt + glisser le déplace. Relâche Alt : les clics le traversent à "
                  "nouveau.").pack(side="left", padx=(42, 0))
        r = self._row(b)
        ctk.CTkLabel(r, text="Opacité", width=70, anchor="w").pack(side="left", padx=(42, 0))
        sl = ctk.CTkSlider(r, from_=0.5, to=1.0, number_of_steps=10, width=180, command=self._set_hud_opacity)
        sl.set(min(1.0, max(0.5, self.cfg.hud_opacity)))
        sl.pack(side="left")
        self.hud_op_lbl = ctk.CTkLabel(r, text=f"{self.cfg.hud_opacity:.0%}", text_color=MUTED, width=44)
        self.hud_op_lbl.pack(side="left", padx=6)
        b = self._section(page, "Apparence")
        self._look = {"theme": self.cfg.theme if self.cfg.theme in style.THEMES else "dark",
                      "accent": self.cfg.accent if self.cfg.accent in style.ACCENTS else "blue",
                      "ambience": self.cfg.ambience if self.cfg.ambience in style.AMBIENCES else "night"}
        r = self._row(b)
        self._tip(ctk.CTkLabel(r, text="Thème", width=120, anchor="w"),
                  "Comme Windows : suit le mode clair / sombre de Windows (Paramètres › Couleurs).").pack(side="left")
        self.theme_seg = ctk.CTkSegmentedButton(r, values=list(style.THEMES.values()), command=self._pick_theme)
        self.theme_seg.set(style.THEMES[self._look["theme"]])
        self.theme_seg.pack(side="left")
        r = self._row(b)
        self._tip(ctk.CTkLabel(r, text="Ambiance", width=120, anchor="w"),
                  "Teinte des fonds, cartes et bordures du thème sombre.").pack(side="left")
        self.amb_seg = ctk.CTkSegmentedButton(r, values=[v[0] for k, v in style.AMBIENCES.items()
                                                         if k not in style.DOFUS_THEMES],
                                              command=self._pick_ambience)
        self.amb_seg.pack(side="left")
        r = self._row(b)
        self._tip(ctk.CTkLabel(r, text="Thème Dofus", width=120, anchor="w"),
                  "Les thèmes du jeu (Options › Thèmes de Dofus) : mêmes fonds, barre de titre et couleur "
                  "d'accent. Passe l'outil en sombre et remplace la couleur choisie.").pack(side="left")
        self.dofus_btns = {}
        for key, (label, pal) in style.DOFUS_THEMES.items():
            sw = ctk.CTkButton(r, text="●", width=30, height=30, corner_radius=8, fg_color=pal["caption"],
                               hover_color=pal["card2"], text_color=pal["accent"], border_width=3,
                               font=ctk.CTkFont(size=15), command=lambda k=key: self._pick_dofus_theme(k))
            sw.pack(side="left", padx=2)
            self._tip(sw, label)
            self.dofus_btns[key] = sw
        r = self._row(b)
        ctk.CTkLabel(r, text="Couleur", width=120, anchor="w").pack(side="left")
        self.accent_row = r
        self.accent_btns = {}
        for key, (label, color, hover) in style.ACCENTS.items():
            sw = ctk.CTkButton(r, text="", width=28, height=28, corner_radius=14, fg_color=color,
                               hover_color=hover, border_width=3, command=lambda k=key: self._pick_accent(k))
            sw.pack(side="left", padx=3)
            self._tip(sw, label)
            self.accent_btns[key] = sw
        self.accent_note = ctk.CTkLabel(r, text="(celle du thème Dofus)", text_color=MUTED)
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
        ctk.CTkButton(r, text="Sauvegarder…", width=150, image=ico("save", P["on_accent"]),
                      command=self._backup).pack(side="left")
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
        self._tip(ctk.CTkButton(r, text="Rapport de problème", width=200, image=ico("package", P["on_accent"]),
                                command=lambda: self._countdown("rapport", self._make_report)),
                  "Crée un zip à envoyer quand quelque chose ne marche pas : journal, réglages, captures "
                  "de diagnostic et une image de l'HDV (affiche-le pendant le compte à rebours). Rien "
                  "n'est envoyé tout seul ; ton historique de ventes n'est pas inclus.").pack(side="left")
        ctk.CTkButton(r, text="Signaler sur GitHub", width=150, fg_color=BTN2, text_color=P["text"], hover_color=BTN2_HOVER,
                      command=lambda: self._open_url(dofus_update.ISSUES_URL)).pack(side="left", padx=8)

