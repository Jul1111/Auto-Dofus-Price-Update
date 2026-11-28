"""HUD : prix de l'objet sélectionné, mise en page responsive, zone de notification."""
import threading

import numpy as np
import pytest

from dofus_helper import core

pytest.importorskip("customtkinter")
from dofus_helper import gui  # noqa: E402


def test_selected_lines_one_per_lot_with_unit_price():
    lines = gui.hud_selected_lines({1: 9499, 10: 92000, 100: 880000})
    assert [t.split()[0] for t, _c in lines] == ["x1", "x10", "x100"]
    assert "9 499" in lines[0][0] and "/u" not in lines[0][0]
    assert "92 000" in lines[1][0] and "9 200/u" in lines[1][0]
    assert all(c is None for _t, c in lines)


def test_selected_quantity_is_highlighted_and_missing_price_shown():
    lines = gui.hud_selected_lines({1: 500, 10: None, 100: 40000}, selected=100)
    assert lines[2][0].startswith("◆ ") and lines[2][1] == "gold"
    assert "—" in lines[1][0] and lines[1][1] is None
    assert lines[0][0].startswith("  ")


def test_table_signature_changes_with_the_image():
    a = np.zeros((60, 120, 3), dtype=np.uint8)
    b = a.copy()
    b[20:40, 30:90] = 200
    assert gui.table_signature(a) == gui.table_signature(a.copy())
    assert gui.table_signature(a) != gui.table_signature(b)
    c = a.copy()
    c[0, 1] = 5                      # bruit minime : même empreinte
    assert gui.table_signature(a) == gui.table_signature(c)


def test_layout_for_breakpoints():
    wide = gui.layout_for(1200, 860)
    assert wide == {"side": True, "subtitle": True, "log_hint": True, "log_lines": 6}
    narrow = gui.layout_for(900, 700)
    assert narrow["side"] is False and narrow["subtitle"] and narrow["log_hint"] and narrow["log_lines"] == 5
    assert gui.layout_for(800, 900)["log_hint"] is False
    tiny = gui.layout_for(650, 560)
    assert tiny["subtitle"] is False and tiny["log_lines"] == 4


def test_peek_never_runs_during_an_action():
    cfg = core.Config()
    cfg.table_region = [0, 0, 10, 10]
    eng = core.PriceEngine(cfg)
    with eng._lock:
        result = []
        t = threading.Thread(target=lambda: result.append(eng.peek()))
        t.start()
        t.join(2)
        assert result == [None]


def test_peek_needs_a_table():
    eng = core.PriceEngine(core.Config())
    assert eng.peek() is None
