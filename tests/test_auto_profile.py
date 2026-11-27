"""Profil automatique selon le personnage, HUD discret."""
import pytest

import dofus_core as core


def test_character_from_title():
    assert core.character_from_title("Ungrottas-Forge - Forgelance - 3.7.14.18 - Release") == "Ungrottas-Forge"
    assert core.character_from_title("Xelorette - Xélor - 3.7.14.18 - Release") == "Xelorette"
    for title in ("Dofus", "Ankama Launcher", "", None, " - Iop - 3.7 - Release"):
        assert core.character_from_title(title) is None


def test_profile_for_character():
    names = ["Principal", "Mule", "Xelorette"]
    assert core.profile_for_character("Perso", {"Perso": "Mule"}, names) == "Mule"
    assert core.profile_for_character("perso", {"Perso": "Mule"}, names) == "Mule"         # majuscules
    assert core.profile_for_character("XELORETTE", {}, names) == "Xelorette"              # même nom
    assert core.profile_for_character("Perso", {"Perso": "Supprimé"}, names) is None      # profil disparu
    assert core.profile_for_character("Autre", {"Perso": "Mule"}, names) is None
    assert core.profile_for_character(None, {"Perso": "Mule"}, names) is None


def test_config_fields_and_cleanup(tmp_path):
    cfg = core.Config()
    assert cfg.auto_profile is True and cfg.character_profiles == {} and cfg.hud is False
    assert cfg.hotkeys["hud"] == "ctrl+alt+u"
    cfg.new_profile("Mule")
    cfg.character_profiles = {"Perso": "Mule", "Autre": "Principal"}
    cfg.hud, cfg.hud_pos = True, [400, 120]
    path = tmp_path / "c.json"
    cfg.save(path)
    back = core.Config.load(path)
    assert back.character_profiles == {"Perso": "Mule", "Autre": "Principal"}
    assert back.hud is True and back.hud_pos == [400, 120]
    back.switch_profile("Principal")
    back.delete_profile("Mule")                     # ses personnages n'y renvoient plus
    assert back.character_profiles == {"Autre": "Principal"}


def test_bad_character_profiles_value_is_ignored(tmp_path):
    path = tmp_path / "c.json"
    path.write_text('{"CHARACTER_PROFILES": {"Perso": 3, "Ok": "Principal"}}', encoding="utf-8")
    assert core.Config.load(path).character_profiles == {"Ok": "Principal"}
    path.write_text('{"CHARACTER_PROFILES": ["x"]}', encoding="utf-8")
    assert core.Config.load(path).character_profiles == {}


def test_hud_hotkey_is_free():
    pytest.importorskip("customtkinter")
    import dofus_price_helper_psg as gui
    others = {k: v for k, v in core.DEFAULT_HOTKEYS.items() if k != "hud"}
    assert gui.hotkey_problem("hud", "ctrl+alt+u", others) is None
    assert "hud" in gui.HOTKEY_LABELS
