import pytest

from dofus_helper import core

pytest.importorskip("customtkinter")
from dofus_helper import gui  # noqa: E402


@pytest.mark.parametrize("combo,ok", [
    ("ctrl+f1", True), ("f5", True), ("alt+shift+x", True), ("esc", True),   # esc = annuler
    ("a", False), ("1", False),                    # touche seule : se déclencherait en écrivant
    ("enter", False), ("ctrl+v", False), ("end", False),   # touches tapées par l'outil
    ("ctrl+alt+f1", False),                        # déjà « calibrer le tableau »
    ("", False), ("!erreur", False),
])
def test_hotkey_problem(combo, ok):
    assert (gui.hotkey_problem("sell", combo, dict(core.DEFAULT_HOTKEYS)) is None) is ok


def test_same_key_for_same_action_is_fine():
    assert gui.hotkey_problem("sell", "f1", dict(core.DEFAULT_HOTKEYS)) is None


def test_every_hotkey_has_a_label():
    gui_keys = set(gui.HOTKEY_LABELS)
    assert gui_keys == set(core.DEFAULT_HOTKEYS) - {"quit"}        # « quitter » : CLI seulement
