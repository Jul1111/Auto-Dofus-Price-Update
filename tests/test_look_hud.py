"""Apparence du HUD : prix qui défile, respiration, formes."""
import dofus_core as core
import dofus_price_helper_psg as gui


def test_count_value_goes_from_start_to_end():
    assert gui.count_value(52000, 49999, 0) == 52000
    assert gui.count_value(52000, 49999, 1) == 49999
    mid = gui.count_value(0, 1000, 0.5)
    assert 500 < mid < 1000                       # rapide au début, lent à la fin


def test_breath_is_a_smooth_cycle():
    assert gui.breath(0) == 0
    assert abs(gui.breath(gui.HUD_BREATH_S / 2) - 1) < 1e-9
    assert gui.breath(gui.HUD_BREATH_S) < 1e-9
    assert all(0 <= gui.breath(t / 10) <= 1 for t in range(40))


def test_hud_shape_is_saved_and_sanitised(tmp_path):
    path = tmp_path / "cfg.json"
    c = core.Config()
    assert c.hud_shape == "card"
    c.hud_shape = "pill"
    c.save(path)
    assert core.Config.load(path).hud_shape == "pill"
    c.hud_shape = "star"
    c.save(path)
    assert core.Config.load(path).hud_shape == "card"
    assert set(gui.HUD_SHAPES) == {"card", "pill", "minimal"}
