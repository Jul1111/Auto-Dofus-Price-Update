import sys
import types
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from dofus_helper import core  # noqa: E402
from dofus_digits import DigitReader  # noqa: E402


@pytest.fixture(autouse=True)
def fresh_digits(monkeypatch):
    """Chaque test part de modèles de chiffres vides, en mémoire (aucun fichier écrit)."""
    monkeypatch.setattr(core, "_digits", DigitReader(None))
    monkeypatch.setattr(core, "_fast_count", 0)


@pytest.fixture(autouse=True)
def no_my_prices_file(monkeypatch, tmp_path):
    """« Tes prix » écrits dans un dossier temporaire, jamais à côté du projet."""
    monkeypatch.setattr(core, "MY_PRICES_PATH", tmp_path / "my_prices.json")


@pytest.fixture(autouse=True)
def debug_dir_in_tmp(monkeypatch, tmp_path):
    """Captures de diagnostic (champ refusé) écrites dans un dossier temporaire."""
    monkeypatch.setattr(core, "DEBUG_DIR", tmp_path / "captures")


@pytest.fixture(autouse=True)
def anchor_in_tmp(monkeypatch, tmp_path):
    """Images du repère (et copies par profil) dans un dossier temporaire, jamais dans le projet."""
    monkeypatch.setattr(core, "ANCHOR_PATH", tmp_path / "hdv_anchor.png")


# ---- Jamais de vraie souris ni de vrai clavier pendant les tests
# Les tests de « Toute la liste » simulent une souris en (0, 0) ; avec le vrai pyautogui, la fin
# du parcours « remettait » la VRAIE souris là, en haut à gauche de l'écran, pendant qu'on jouait.
MOUSE_KEYS = {"click", "doubleClick", "tripleClick", "rightClick", "middleClick", "moveTo", "moveRel", "move",
              "dragTo", "dragRel", "drag", "scroll", "hscroll", "vscroll", "mouseDown", "mouseUp",
              "press", "keyDown", "keyUp", "hotkey", "typewrite", "write"}
KEYBOARD_KEYS = {"press_and_release", "send", "press", "release", "write"}
BLOCKED_INPUTS: list = []          # (module, fonction, arguments) que le code a tenté d'envoyer


class _NoInput(types.ModuleType):
    """Le vrai module (lecture de la position, raccourcis…), sauf ce qui bouge la souris ou
    envoie des touches : noté dans BLOCKED_INPUTS, sans effet."""

    def __init__(self, name, blocked):
        super().__init__(name)
        try:
            self._real = __import__(name)
        except Exception:               # pas d'écran (CI Linux) : seules les fonctions bloquées existent
            self._real = None
        self._blocked = blocked

    def __getattr__(self, attr):
        if attr in self._blocked:
            return lambda *a, **k: BLOCKED_INPUTS.append((self.__name__, attr, a))
        if self._real is None:
            raise AttributeError(attr)
        return getattr(self._real, attr)


_NO_INPUT = {}


@pytest.fixture(autouse=True)
def no_real_input(monkeypatch):
    """pyautogui et keyboard remplacés : un test ne peut ni bouger la souris ni taper dans le jeu.
    (Un test peut toujours mettre son propre faux module par-dessus.)"""
    for name, blocked in (("pyautogui", MOUSE_KEYS), ("keyboard", KEYBOARD_KEYS)):
        if name not in _NO_INPUT:
            _NO_INPUT[name] = _NoInput(name, blocked)
        monkeypatch.setitem(sys.modules, name, _NO_INPUT[name])


def pytest_sessionfinish(session, exitstatus):
    if BLOCKED_INPUTS and session.config.getoption("verbose") > 0:
        print(f"\n[no_real_input] {len(BLOCKED_INPUTS)} actions souris / clavier bloquées pendant les tests.")
