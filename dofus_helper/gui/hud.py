"""HUD discret par-dessus le jeu."""
from __future__ import annotations

import time
import tkinter as tk
from typing import Optional

import customtkinter as ctk

from dofus_helper import core
from dofus_helper.gui import logo as dofus_logo
from dofus_helper.gui import style
from dofus_helper.gui.style import P

from .common import BTN2, BTN2_HOVER, fmt, ico, MUTED
from .popups import ANIMATE, make_draggable, POPUP_KEY, rounded_popup
from .helpers import (
    alt_alone_down,
    ALT_HOLD_S,
    breath,
    count_value,
    eta_text,
    geometry_on_screen,
    HUD_AUTOHIDE,
    hud_calib_alert,
    HUD_CONTENTS,
    HUD_COUNT_MS,
    HUD_EXPAND_S,
    HUD_PULSE_S,
    HUD_RESIZE_MS,
    HUD_SEL_N,
    hud_selected_lines,
    HUD_SHAPES,
    HUD_SIZES,
    SEL_WATCH_MS,
    table_signature,
)
from .tray import TRAY_STATES


class HudMixin:
    """HUD discret par-dessus le jeu. (partie de App)"""

    # ---- HUD discret par-dessus le jeu (les clics le traversent)
    def _toggle_hud(self):
        self.cfg.hud = not self.cfg.hud
        self.v["hud"].set(self.cfg.hud)
        self._apply_hud()
        self._save_cfg()

    def _apply_hud(self):
        w = self._hud
        if self.cfg.hud:
            if w is None or not w.winfo_exists():
                self._hud_create()
            self._refresh_hud()
            self._hud_visibility()
        elif w is not None:
            if w.winfo_exists():
                w.destroy()
            self._hud = None
            self._hud_moving = False

    def _hud_create(self):
        c = self.cfg
        size = HUD_SIZES.get(c.hud_size, HUD_SIZES["normal"])[1]
        shape = c.hud_shape if c.hud_shape in HUD_SHAPES else "card"
        radius = {"card": 10, "pill": size + 8, "minimal": 0}[shape]
        t, card = rounded_popup(self, radius=radius, alpha=min(1.0, max(0.5, c.hud_opacity)),
                                border=self._hud_border())
        card.pack_configure(fill="both", expand=True)     # la fenêtre change de taille en douceur
        if shape == "minimal":                             # texte seul : fond transparent, liseré dessous
            card.configure(fg_color=POPUP_KEY, border_width=0)
        self._hud, self._hud_card = t, card
        self._hud_shape = shape
        row = ctk.CTkFrame(card, fg_color="transparent")
        row.pack(anchor="w", padx=(18, 20) if shape == "pill" else (10, 14), pady=max(3, size // 2 - 1))
        self._hud_row = row
        self._hud_line = ctk.CTkFrame(card, height=2, corner_radius=1, fg_color=P["border"])
        if shape == "minimal":
            self._hud_line.pack(fill="x", padx=(10, 14), pady=(0, 4), after=row)
        self._hud_layout_key = None
        self._hud_logo = ctk.CTkLabel(row, text="", image=self._logo_img_small())
        self._hud_logo.pack(side="left", padx=(0, 8))
        self._hud_profile = ctk.CTkLabel(row, text="", corner_radius=8, height=size + 6, text_color=style.ON_PROFILE,
                                         font=ctk.CTkFont(size=size - 1, weight="bold"))
        self._hud_state = ctk.CTkLabel(row, text="", font=ctk.CTkFont(size=size, weight="bold"))
        self._hud_state.pack(side="left")
        self._hud_head = ctk.CTkLabel(row, text="", text_color=P["text"], font=ctk.CTkFont(size=size, weight="bold"))
        self._hud_head.pack(side="left", padx=(10, 0))
        self._hud_sub = ctk.CTkLabel(row, text="", font=ctk.CTkFont(size=size))
        self._hud_sub.pack(side="left", padx=(8, 0))
        self._hud_bar = ctk.CTkProgressBar(card, height=4, corner_radius=2, progress_color=P["cyan"])
        self._hud_actions = ctk.CTkFrame(card, fg_color="transparent")    # Alt maintenu
        small = ctk.CTkFont(size=max(11, size - 1))
        self._hud_btn_stop = ctk.CTkButton(self._hud_actions, text="Arrêter le parcours", height=24, width=10,
                                           image=ico("stop", P["on_accent"], 12),
                                           font=small, fg_color=P["red"], hover_color=P["red_hover"],
                                           text_color=P["on_accent"], command=self._stop_loop)
        self._hud_btn_copy = ctk.CTkButton(self._hud_actions, text="Copier le prix", height=24, width=10, font=small,
                                           image=ico("copy", P["on_accent"], 14),
                                           command=self._hud_copy_price)
        self._hud_btn_recal = ctk.CTkButton(self._hud_actions, text="Recalibrer", height=24, width=10,
                                            image=ico("spark", style.CHIP["orange"][1], 14),
                                            font=small, fg_color=style.CHIP["orange"][0],
                                            hover_color=P["card2"], text_color=style.CHIP["orange"][1],
                                            command=self._hud_recalibrate)
        self._hud_btn_open = ctk.CTkButton(self._hud_actions, text="Ouvrir l'outil", height=24, width=10, font=small,
                                           fg_color=BTN2, text_color=P["text"], hover_color=BTN2_HOVER,
                                           command=self._show_main)
        self._hud_hist = ctk.CTkFrame(card, fg_color="transparent")       # derniers prix (option)
        self._hud_hist_lbls = [ctk.CTkLabel(self._hud_hist, text="", anchor="w", height=size + 4,
                                            font=ctk.CTkFont(family=style.MONO, size=size - 1))
                               for _ in range(HUD_SEL_N)]
        pos = self.cfg.hud_pos
        try:
            ok = bool(pos) and geometry_on_screen(f"300x40+{pos[0]}+{pos[1]}", core.screen_bounds())
        except Exception:
            ok = False
        if ok:
            x, y = pos
        else:                                   # en haut, au centre de l'écran principal
            x, y = self.winfo_screenwidth() // 2 - 170, 8
        t.geometry(f"+{int(x)}+{int(y)}")
        make_draggable(t, self._hud_dropped)
        t.after(150, self._hud_apply_click)
        t.withdraw()

    def _logo_img_small(self):
        if getattr(self, "_logo16", None) is None:
            img = dofus_logo.logo_image(32)
            self._logo16 = ctk.CTkImage(light_image=img, dark_image=img, size=(16, 16))
        return self._logo16

    def _refresh_hud(self):
        w = self._hud
        if w is None or not w.winfo_exists():
            return
        c = self.cfg
        now = time.time()
        state = "loop" if self._loop is not None else "calib" if not self._calibrated() else "ok"
        color, text = TRAY_STATES[state]
        chip = {"ok": "green", "loop": "grey", "calib": "red"}[state]
        multi = len(c.profile_names()) > 1          # multi-compte : profil actif dans sa couleur
        dot = (c.hud_content == "dot" and not self._hud_moving and not self._hud_alt
               and now >= self._hud_expand_until)
        self._hud_layout(dot, multi)
        if multi:
            self._hud_profile.configure(text=f" {c.profile} ", fg_color=self._profile_color())
        show_state = c.hud_content not in ("action", "dot") or self._hud_moving
        show_action = c.hud_content != "state" or self._loop is not None or self._hud_moving
        alert = self._hud_alert() if state == "ok" else None
        state_color = P["cyan"] if state == "loop" else style.CHIP[chip][1]
        if alert:                                   # calibration décalée : rond orange, toujours visible
            text, state_color, show_state = alert[0], style.CHIP["orange"][1], True
        self._hud_state.configure(text=(f"⚠ {text}" if alert else f"● {text}") if show_state and not dot
                                  else "●", text_color=state_color)
        lp = self._loop
        frac = None
        if self._hud_moving:
            head, sub, col = "Glisse-moi où tu veux", "(lâche pour terminer)", MUTED
        elif self._hud_alt:
            head, sub, col = "Actions", "relâche Alt pour fermer · Alt + glisser = déplacer", MUTED
        elif lp is not None:                    # parcours : progression, temps restant, comment l'arrêter
            stop = "arrêt demandé…" if self.engine.stop_requested else f"{c.hotkeys['pause'].upper()} = arrêter"
            parts = (lp["text"], eta_text(now - lp["t0"], lp["frac"]), stop)
            head, sub, col = self.LOOP_NAMES.get(lp["kind"], ""), " · ".join(x for x in parts if x), P["text"]
            frac = lp["frac"]
        else:
            note = self._hud_note
            head, sub, col = note[:3] if note and now < note[3] else self.last_action
            if head.startswith("En attente"):
                head = ""
            if alert and not (note and now < note[3]) and self._calib_alert_t >= self._last_action_t:
                hint = " · maintiens Alt pour recalibrer" if c.hud_alt else ""
                head, sub, col = "", alert[1] + hint, style.CHIP["orange"][1]
        tick = self._hud_ticker
        if tick and head == tick["head"]:              # nouveau prix : il défile jusqu'à sa valeur
            f = (now - tick["t0"]) * 1000 / HUD_COUNT_MS
            if f < 1 and ANIMATE["on"]:
                head = tick["tpl"].format(fmt(count_value(tick["from"], tick["to"], f)))
                if not self._hud_tick_after:
                    self._hud_tick_after = self.after(16, self._hud_tick_refresh)
            else:
                self._hud_ticker = None
        self._hud_head.configure(text=head if show_action and not dot else "")
        self._hud_sub.configure(text=sub if show_action and not dot else "", text_color=col)
        if self._hud_shape == "minimal":
            self._hud_line.configure(fg_color=state_color)
        elif not getattr(self, "_hud_flash_after", None) and not self._hud_moving:
            self._hud_card.configure(border_color=self._hud_border())
        self._refresh_hud_bar(None if dot else frac)
        self._refresh_hud_actions()
        self._refresh_hud_history(hide=dot)
        self._hud_resize()

    def _hud_border(self) -> str:
        """Bord du HUD : couleur du personnage en multi-compte, sinon le bord fin habituel."""
        return self._profile_color() if len(self.cfg.profile_names()) > 1 else P["border"]

    def _hud_tick_refresh(self):
        self._hud_tick_after = None
        self._refresh_hud()

    def _hud_resize(self):
        """La fenêtre du HUD suit la taille de son contenu en douceur (au lieu d'un saut)."""
        w = self._hud
        if w is None or not w.winfo_exists():
            return
        w.update_idletasks()
        tw, th = self._hud_card.winfo_reqwidth(), self._hud_card.winfo_reqheight()
        cw, ch = w.winfo_width(), w.winfo_height()
        if (cw, ch) == (tw, th):
            return
        if not ANIMATE["on"] or self._hud_moving or not w.winfo_ismapped() or cw <= 1:
            self._hud_resize_anim = None
            w.geometry(f"{tw}x{th}")
            return
        token = object()
        self._hud_resize_anim = token
        steps = max(1, HUD_RESIZE_MS // 16)

        def step(i=1):
            if self._hud_resize_anim is not token or not w.winfo_exists():
                return
            e = style.ease_out(i / steps)
            w.geometry(f"{round(cw + (tw - cw) * e)}x{round(ch + (th - ch) * e)}")
            if i < steps:
                self.after(16, lambda: step(i + 1))
            else:
                self._hud_resize_anim = None
                self._hud_resize()                # le contenu a pu changer entre-temps
        step()

    def _hud_anim_tick(self):
        """Rond d'état vivant : il respire pendant un parcours et s'illumine à chaque résultat."""
        delay = 400
        try:
            w = self._hud
            if w is not None and w.winfo_exists() and w.winfo_ismapped() and ANIMATE["on"] \
                    and not self._hud_moving:
                now = time.time()
                card = P["card"] if self._hud_shape != "minimal" else P["bg"]
                pulse = self._hud_pulse
                if pulse and now - pulse[1] < HUD_PULSE_S:
                    f = (now - pulse[1]) / HUD_PULSE_S
                    color = style.blend(w, "#ffffff", pulse[0], style.ease_out(f))
                    self._hud_state.configure(text_color=color)
                    self._hud_tinted, delay = True, 30
                elif self._loop is not None:
                    color = style.blend(w, P["cyan"], card, 0.55 * breath(now))
                    self._hud_state.configure(text_color=color)
                    self._hud_tinted, delay = True, 50
                elif self._hud_tinted:
                    self._hud_tinted = False
                    self._hud_pulse = None
                    self._refresh_hud()
        except Exception:
            pass
        self.after(delay, self._hud_anim_tick)

    def _hud_layout(self, dot: bool, multi: bool):
        """Éléments de la ligne du HUD : tout, ou seulement le rond d'état (pastille)."""
        key = (dot, multi)
        if key == self._hud_layout_key:
            return
        self._hud_layout_key = key
        items = [(self._hud_logo, (0, 8)), (self._hud_profile, (0, 8)), (self._hud_state, 0),
                 (self._hud_head, (10, 0)), (self._hud_sub, (8, 0))]
        for wdg, _pad in items:
            wdg.pack_forget()
        for wdg, pad in items:
            if dot and wdg is not self._hud_state:
                continue
            if wdg is self._hud_profile and not multi:
                continue
            wdg.pack(side="left", padx=pad)

    def _refresh_hud_bar(self, frac: Optional[float]):
        bar = self._hud_bar
        if frac is None:
            bar.pack_forget()
            return
        bar.set(frac)
        if not bar.winfo_manager():
            bar.pack(fill="x", padx=(34, 14), pady=(0, 6), after=self._hud_row)

    def _refresh_hud_actions(self):
        box = self._hud_actions
        if not self._hud_alt:
            box.pack_forget()
            return
        for b in (self._hud_btn_stop, self._hud_btn_recal, self._hud_btn_copy, self._hud_btn_open):
            b.pack_forget()
        if self._loop is not None:
            self._hud_btn_stop.configure(state="disabled" if self.engine.stop_requested else "normal")
            self._hud_btn_stop.pack(side="left", padx=(0, 6))
        elif self._hud_alert():
            self._hud_btn_recal.configure(state="disabled" if self.engine._lock.locked() else "normal")
            self._hud_btn_recal.pack(side="left", padx=(0, 6))
        p = self._last_price
        self._hud_btn_copy.configure(text=f"Copier {fmt(p)}" if p is not None else "Copier le prix",
                                     state="normal" if p is not None else "disabled")
        self._hud_btn_copy.pack(side="left", padx=(0, 6))
        self._hud_btn_open.pack(side="left")
        if not box.winfo_manager():
            box.pack(anchor="w", padx=(34, 14), pady=(0, 8),
                     after=self._hud_bar if self._hud_bar.winfo_manager() else self._hud_row)

    def _refresh_hud_history(self, hide: bool = False):
        """Sous la ligne du HUD : les prix de l'objet sélectionné, lots 1 / 10 / 100
        (option « Prix de l'objet sélectionné »). Mis à jour quand tu changes d'objet dans l'HDV."""
        sel = self.hud_sel
        lines = (hud_selected_lines(sel["prices"], sel.get("selected"))
                 if sel and self.cfg.hud_history and not self._hud_moving and not hide else [])
        hist = self._hud_hist
        for i, lbl in enumerate(self._hud_hist_lbls):
            if i < len(lines):
                text, color = lines[i]
                lbl.configure(text=text, text_color=P[color] if color else MUTED)
                if not lbl.winfo_ismapped():
                    lbl.pack(anchor="w", fill="x")
            else:
                lbl.pack_forget()
        if lines and not hist.winfo_ismapped():
            hist.pack(anchor="w", fill="x", padx=(34, 14), pady=(0, 6))
        elif not lines:
            hist.pack_forget()

    def _push_history(self, res, refresh: bool = True):
        """Résultat avec un prix : il devient le « dernier prix » (bouton Copier du HUD) et, s'il porte
        une lecture du tableau, les prix de l'objet sélectionné sont mis à jour."""
        if res.new_price is not None and "rien à faire" not in res.message:
            self._last_price = res.new_price
        sr = getattr(res, "screen", None)
        if sr is not None and any(v is not None for v in sr.values.values()):
            self._set_hud_selected(sr, refresh=False)
        if refresh:
            self._refresh_hud()

    def _set_hud_selected(self, sr, refresh: bool = True):
        self.hud_sel = {"prices": dict(sr.values), "selected": sr.selected, "t": time.time()}
        if refresh:
            self._refresh_hud()

    def _sel_watch(self):
        """Toutes les 0,5 s, si l'option est active et le jeu au premier plan : le tableau de l'HDV
        a-t-il changé (autre objet sélectionné) ? Une fois l'image stable, lecture discrète
        (capture d'écran + lecture des chiffres, aucun clic ni touche)."""
        try:
            c = self.cfg
            if (c.hud and c.hud_history and self._game_fg and self._loop is None and not self._sel_pending
                    and c.table_region and not self.engine._lock.locked() and self.jobs.empty()):
                sig = table_signature(core.grab_screen(tuple(c.table_region)))
                if sig != self._sel_sig:
                    if getattr(self, "_sel_candidate", None) == sig:     # stable depuis 0,5 s : on lit
                        self._sel_sig = sig
                        self._sel_pending = True
                        self.jobs.put(("peek", None))
                    self._sel_candidate = sig
        except Exception:
            pass
        if not self.closing:
            self.after(SEL_WATCH_MS, self._sel_watch)

    def _set_hud_history(self):
        self.cfg.hud_history = bool(self.hud_hist_var.get())
        self._save_cfg()
        self._refresh_hud()

    def _hud_rebuild(self):
        """Taille / contenu changés : le HUD est recréé."""
        w = self._hud
        if w is not None and w.winfo_exists():
            w.destroy()
        self._hud = None
        self._apply_hud()

    def _set_hud_size(self, label: str):
        self.cfg.hud_size = next((k for k, (lbl, _s) in HUD_SIZES.items() if lbl == label), "normal")
        self._save_cfg()
        self._hud_rebuild()

    def _set_hud_shape(self, label: str):
        self.cfg.hud_shape = next((k for k, lbl in HUD_SHAPES.items() if lbl == label), "card")
        self._save_cfg()
        self._hud_rebuild()

    def _set_hud_content(self, label: str):
        self.cfg.hud_content = next((k for k, lbl in HUD_CONTENTS.items() if lbl == label), "both")
        self._save_cfg()
        self._refresh_hud()

    def _set_hud_opacity(self, value: float):
        self.cfg.hud_opacity = round(float(value), 2)
        self.hud_op_lbl.configure(text=f"{self.cfg.hud_opacity:.0%}")
        w = self._hud
        if w is not None and w.winfo_exists():
            try:
                w.attributes("-alpha", self.cfg.hud_opacity)
            except tk.TclError:
                pass
        if getattr(self, "_hud_op_save", None):
            self.after_cancel(self._hud_op_save)
        self._hud_op_save = self.after(500, self._save_cfg)

    # ---- couleur du profil
    def _profile_color(self, name: str = None) -> str:
        return style.profile_color(name or self.cfg.profile, self.cfg.profile_colors)

    def _set_profile_color(self, key: str):
        self.cfg.profile_colors[self.cfg.profile] = key
        self._save_cfg()
        self._refresh_profile_colors()
        self._refresh_status()

    def _refresh_profile_colors(self):
        btns = getattr(self, "pcolor_btns", None)
        if not btns:
            return
        current = self._profile_color()
        for key, sw in btns.items():
            sw.configure(border_color=P["text"] if style.PROFILE_COLORS[key][1] == current else P["card"])

    def _hud_flash(self, color: str, ms: int = 1800):
        """Nouveau résultat : le bord du HUD prend sa couleur un instant (pastille : il s'agrandit)."""
        w = self._hud
        if w is None or not w.winfo_exists() or self._hud_moving:
            return
        self._hud_bump()
        if self.cfg.hud_content == "dot":
            self._hud_expand_until = time.time() + HUD_EXPAND_S
            self._refresh_hud()
            self.after(int(HUD_EXPAND_S * 1000) + 60, self._refresh_hud)
        self._hud_pulse = (color, time.time())
        if self._hud_shape == "minimal":
            self._hud_line.configure(fg_color=color)
        else:
            self._hud_card.configure(border_color=color, border_width=2)
        if getattr(self, "_hud_flash_after", None):
            self.after_cancel(self._hud_flash_after)

        def back():
            self._hud_flash_after = None
            if self._hud is not None and self._hud.winfo_exists() and not self._hud_moving:
                if self._hud_shape != "minimal":
                    self._hud_card.configure(border_color=self._hud_border(), border_width=1)
                self._refresh_hud()
        self._hud_flash_after = self.after(ms, back)

    def _hud_message(self, head: str, sub: str, color: str, ms: int = 2500):
        """Message temporaire dans le HUD (ex. changement de profil), puis la dernière action."""
        self._hud_note = (head, sub, color, time.time() + ms / 1000)
        self._refresh_hud()
        self._hud_flash(color, ms)
        self.after(ms + 50, self._refresh_hud)

    def _hud_visibility(self):
        w = self._hud
        if w is None or not w.winfo_exists():
            return
        want, idle = self._hud_wanted()
        shown = w.winfo_ismapped()
        if want and (not shown or self._hud_fading):
            self._hud_fading = False
            w.attributes("-alpha", min(1.0, max(0.5, self.cfg.hud_opacity)))
            if not shown:
                w.deiconify()
                w.attributes("-topmost", True)
                w.after(50, self._hud_apply_click)
        elif not want and shown and not self._hud_fading:
            if idle and ANIMATE["on"]:               # sans action depuis un moment : il s'estompe
                self._hud_fading = True
                style.fade(w, min(1.0, max(0.5, self.cfg.hud_opacity)), 0.0, 600, self._hud_faded)
            else:
                w.withdraw()

    def _hud_alert(self) -> Optional[tuple]:
        return hud_calib_alert(self._drift_text, self.hdv_state, self._calibrated())

    def _hud_recalibrate(self):
        """« Recalibrer » du HUD (Alt maintenu) : calibration automatique tout de suite, l'HDV est à l'écran."""
        if self.engine._lock.locked():
            return
        self._hud_message("Calibration automatique…", "garde l'HDV ouvert, onglet Vente", P["cyan"], 4000)
        self._calib_auto_ui()

    def _hud_wanted(self) -> tuple:
        """(afficher ?, masqué faute d'activité ?)."""
        c = self.cfg
        idle = bool(c.hud_autohide) and self._loop is None and not self._hud_moving and not self._hud_alt \
            and not self._hud_alert() and time.time() - self._hud_active > c.hud_autohide
        return bool(c.hud and ((self._game_fg and not idle) or self._hud_moving)), idle

    def _hud_faded(self):
        w = self._hud
        if not self._hud_fading or w is None or not w.winfo_exists():
            return
        self._hud_fading = False
        if not self._hud_wanted()[0]:
            w.withdraw()
        w.attributes("-alpha", min(1.0, max(0.5, self.cfg.hud_opacity)))

    def _hud_bump(self):
        """Activité : le HUD masqué faute d'action revient."""
        self._hud_active = time.time()
        if self.cfg.hud_autohide:
            self._hud_visibility()

    def _hud_apply_click(self):
        w = self._hud
        if w is None or not w.winfo_exists():
            return
        if self._hud_moving:
            style.set_click_through(w, False)
        elif self._hud_alt:
            style.set_click_through(w, False, activate=False)   # cliquable, le jeu garde le focus
        else:
            style.set_click_through(w, True)

    # ---- Alt maintenu : HUD cliquable
    def _hud_alt_poll(self):
        try:
            w, c = self._hud, self.cfg
            ok = (c.hud and c.hud_alt and w is not None and w.winfo_exists() and self._game_fg
                  and not self._hud_moving)
            down = ok and alt_alone_down()
            now = time.time()
            if not down:
                self._alt_since = None
            elif self._alt_since is None:
                self._alt_since = now
            want = bool(down and now - self._alt_since >= ALT_HOLD_S)
            if want != self._hud_alt:
                self._set_hud_alt(want)
        except Exception:
            pass
        self.after(100, self._hud_alt_poll)

    def _set_hud_alt(self, on: bool):
        self._hud_alt = on
        w = self._hud
        if w is None or not w.winfo_exists():
            return
        if on:
            self._hud_bump()
            self._hud_visibility()
        if self._hud_shape != "minimal":
            self._hud_card.configure(border_color=P["accent"] if on else self._hud_border(),
                                     border_width=2 if on else 1)
        self._hud_apply_click()
        self._refresh_hud()

    def _hud_copy_price(self):
        p = self._last_price
        if p is None:
            return
        self.clipboard_clear()
        self.clipboard_append(str(p))
        self._hud_message(f"{fmt(p)} copié", "Ctrl+V dans le jeu", P["green"], 1500)

    def _set_hud_autohide(self, label: str):
        self.cfg.hud_autohide = next((k for k, lbl in HUD_AUTOHIDE.items() if lbl == label), 0)
        self._hud_active = time.time()
        self._save_cfg()
        self._hud_visibility()

    def _set_hud_alt_opt(self):
        self.cfg.hud_alt = bool(self.hud_alt_var.get())
        self._save_cfg()

    def _hud_move(self):
        """« Déplacer » : le HUD devient cliquable le temps de le poser ailleurs."""
        if not self.cfg.hud:
            self._toggle_hud()
        w = self._hud
        if w is None or not w.winfo_exists():
            return
        self._hud_moving = True
        if self._hud_shape != "minimal":
            self._hud_card.configure(border_color=P["accent"], border_width=2)
        style.set_click_through(w, False)
        self._refresh_hud()
        self._hud_visibility()
        self.hud_move_btn.configure(text="Glisse le HUD…", state="disabled")
        self._hud_move_after = self.after(30000, self._hud_move_end)    # oublié : fin au bout de 30 s

    def _hud_dropped(self, x: int, y: int):
        self.cfg.hud_pos = [x, y]
        self._save_cfg()
        if self._hud_moving:
            self._hud_move_end()

    def _hud_move_end(self):
        if getattr(self, "_hud_move_after", None):
            self.after_cancel(self._hud_move_after)
            self._hud_move_after = None
        self._hud_moving = False
        w = self._hud
        if w is not None and w.winfo_exists():
            if self._hud_shape != "minimal":
                self._hud_card.configure(border_color=self._hud_border(), border_width=1)
            style.set_click_through(w, True)
        self.hud_move_btn.configure(text="Déplacer", state="normal")
        self._refresh_hud()
        self._hud_visibility()

