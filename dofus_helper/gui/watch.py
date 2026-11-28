"""Surveillance du jeu : calibration décalée, profil selon le personnage."""
from __future__ import annotations

import time
from typing import Optional

from dofus_helper import core
from dofus_helper.gui import style
from dofus_helper.gui.style import P

from .common import MUTED, ZONE_LABELS
from .helpers import CALIB_WATCH_MS


class GameWatchMixin:
    """Surveillance du jeu : calibration décalée, profil selon le personnage. (partie de App)"""

    # ---- calibration décalée (fenêtre du jeu ou écran changés depuis la calibration)
    OFF_LABELS = dict(ZONE_LABELS, price_field="Prix du lot", sell_button="Mettre en vente",
                      modify_button="Modifier", relist_row="Lignes de mes ventes")

    def _remember_game_window(self):
        try:
            rect = core.game_window_rect(self.cfg)
        except Exception:
            rect = None
        if rect and list(rect) != self.cfg.calib_window:
            self.cfg.calib_window = list(rect)
            self._save_cfg()
        if rect:
            self._hide_drift()

    def _calib_problem(self) -> Optional[str]:
        """Écran changé (zones hors de l'écran) ou fenêtre du jeu redimensionnée / déplacée depuis
        la calibration ? Texte du problème, None si rien, "" si le jeu est introuvable (on ne sait pas)."""
        c = self.cfg
        try:
            off = core.zones_off_screen(c, core.screen_bounds())
        except Exception:
            off = []
        if off:
            names = ", ".join(dict.fromkeys(self.OFF_LABELS.get(z, z) for z in off))
            return (f"Calibration à refaire : des zones sont hors de l'écran ({names}). Écran "
                    "débranché ou résolution changée ?")
        try:
            rect = core.game_window_rect(c)
        except Exception:
            rect = None
        if rect is None:                       # jeu pas lancé (ou réduit)
            return ""
        why = core.calib_drift(c.calib_window, rect, bool(c.anchor_region))
        return f"La calibration semble décalée : {why}." if why else None

    def _check_calibration(self):
        """Toutes les 5 s : calibration décalée ? -> bandeau « Recalibrer » et alerte dans le HUD,
        qui disparaissent d'eux-mêmes quand c'est réglé."""
        try:
            if self._calibrated() and self._loop is None and not self.closing:
                text = self._calib_problem()
                if text is None:
                    self._drift_ignored = None
                    if self._drift_text:
                        self._hide_drift()
                elif text and text != self._drift_ignored:
                    self._show_drift(text)
        except Exception:
            pass
        if not self.closing:
            self.after(CALIB_WATCH_MS, self._check_calibration)

    def _show_drift(self, text: str):
        self.drift_lbl.configure(text=text)
        if text != self._drift_text:
            self._drift_text = text
            self._calib_alert_t = time.time()
        if not self.drift_bar.winfo_manager():
            self.drift_bar.pack(fill="x", padx=12, pady=(0, 6))
            self._log(f"[Calib] {text}", "WARN")
            self._hud_flash(style.CHIP["orange"][1], 2500)
        self._refresh_hud()

    def _hide_drift(self):
        self._drift_text = None
        if self.drift_bar.winfo_manager():
            self.drift_bar.pack_forget()
        self._refresh_hud()

    def _ignore_drift(self):
        try:
            rect = core.game_window_rect(self.cfg)
        except Exception:
            rect = None
        if rect:
            self.cfg.calib_window = list(rect)    # nouvelle référence : plus d'alerte pour cette fenêtre
            self._save_cfg()
        self._drift_ignored = self._drift_text    # zones hors de l'écran : ne revient pas toutes les 5 s
        self._hide_drift()

    # ---- profil automatique selon le personnage
    def _auto_profile(self) -> Optional[str]:
        """Le jeu au premier plan montre un personnage qui a un autre profil : on le prend.
        Appelé par la surveillance (thread UI) et avant chaque touche de jeu (thread de travail).
        Retourne le message à afficher, ou None."""
        c = self.cfg
        info = core.foreground_info()
        if not info or not core.is_game_window(*info, c):
            return None
        char = core.character_from_title(info[0])
        if not char:
            return None
        self._char = char
        if not c.auto_profile:
            return None
        with self._profile_lock:
            target = core.profile_for_character(char, c.character_profiles, c.profile_names())
            if not target or target == c.profile:
                return None
            c.switch_profile(target)
            c.character_profiles[char] = target
            c.save()
        return f"[Profil] « {target} » activé pour {char}."

    def _on_auto_profile(self, msg: str):
        self.profile_menu.configure(values=self.cfg.profile_names())
        self.profile_var.set(self.cfg.profile)
        self.hdv_state = None
        self._log(msg, "CAL")
        self._refresh_status()
        self._refresh_character()
        self._refresh_profile_colors()
        self._hud_message(f"Profil « {self.cfg.profile} »", self._char or "", P["cyan"])

    def _refresh_character(self):
        lbl = getattr(self, "char_lbl", None)
        if lbl is None:
            return
        c, char = self.cfg, self._char
        if not char:
            return
        linked = core.profile_for_character(char, c.character_profiles, c.profile_names())
        if linked:
            lbl.configure(text=f"Personnage : {char}  →  profil « {linked} »", text_color=P["text"])
        else:
            lbl.configure(text=f"Personnage : {char}  —  aucun profil associé", text_color=MUTED)
        if linked != c.profile:
            self.char_btn.configure(text=f"Associer à « {c.profile} »")
            if not self.char_btn.winfo_ismapped():
                self.char_btn.pack(side="right")
        else:
            self.char_btn.pack_forget()

    def _link_character(self):
        if self._char:
            self.cfg.character_profiles[self._char] = self.cfg.profile
            self._save_cfg()
            self._log(f"[Profil] « {self.cfg.profile} » associé à {self._char}.", "CAL")
            self._refresh_character()

    def _watch_game(self):
        """Toutes les 0,7 s : personnage au premier plan (profil auto) et visibilité du HUD."""
        try:
            info = core.foreground_info()
            self._game_fg = bool(info and core.is_game_window(*info, self.cfg))
            if self._game_fg:
                before = self._char
                if not self.engine._lock.locked() and self._loop is None:
                    msg = self._auto_profile()
                    if msg:
                        self._on_auto_profile(msg)
                else:
                    self._char = core.character_from_title(info[0]) or self._char
                if self._char != before:
                    self._refresh_character()
            self._hud_visibility()
        except Exception:
            pass
        self.after(700, self._watch_game)

