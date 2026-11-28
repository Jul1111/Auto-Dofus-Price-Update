"""HUD : temps restant, pastille, masquage automatique, Alt maintenu."""
import json

import pytest

from dofus_helper import core

pytest.importorskip("customtkinter")
from dofus_helper import gui  # noqa: E402


def test_eta_text():
    assert gui.eta_text(30, None) is None              # total inconnu
    assert gui.eta_text(3, 0.5) is None                # trop tôt
    assert gui.eta_text(60, 0.02) is None
    assert gui.eta_text(60, 0.95) == "presque fini"     # ~3 s
    assert gui.eta_text(30, 0.5) == "≈ 30 s restantes"
    assert gui.eta_text(60, 0.25) == "≈ 3 min restantes"
    assert gui.eta_text(100, 0.5) == "≈ 2 min restantes"   # 100 s -> arrondi au-dessus


def test_hud_options_saved_and_checked(tmp_path):
    assert "dot" in gui.HUD_CONTENTS and 0 in gui.HUD_AUTOHIDE
    cfg = core.Config()
    assert cfg.hud_autohide == 0 and cfg.hud_alt is True
    cfg.hud_content, cfg.hud_autohide, cfg.hud_alt = "dot", 30, False
    path = tmp_path / "c.json"
    cfg.save(path)
    back = core.Config.load(path)
    assert (back.hud_content, back.hud_autohide, back.hud_alt) == ("dot", 30, False)
    data = json.loads(path.read_text(encoding="utf-8"))
    data.update(HUD_AUTOHIDE=7, HUD_CONTENT="nope")
    path.write_text(json.dumps(data), encoding="utf-8")
    back = core.Config.load(path)
    assert back.hud_autohide == 0 and back.hud_content == "both"


def test_alt_detection_is_safe_off_windows(monkeypatch):
    monkeypatch.setattr(gui.sys, "platform", "linux")
    assert gui.alt_alone_down() is False
