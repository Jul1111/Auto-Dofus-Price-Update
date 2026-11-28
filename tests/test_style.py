"""Apparence : palette, thème CustomTkinter, teinte du verre."""
import sys

import pytest

from dofus_helper import core
from dofus_helper.gui import style


def test_tint_color_format():
    # Windows attend 0xAABBGGRR
    assert style.tint_color(1.0, (0x11, 0x22, 0x33)) == 0xFF332211
    assert style.tint_color(0.0, (0x11, 0x22, 0x33)) == 0x00332211
    assert style.tint_color(0.6) >> 24 == round(0.6 * 255)


def test_tint_color_is_clamped():
    assert style.tint_color(5) >> 24 == 255
    assert style.tint_color(-1) >> 24 == 0


def test_glass_supported_only_on_windows(monkeypatch):
    monkeypatch.setattr(sys, "platform", "linux")
    assert style.glass_supported() is False


def test_set_glass_is_harmless_when_unsupported(monkeypatch):
    monkeypatch.setattr(style, "glass_supported", lambda: False)
    assert style.set_glass(object(), True) is False


def test_apply_theme_sets_palette():
    ctk = pytest.importorskip("customtkinter")
    style.apply_theme(ctk)
    t = ctk.ThemeManager.theme
    assert t["CTkButton"]["fg_color"] == [style.P["accent"]] * 2
    assert t["CTk"]["fg_color"] == [style.P["bg"]] * 2
    assert t["CTkFont"]["family"] == style.FONT
    assert t["CTkScrollbar"]["fg_color"] == "transparent"      # valeurs non touchées gardées


def test_chip_colors_are_pairs():
    for bg, fg in style.CHIP.values():
        assert bg.startswith("#") and fg.startswith("#")


def test_style_config_round_trip(tmp_path):
    path = tmp_path / "cfg.json"
    cfg = core.Config()
    assert (cfg.ui_style, cfg.glass_opacity) == ("classic", 0.6)
    cfg.ui_style, cfg.glass_opacity = "glass", 0.8
    cfg.save(path)
    back = core.Config.load(path)
    assert (back.ui_style, back.glass_opacity) == ("glass", 0.8)
