"""Thèmes repris du jeu (Options › Thèmes de Dofus 3)."""
from dofus_helper import core
import dofus_style as style


def _lum(c: str) -> float:
    def f(v):
        v /= 255
        return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4
    r, g, b = (f(int(c[i:i + 2], 16)) for i in (1, 3, 5))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def _contrast(a: str, b: str) -> float:
    la, lb = _lum(a), _lum(b)
    return (max(la, lb) + 0.05) / (min(la, lb) + 0.05)


def test_core_knows_every_ambience():
    assert core.AMBIENCE_KEYS == tuple(style.AMBIENCES)


def test_eleven_dofus_themes_with_full_surfaces():
    assert len(style.DOFUS_THEMES) == 11
    for key, (label, over) in style.DOFUS_THEMES.items():
        assert key.startswith("dofus_") and label
        assert {"bg", "card", "card2", "border", "caption", "accent", "accent_hover", "on_accent"} <= set(over)


def test_dofus_theme_forces_dark_and_its_own_accent():
    for theme in ("dark", "light", "system"):
        pal = style.palette(theme, "pink", "dofus_standard")
        over = style.DOFUS_THEMES["dofus_standard"][1]
        assert pal["bg"] == over["bg"] and pal["accent"] == over["accent"] and pal["caption"] == over["caption"]
        assert pal["text"] == style.DARK["text"]


def test_caption_follows_background_outside_dofus_themes():
    assert style.palette("dark", "blue", "forest")["caption"] == style.AMBIENCES["forest"][1]["bg"]
    assert style.palette("light", "blue", "night")["caption"] == style.LIGHT["bg"]


def test_configure_dofus_theme_is_dark():
    try:
        style.configure("light", "blue", "dofus_braise")
        assert style.is_dark() and style.CURRENT["ambience"] == "dofus_braise"
        assert style.P["caption"] == style.DOFUS_THEMES["dofus_braise"][1]["caption"]
    finally:
        style.configure("dark", "blue")


def test_dofus_themes_stay_readable():
    for key in style.DOFUS_THEMES:
        p = style.palette("dark", "blue", key)
        assert _contrast(p["on_accent"], p["accent"]) >= 4.5, key
        assert _contrast(p["on_accent"], p["accent_hover"]) >= 4.5, key
        assert _contrast(p["text"], p["card2"]) >= 7, key
        assert _contrast(p["muted"], p["card"]) >= 4.5, key
        assert _contrast(p["text"], p["caption"]) >= 4.5, key


def test_config_keeps_a_dofus_theme(tmp_path):
    path = tmp_path / "cfg.json"
    c = core.Config()
    c.ambience = "dofus_jade"
    c.save(path)
    assert core.Config.load(path).ambience == "dofus_jade"
    assert style.saved_ambience(path) == "dofus_jade"
