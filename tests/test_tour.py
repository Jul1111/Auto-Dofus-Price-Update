"""Visite guidée : étapes, placement de la bulle, montrée seulement aux nouvelles installations."""
import json

import pytest

from dofus_helper import core

pytest.importorskip("customtkinter")
import dofus_price_helper as gui  # noqa: E402


def test_tour_steps_use_current_hotkeys():
    steps = gui.tour_steps(core.Config().hotkeys)
    assert len(steps) == 5
    assert all("{" not in s["text"] and s["tab"] in gui.TAB_NAMES for s in steps)
    hk = dict(core.Config().hotkeys, pause="ctrl+shift+k")
    assert any("CTRL+SHIFT+K" in s["text"] for s in gui.tour_steps(hk))


AREA = (0, 0, 1000, 700)


def test_tour_place_prefers_below_then_above_then_side():
    assert gui.tour_place((100, 100, 200, 40), (300, 150), AREA) == (100, 152)           # dessous
    assert gui.tour_place((100, 600, 200, 60), (300, 150), AREA) == (100, 438)           # dessus
    assert gui.tour_place((20, 20, 500, 660), (300, 150), AREA) == (532, 20)             # à droite
    x, y = gui.tour_place((900, 100, 90, 30), (300, 150), AREA)                         # bord droit
    assert x + 300 <= 1000 and y == 142
    assert gui.tour_place(None, (300, 150), AREA) == (350, 275)                          # centrée


def test_tour_only_for_new_installs(tmp_path):
    assert core.Config().tour_done is False                       # aucun fichier : nouvelle installation
    path = tmp_path / "c.json"
    path.write_text(json.dumps({"CONFIG_VERSION": 6, "PROFILE": "Principal"}), encoding="utf-8")
    assert core.Config.load(path).tour_done is True               # mise à jour : pas de visite imposée
    cfg = core.Config()
    cfg.save(path)
    assert core.Config.load(path).tour_done is False              # nouvelle install pas encore vue
