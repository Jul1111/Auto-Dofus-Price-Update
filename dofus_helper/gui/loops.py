"""Parcours (F2 / Ctrl+F3) : progression, Arrêter ; aide-mémoire des touches."""
from __future__ import annotations

import time
import tkinter as tk
from typing import Optional

import customtkinter as ctk

from dofus_helper import core
from dofus_helper.gui import style
from dofus_helper.gui.style import P

from .common import ico, MUTED
from .popups import ANIMATE, close_popup, make_draggable, rounded_popup
from .helpers import geometry_on_screen, LONG_LOOP_S, progress_text, windows_notify


class LoopsMixin:
    """Parcours (F2 / Ctrl+F3) : progression, Arrêter ; aide-mémoire des touches. (partie de App)"""

    # ---- boucles (F2 / Ctrl+F3) : progression, Arrêter, notification
    LOOP_NAMES = {"relist_all": "Toute la liste", "sell_all": "Tout vendre"}

    def _loop_start(self, kind: str):
        self._loop = {"kind": kind, "t0": time.time(), "frac": None,
                      "text": "Démarrage…" if kind == "relist_all" else "en cours…"}
        self.loop_stop.configure(text="Arrêter", state="normal")
        self._hud_bump()
        self._loop_show()
        self._tray_update()
        self._refresh_status()               # pastille d'état : « ■ Arrêter le parcours »

    def _loop_progress(self, d: dict):
        if self._loop is None or d.get("finished"):
            return
        text, frac = progress_text(d)
        self._loop.update(text=text, frac=frac)
        self._hud_bump()
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
        ctk.CTkButton(head, text="", width=24, height=22, fg_color="transparent", hover_color=P["btn2_hover"],
                      image=ico("close", MUTED, 14), command=lambda: self._cheat_close(t)).pack(side="right")
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

