"""Apparence : icônes, écart de prix, couleurs, états vides."""
import pytest

import dofus_icons
import dofus_price_helper as gui
import dofus_style as style


@pytest.mark.parametrize("name", dofus_icons.NAMES)
def test_every_icon_draws_something(name):
    img = dofus_icons.icon_image(name, "#ffffff", 16)
    assert img.size == (32, 32) and img.mode == "RGBA"
    assert img.getchannel("A").getbbox() is not None       # pas une image vide


def test_unknown_icon_is_an_error():
    with pytest.raises(KeyError):
        dofus_icons.icon_image("nope", "#ffffff", 16)


def test_price_delta():
    assert gui.price_delta(52000, 49999) == ("▼ 4 %", "down")
    assert gui.price_delta(1000, 1100) == ("▲ 10 %", "up")
    assert gui.price_delta(100000, 99999) == ("▼ <1 %", "down")
    assert gui.price_delta(None, 500) is None
    assert gui.price_delta(500, 500) is None
    assert gui.price_delta(500, None) is None


def test_action_entry_has_icon_and_delta():
    from dofus_helper import core
    e = gui.action_entry(core.Result(100, "ok", "[MAJ] Lot 100 | modifié", new_price=49999, old_price=52000))
    assert e["icon"] == "edit" and e["delta"] == ("▼ 4 %", "down")
    e = gui.action_entry(core.Result(10, "ok", "[VENTE] Lot 10 | mis en vente", new_price=9499))
    assert e["icon"] == "tag" and e["delta"] is None


def test_mix_color_and_colorref():
    assert gui.mix_color("#000000", "#ffffff", 0) == "#000000"
    assert gui.mix_color("#000000", "#ffffff", 1) == "#ffffff"
    assert gui.mix_color("#000000", "#ff8000", 0.5) == "#804000"
    assert style.colorref("#102030") == 0x302010


def test_faded_keeps_size_and_lowers_alpha():
    from PIL import Image
    img = Image.new("RGBA", (4, 4), (255, 0, 0, 200))
    out = gui.faded(img, 0.5)
    assert out.size == img.size and out.getpixel((0, 0))[3] == 100 and img.getpixel((0, 0))[3] == 200
