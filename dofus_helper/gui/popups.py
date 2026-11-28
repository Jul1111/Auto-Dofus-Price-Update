"""Fenêtres flottantes au style de l'outil (coins arrondis, déplaçables) et infobulles."""
from __future__ import annotations

import tkinter as tk

import customtkinter as ctk

from dofus_helper.gui import style
from dofus_helper.gui.style import P


# ---------------------------------------------------------------- fenêtres flottantes au style de l'outil
POPUP_KEY = "#010203"   # couleur rendue transparente : coins arrondis des fenêtres flottantes
ANIMATE = {"on": True}  # fondus et progression douce (option « Animations »)


def rounded_popup(master, radius: int = 12, alpha: float = 0.97, border: str = None):
    """Fenêtre flottante sans bord (HUD, aide-mémoire, bulle d'aide) : une carte arrondie avec une
    bordure fine, aux couleurs de l'outil. Retourne (fenêtre, carte) ; mettre le contenu dans la carte."""
    t = tk.Toplevel(master)
    t.overrideredirect(True)
    t.attributes("-topmost", True)
    t.configure(bg=POPUP_KEY)
    try:
        t.attributes("-transparentcolor", POPUP_KEY)   # Windows : coins vraiment arrondis
    except tk.TclError:
        t.configure(bg=P["card"])
    try:
        t.attributes("-alpha", 0.0 if ANIMATE["on"] else alpha)
    except tk.TclError:
        pass
    if ANIMATE["on"]:
        style.fade(t, 0.0, alpha, 130)      # apparition en fondu
    card = ctk.CTkFrame(t, fg_color=P["card"], corner_radius=radius, border_width=1,
                        border_color=border or P["border"])
    card.pack()
    return t, card


def make_draggable(window, on_drop=None) -> None:
    """Fenêtre sans bord déplaçable en la tirant (clic gauche maintenu n'importe où dessus,
    sauf les boutons). on_drop(x, y) : appelé à la fin d'un déplacement."""
    state = {}

    def press(e):
        state.update(x=e.x_root, y=e.y_root, wx=window.winfo_x(), wy=window.winfo_y(), moved=False)

    def drag(e):
        if "x" not in state:
            return
        dx, dy = e.x_root - state["x"], e.y_root - state["y"]
        if abs(dx) + abs(dy) > 2:
            state.update(moved=True, nx=state["wx"] + dx, ny=state["wy"] + dy)
            window.geometry(f"+{state['nx']}+{state['ny']}")

    def release(_e):
        if state.get("moved") and on_drop is not None:
            on_drop(state["nx"], state["ny"])
        state.clear()

    def bind_all(w):
        if isinstance(w, ctk.CTkButton):
            return
        for seq, fn in (("<ButtonPress-1>", press), ("<B1-Motion>", drag), ("<ButtonRelease-1>", release)):
            try:
                w.bind(seq, fn, add="+")
            except (NotImplementedError, ValueError, tk.TclError):
                pass
        for c in w.winfo_children():
            bind_all(c)
    bind_all(window)
    try:
        window.configure(cursor="fleur")
    except tk.TclError:
        pass


def close_popup(t) -> None:
    """Ferme une fenêtre flottante (en fondu si les animations sont actives)."""
    try:
        if not t.winfo_exists():
            return
        if not ANIMATE["on"]:
            t.destroy()
            return
        start = float(t.attributes("-alpha"))
    except tk.TclError:
        return
    style.fade(t, start, 0.0, 160, then=lambda: t.winfo_exists() and t.destroy())


class Tooltip:
    """Aide au survol : petite bulle après une demi-seconde sur le widget."""

    def __init__(self, widget, text: str, delay: int = 450):
        self.widget, self.text, self.delay = widget, text, delay
        self._after = None
        self._tip = None
        for seq, fn in (("<Enter>", self._schedule), ("<Leave>", self._hide), ("<ButtonPress>", self._hide)):
            try:
                widget.bind(seq, fn, add="+")
            except (NotImplementedError, ValueError, tk.TclError):
                pass

    def _schedule(self, _e=None):
        self._cancel()
        self._after = self.widget.after(self.delay, self._show)

    def _cancel(self):
        if self._after:
            try:
                self.widget.after_cancel(self._after)
            except tk.TclError:
                pass
            self._after = None

    def _show(self):
        self._after = None
        if self._tip is not None or not self.text:
            return
        try:
            x, y = self.widget.winfo_pointerx() + 14, self.widget.winfo_pointery() + 18
        except tk.TclError:
            return
        t, card = rounded_popup(self.widget, radius=8)
        ctk.CTkLabel(card, text=self.text, justify="left", wraplength=340, text_color=P["text"],
                     font=ctk.CTkFont(size=12)).pack(padx=10, pady=6)
        t.geometry(f"+{x}+{y}")
        self._tip = t

    def _hide(self, _e=None):
        self._cancel()
        if self._tip is not None:
            try:
                self._tip.destroy()
            except tk.TclError:
                pass
            self._tip = None

