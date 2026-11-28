"""Renommer un profil, touche afficher / cacher la fenêtre, rappel « Entrée pour valider »."""
import pytest

from dofus_helper import core


def test_rename_active_default_profile_moves_everything(tmp_path, monkeypatch):
    monkeypatch.setattr(core, "ANCHOR_PATH", tmp_path / "hdv_anchor.png")
    cfg = core.Config()
    cfg.table_region = [1, 2, 3, 4]
    core.ANCHOR_PATH.write_bytes(b"repere")
    cfg.character_profiles = {"Perso": "Principal"}
    cfg.profile_colors = {"Principal": "gold"}
    cfg.rename_profile("Principal", "Ungrottas")
    assert cfg.profile == "Ungrottas" and cfg.profile_names() == ["Ungrottas"]
    assert cfg.table_region == [1, 2, 3, 4]
    assert cfg.character_profiles == {"Perso": "Ungrottas"} and cfg.profile_colors == {"Ungrottas": "gold"}
    assert not core.ANCHOR_PATH.exists() and core.anchor_path(cfg).read_bytes() == b"repere"
    path = tmp_path / "c.json"
    cfg.save(path)
    back = core.Config.load(path)
    assert back.profile == "Ungrottas" and back.table_region == [1, 2, 3, 4]


def test_rename_inactive_profile_and_errors(tmp_path, monkeypatch):
    monkeypatch.setattr(core, "ANCHOR_PATH", tmp_path / "hdv_anchor.png")
    cfg = core.Config()
    cfg.new_profile("Mule")
    cfg.qty_region = [5, 6, 7, 8]                         # zone propre à Mule
    cfg.switch_profile("Principal")
    cfg.rename_profile("Mule", "Mule 2")
    assert cfg.profile == "Principal" and "Mule 2" in cfg.profile_names() and "Mule" not in cfg.profile_names()
    cfg.switch_profile("Mule 2")
    assert cfg.qty_region == [5, 6, 7, 8]
    with pytest.raises(ValueError):
        cfg.rename_profile("Mule 2", "principal")          # existe déjà (majuscules ignorées)
    with pytest.raises(ValueError):
        cfg.rename_profile("Mule 2", "  ")
    with pytest.raises(KeyError):
        cfg.rename_profile("Inconnu", "X")
    cfg.rename_profile("Mule 2", "mule 2")                 # même profil, autre casse : permis
    assert cfg.profile == "mule 2"


def test_toggle_window_hotkey():
    pytest.importorskip("customtkinter")
    from dofus_helper import gui
    assert core.DEFAULT_HOTKEYS["toggle_window"] == "ctrl+alt+o"
    others = {k: v for k, v in core.DEFAULT_HOTKEYS.items() if k != "toggle_window"}
    assert gui.hotkey_problem("toggle_window", "ctrl+alt+o", others) is None
    assert "toggle_window" in gui.HOTKEY_LABELS


def test_validate_reminder():
    pytest.importorskip("customtkinter")
    from dofus_helper import gui
    cfg = core.Config()

    def R(msg, level="ok", new=9499):
        return core.Result(10, level, msg, new_price=new)
    assert gui.validate_reminder(R("[VENTE] Lot 10 | Lu: 9500 -> 9499 | saisi"), cfg) == "Prix saisi · Entrée pour valider"
    assert gui.validate_reminder(R("[OPT] Lot 10 | Lu: 9500 -> 9499 | copié"), cfg) == "Prix copié · Ctrl+V puis Entrée"
    assert gui.validate_reminder(R("[VENTE] Lot 10 | Lu: 9500 -> 9499 | saisi + mis en vente"), cfg) is None
    assert gui.validate_reminder(R("[MAJ] Lot 1 | modifié"), cfg) is None
    assert gui.validate_reminder(R("[VENTE] Lot 10 | SUSPECT … Copié seulement.", "warn"), cfg) is None
    assert gui.validate_reminder(R("[TOUT] 3×10", new=None), cfg) is None
