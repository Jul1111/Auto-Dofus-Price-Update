"""Assistant de calibration."""
from __future__ import annotations

from typing import Optional

import customtkinter as ctk

from dofus_helper import core
from dofus_helper.gui import style
from dofus_helper.gui.style import P

from .common import BTN2, BTN2_HOVER, CARD, fmt, ico, MUTED, POINT_LABELS, ZONE_LABELS
from .tray import brand


class CalibrationMixin:
    """Assistant de calibration. (partie de App)"""

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
        auto = ctk.CTkButton(side, text="Tout placer automatiquement", height=34, image=ico("spark", P["on_accent"]),
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
        ctk.CTkButton(hr, text="Relire", width=80, height=22, fg_color=BTN2, text_color=P["text"], hover_color=BTN2_HOVER,
                      image=ico("refresh", size=13),
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
        self._wiz_back = ctk.CTkButton(bar, text="Retour", width=96, fg_color=BTN2, text_color=P["text"], hover_color=BTN2_HOVER,
                                       image=ico("back", size=14),
                                       command=lambda: self._wiz_go(-1))
        self._wiz_back.pack(side="left")
        ctk.CTkButton(bar, text="Voir zones", width=108, fg_color=BTN2, text_color=P["text"], hover_color=BTN2_HOVER,
                      image=ico("eye"),
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
        if res.ok:
            self._hud_message("Calibration refaite ✓", "zones recalées sur l'HDV", P["green"], 3000)
        else:
            self._hud_message("Calibration impossible", "HDV pas reconnu : ouvre-le, onglet Vente", P["red"], 3500)
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

