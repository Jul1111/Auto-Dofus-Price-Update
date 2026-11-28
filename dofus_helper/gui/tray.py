"""Icône dans la zone de notification (près de l'horloge)."""
from __future__ import annotations

import os
import tkinter as tk
from typing import Optional

from dofus_helper import core
from dofus_helper.gui import logo as dofus_logo
from dofus_helper.gui import style
from dofus_helper.gui.style import P

from .common import pystray, TRAY_AVAILABLE


# ---------------------------------------------------------------- zone de notification (près de l'horloge)
TRAY_STATES = {"ok": ("#3ecf8e", "Actif"),
               "loop": ("#5ccfe6", "Parcours en cours"), "calib": ("#f0616d", "Calibration à faire")}


def tray_image(color: str, size: int = 64, ring: str = None):
    """Icône : la pièce du logo, pastille de couleur = état de l'outil, anneau = couleur du profil."""
    return dofus_logo.logo_with_dot(color, size, ring=ring)


_ICO_PATH = None


def logo_ico() -> Optional[str]:
    """Chemin d'un .ico du logo (créé une fois dans le dossier temporaire), ou None."""
    global _ICO_PATH
    if _ICO_PATH is None:
        import tempfile
        from pathlib import Path
        path = Path(tempfile.gettempdir()) / f"dofus_price_helper_{core.app_version()}.ico"
        try:
            if not path.exists():
                dofus_logo.write_ico(path)
            _ICO_PATH = str(path)
        except Exception:
            _ICO_PATH = ""
    return _ICO_PATH or None


def brand(window) -> None:
    """Met le logo comme icône de la fenêtre (barre de titre, barre des tâches)."""
    path = logo_ico()
    if path:
        try:
            window.iconbitmap(path)    # avant le délai de CustomTkinter : il ne remet pas son icône
        except tk.TclError:
            pass
    try:                               # barre de titre de la couleur du fond (Windows 11), après CustomTkinter
        window.after(350, lambda: style.set_titlebar(window, P["caption"], P["text"], P["border"]))
    except tk.TclError:
        pass


class Tray:
    """Icône dans la zone de notification : clic = ouvrir, clic droit = menu (pystray)."""

    def __init__(self, app):
        self.app, self.icon, self._last = app, None, None
        self.told = False      # bulle « l'outil continue ici » déjà montrée

    def start(self):
        # Pas pendant la fermeture : _on_close enregistre les réglages (-> _apply_tray), ce qui
        # recréait l'icône ; son fil (non « daemon ») gardait alors l'outil actif sans fenêtre.
        if self.icon is not None or not TRAY_AVAILABLE or self.app.closing:
            return
        put = self.app.ui_events.put
        item = pystray.MenuItem
        menu = pystray.Menu(
            item("Ouvrir l'outil", lambda: put(("tray", "open")), default=True),
            item("■ Arrêter le parcours", lambda: put(("tray", "stop")),
                 visible=lambda _i: self.app._loop is not None),
            item("Aide-mémoire en jeu", lambda: put(("tray", "cheatsheet"))),
            item("HUD discret", lambda: put(("tray", "hud")), checked=lambda _i: bool(self.app.cfg.hud)),
            pystray.Menu.SEPARATOR,
            item("Quitter", lambda: put(("tray", "quit"))),
            item("Forcer l'arrêt", self._kill))
        color, text = (self._last or (*TRAY_STATES["ok"], None))[:2]
        ring = self._last[2] if self._last else None
        try:
            self.icon = pystray.Icon("DofusPriceHelper", tray_image(color, ring=ring),
                                     f"Dofus Price Helper · {text}", menu)
            self.icon.run_detached()
        except Exception as e:
            self.icon = None
            self.app._log(f"[Zone de notification] Icône impossible : {e}", "WARN")

    def update(self, state: str, ring: str = None, profile: str = ""):
        color, text = TRAY_STATES.get(state, TRAY_STATES["ok"])
        if profile:
            text += f" · {profile}"
        if (color, text, ring) == self._last:
            return
        self._last = (color, text, ring)
        if self.icon is not None:
            try:
                self.icon.icon = tray_image(color, ring=ring)
                self.icon.title = f"Dofus Price Helper · {text}"
                self.icon.update_menu()          # « Arrêter le parcours » visible ou non
            except Exception:
                pass

    def notify(self, text: str):
        if self.icon is not None:
            try:
                self.icon.notify(text, "Dofus Price Helper")
            except Exception:
                pass

    def _kill(self, *_):
        """Arrêt immédiat, appelé directement par l'icône (marche même si la fenêtre est figée)."""
        core.log_line("Arrêt forcé depuis l'icône de la zone de notification.", "WARN")
        try:
            if self.icon is not None:
                self.icon.visible = False      # sinon une icône « fantôme » reste près de l'horloge
        except Exception:
            pass
        os._exit(1)

    def stop(self):
        icon, self.icon = self.icon, None
        if icon is not None:
            try:
                icon.stop()
            except Exception:
                pass

