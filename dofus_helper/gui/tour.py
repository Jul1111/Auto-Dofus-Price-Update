"""Visite guidée et fenêtre « Quoi de neuf »."""
from __future__ import annotations

import tkinter as tk

import customtkinter as ctk

from dofus_helper import core
from dofus_helper.gui import style
from dofus_helper.gui.style import P

from .common import BTN2, BTN2_HOVER, ico, MUTED
from .popups import POPUP_KEY, rounded_popup
from .helpers import tour_place, tour_steps
from .tray import brand
from .news import whats_new


class TourMixin:
    """Visite guidée et fenêtre « Quoi de neuf ». (partie de App)"""

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
            attr, _, key = name.partition(":")          # « chips:state » = self.chips["state"]
            w = getattr(self, attr, None)
            if key:
                w = w.get(key) if isinstance(w, dict) else None
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
            ctk.CTkButton(bar, text="Précédent", width=108, height=28, fg_color=BTN2, text_color=P["text"],
                          image=ico("back", size=14),
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

