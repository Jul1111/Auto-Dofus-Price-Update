"""Apparence, sons, profils de calibration."""
from __future__ import annotations

import tkinter as tk

import customtkinter as ctk

from dofus_helper import core
from dofus_helper.gui import style
from dofus_helper.gui.style import P

from .common import fmt, ZONE_LABELS
from .helpers import UI_SCALES


class OptionsMixin:
    """Apparence, sons, profils de calibration. (partie de App)"""

    # ---- apparence : thème, couleur d'accent (appliqués au redémarrage, avec un aperçu)
    def _pick_theme(self, label: str):
        self._look["theme"] = next((k for k, v in style.THEMES.items() if v == label), "dark")
        if style.resolve_theme(self._look["theme"]) == "light" and self._look["ambience"] in style.DOFUS_THEMES:
            self._look["ambience"] = "night"      # les thèmes Dofus sont sombres
        self._refresh_look()

    def _pick_ambience(self, label: str):
        self._look["ambience"] = next((k for k, v in style.AMBIENCES.items()
                                       if v[0] == label and k not in style.DOFUS_THEMES), "night")
        self._refresh_look()

    def _pick_dofus_theme(self, key: str):
        self._look["ambience"] = key
        if style.resolve_theme(self._look["theme"]) == "light":
            self._look["theme"] = "dark"
        self._refresh_look()

    def _pick_accent(self, key: str):
        self._look["accent"] = key
        if self._look["ambience"] in style.DOFUS_THEMES:
            self._look["ambience"] = "night"      # une couleur choisie à la main quitte le thème Dofus
        self._refresh_look()

    def _refresh_look(self):
        amb = self._look["ambience"]
        dofus = amb in style.DOFUS_THEMES
        self.theme_seg.set(style.THEMES[self._look["theme"]])
        self.amb_seg.set("" if dofus else style.AMBIENCES.get(amb, style.AMBIENCES["night"])[0])
        for key, sw in self.dofus_btns.items():
            sw.configure(border_color=P["text"] if key == amb else P["card"])
        for key, sw in self.accent_btns.items():
            sw.configure(border_color=P["text"] if key == self._look["accent"] and not dofus else P["card"])
        if dofus and not self.accent_note.winfo_manager():
            self.accent_note.pack(side="left", padx=8)
        elif not dofus:
            self.accent_note.pack_forget()
        self._render_look_preview()
        self.amb_seg.configure(state="normal" if style.resolve_theme(self._look["theme"]) == "dark" else "disabled")
        pending = (self._look["theme"], self._look["accent"], self._look["ambience"]) != \
            (self.cfg.theme, self.cfg.accent, self.cfg.ambience)
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
        self.cfg.theme, self.cfg.accent, self.cfg.ambience = (self._look["theme"], self._look["accent"],
                                                              self._look["ambience"])
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
        self._log_fonts()
        self._render_log()
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

