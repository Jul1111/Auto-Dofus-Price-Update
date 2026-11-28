"""HUD réglable, couleur par profil, fiabilité de lecture, « Quoi de neuf », sauvegarde."""
import json
import zipfile

import pytest

import dofus_backup
from dofus_helper import core
import dofus_logo
import dofus_style as style

pytest.importorskip("customtkinter")
import dofus_price_helper as gui  # noqa: E402


# ---- « Quoi de neuf »
def test_whats_new_shows_versions_since_last_seen():
    assert [v for v, _ in gui.whats_new("v1.8.0", "v1.9.0")] == ["1.9.0"]
    assert [v for v, _ in gui.whats_new("", "v1.9.0")] == ["1.8.0", "1.9.0"]      # ancienne version
    assert gui.whats_new("v1.9.0", "v1.9.0") == []
    assert gui.whats_new("v1.7.0", "v1.8.0")[-1][0] == "1.8.0"                      # pas de futur
    assert gui.whats_new("", "dev") == []


def test_whats_new_lines_format_with_hotkeys():
    keys = {"pause": "CTRL+ALT+P", "hud": "CTRL+ALT+U", "window": "CTRL+ALT+O"}
    for lines in gui.WHATS_NEW.values():
        for line in lines:
            assert "{" not in line.format(**keys)
    assert all(core.parse_version(v) for v in gui.WHATS_NEW)


# ---- fiabilité de la lecture
def test_reading_quality():
    R = core.Reading
    assert gui.reading_quality(None, 60)[0] is None
    assert gui.reading_quality(R(None, -1, ""), 60)[0] is None
    assert gui.reading_quality(R(1000, 97, "1000"), 60)[0] == "good"
    assert gui.reading_quality(R(1000, 70, "1000"), 60)[0] == "doubt"
    level, why = gui.reading_quality(R(90000, 41, "90 000"), 60)
    assert level == "bad" and "41 %" in why and "« 90 000 »" in why
    assert gui.reading_quality(R(5, 99, "estimé"), 60)[0] == "doubt"


# ---- couleur par profil
def test_profile_color_is_stable_and_choosable():
    a = style.profile_color("Mule", {})
    assert a == style.profile_color("Mule", {}) and a in {c for _, c in style.PROFILE_COLORS.values()}
    assert style.profile_color("Mule", {"Mule": "violet"}) == style.PROFILE_COLORS["violet"][1]
    assert style.profile_color("Mule", {"Mule": "nope"}) == a


def test_profile_colors_saved_and_cleaned(tmp_path):
    cfg = core.Config()
    cfg.new_profile("Mule")
    cfg.profile_colors = {"Mule": "gold"}
    cfg.hud_size, cfg.hud_content, cfg.hud_opacity = "large", "state", 0.7
    path = tmp_path / "c.json"
    cfg.save(path)
    back = core.Config.load(path)
    assert back.profile_colors == {"Mule": "gold"}
    assert (back.hud_size, back.hud_content, back.hud_opacity) == ("large", "state", 0.7)
    back.switch_profile("Principal")
    back.delete_profile("Mule")
    assert back.profile_colors == {}


def test_tray_icon_ring():
    img = dofus_logo.logo_with_dot("#3ecf8e", 64, ring="#b392f0")
    assert img.size == (64, 64) and img.getpixel((32, 1))[:3] == (0xb3, 0x92, 0xf0)
    assert dofus_logo.logo_with_dot("#3ecf8e", 64).getpixel((32, 1))[:3] != (0xb3, 0x92, 0xf0)


# ---- sauvegarde / restauration
def _setup(base):
    base.mkdir()
    (base / core.CONFIG_PATH.name).write_text(json.dumps({"PROFILE": "Mule", "PROFILES": {"Principal": {}}}),
                                              encoding="utf-8")
    (base / "hdv_anchor.png").write_bytes(b"png1")
    (base / core.DIGITS_PATH.name).write_bytes(b"npz")
    (base / "dofus_price_history.csv").write_text("ventes", encoding="utf-8")   # pas sauvegardé


def test_backup_round_trip(tmp_path):
    base = tmp_path / "a"
    _setup(base)
    zpath = dofus_backup.make_backup(tmp_path / "s.zip", base)
    info = dofus_backup.read_backup(zpath)
    assert info["profiles"] == ["Mule", "Principal"]
    assert "dofus_price_history.csv" not in info["files"] and "hdv_anchor.png" in info["files"]
    # autre PC : rien, ou d'autres réglages
    other = tmp_path / "b"
    other.mkdir()
    (other / core.CONFIG_PATH.name).write_text('{"PROFILE": "Autre"}', encoding="utf-8")
    keep = dofus_backup.restore_backup(zpath, other)
    assert json.loads((other / core.CONFIG_PATH.name).read_text(encoding="utf-8"))["PROFILE"] == "Mule"
    assert (other / "hdv_anchor.png").read_bytes() == b"png1"
    with zipfile.ZipFile(keep) as z:                       # anciens réglages gardés
        assert json.loads(z.read(core.CONFIG_PATH.name))["PROFILE"] == "Autre"


def test_backup_refuses_bad_files_and_never_writes_outside(tmp_path):
    bad = tmp_path / "x.zip"
    bad.write_bytes(b"pas un zip")
    with pytest.raises(ValueError):
        dofus_backup.read_backup(bad)
    nocfg = tmp_path / "n.zip"
    with zipfile.ZipFile(nocfg, "w") as z:
        z.writestr("autre.txt", "x")
    with pytest.raises(ValueError):
        dofus_backup.read_backup(nocfg)
    evil = tmp_path / "e.zip"
    with zipfile.ZipFile(evil, "w") as z:
        z.writestr(core.CONFIG_PATH.name, "{}")
        z.writestr("../hdv_anchor.png", "x")
        z.writestr("sub/hdv_anchor.png", "x")
        z.writestr("virus.exe", "x")
    base = tmp_path / "c"
    base.mkdir()
    dofus_backup.restore_backup(evil, base)
    assert sorted(f.name for f in base.iterdir() if f.is_file()) == [core.CONFIG_PATH.name]
    assert not (tmp_path / "hdv_anchor.png").exists()


def test_backup_needs_a_config(tmp_path):
    with pytest.raises(ValueError):
        dofus_backup.make_backup(tmp_path / "s.zip", tmp_path)
