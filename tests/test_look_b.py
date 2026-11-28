"""Apparence (2) : ambiances, animations, journal."""
import json

import pytest

from dofus_helper import core
import dofus_style as style


def test_ambience_tints_only_the_dark_theme():
    night = style.palette("dark", "blue", "night")
    forest = style.palette("dark", "blue", "forest")
    assert night["bg"] == style.DARK["bg"]
    assert forest["bg"] != night["bg"] and forest["text"] == night["text"] and forest["accent"] == night["accent"]
    assert style.palette("light", "blue", "forest")["bg"] == style.LIGHT["bg"]
    assert style.palette("dark", "blue", "nope")["bg"] == style.DARK["bg"]


def test_every_ambience_overrides_known_keys():
    for key, (label, over) in style.AMBIENCES.items():
        assert label and set(over) <= set(style.DARK), key


def test_saved_ambience(tmp_path):
    path = tmp_path / "c.json"
    assert style.saved_ambience(path) == "night"
    path.write_text(json.dumps({"AMBIENCE": "ocean"}), encoding="utf-8")
    assert style.saved_ambience(path) == "ocean"
    path.write_text(json.dumps({"AMBIENCE": "lava"}), encoding="utf-8")
    assert style.saved_ambience(path) == "night"


def test_configure_keeps_ambience():
    try:
        style.configure("dark", "blue", "amber")
        assert style.CURRENT["ambience"] == "amber" and style.P["bg"] == style.AMBIENCES["amber"][1]["bg"]
    finally:
        style.configure("dark", "blue")


def test_config_ambience_is_sanitised(tmp_path):
    path = tmp_path / "cfg.json"
    c = core.Config()
    c.ambience = "lava"
    c.save(path)
    assert core.Config.load(path).ambience == "night"
    c.ambience = "forest"
    c.save(path)
    assert core.Config.load(path).ambience == "forest"


def test_ease_out():
    assert style.ease_out(0) == 0 and style.ease_out(1) == 1
    assert style.ease_out(0.5) > 0.5                       # rapide au début
    assert style.ease_out(-1) == 0 and style.ease_out(2) == 1


def test_smooth_hover_reaches_the_hover_colour():
    ctk = pytest.importorskip("customtkinter")
    try:
        root = ctk.CTk()
    except Exception:
        pytest.skip("pas d'affichage")
    try:
        style.smooth_hover(ctk, lambda: True)
        b = ctk.CTkButton(root, text="x", fg_color="#000000", hover_color="#ffffff")
        b.pack()
        root.update()
        fill = lambda: b._canvas.itemcget(b._canvas.find_withtag("inner_parts")[0], "fill")  # noqa: E731
        assert style.blend(b, "#000000", "#ffffff", 0.5) == "#808080"
        b._on_enter()
        for _ in range(40):
            root.update()
            root.after(10)
        assert fill() == "#ffffff"
        b._on_leave()
        for _ in range(40):
            root.update()
            root.after(10)
        assert fill() == "#000000"
    finally:
        root.destroy()
