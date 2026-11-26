"""Interface v3 : thème clair / accent, sons doux, calibration décalée, raccourcis de la fenêtre,
journal, zone de notification, logo."""
import json
import struct

import pytest

import dofus_core as core
import dofus_logo
import dofus_style as style

pytest.importorskip("customtkinter")
import dofus_price_helper_psg as gui  # noqa: E402


# ---- thème et couleur d'accent
def test_light_and_dark_palettes_have_the_same_keys():
    assert set(style.DARK) == set(style.LIGHT)
    assert set(style.CHIP_DARK) == set(style.CHIP_LIGHT)


def test_configure_changes_the_active_palette_in_place():
    p = style.P
    try:
        style.configure("light", "amber")
        assert p is style.P and p["bg"] == style.LIGHT["bg"] and p["accent"] == style.ACCENTS["amber"][1]
        assert style.CHIP["red"] == style.CHIP_LIGHT["red"] and not style.is_dark()
        style.configure("dark", "nope")                    # accent inconnu -> bleu
        assert p["bg"] == style.DARK["bg"] and p["accent"] == style.ACCENTS["blue"][1] and style.is_dark()
    finally:
        style.configure("dark", "blue")


def test_palette_preview_does_not_touch_the_active_one():
    before = dict(style.P)
    pal = style.palette("light", "pink")
    assert pal["accent"] == style.ACCENTS["pink"][1] and style.P == before


def test_system_theme_follows_windows(monkeypatch):
    monkeypatch.setattr(style, "windows_light_theme", lambda: True)
    assert style.resolve_theme("system") == "light"
    monkeypatch.setattr(style, "windows_light_theme", lambda: False)
    assert style.resolve_theme("system") == "dark"
    assert style.resolve_theme("bizarre") == "dark"


def test_saved_look_reads_the_config(tmp_path):
    path = tmp_path / "c.json"
    assert style.saved_look(path) == ("dark", "blue")              # pas de fichier
    path.write_text(json.dumps({"THEME": "light", "ACCENT": "cyan"}), encoding="utf-8")
    assert style.saved_look(path) == ("light", "cyan")
    path.write_text(json.dumps({"THEME": "rose", "ACCENT": "?"}), encoding="utf-8")
    assert style.saved_look(path) == ("dark", "blue")


def test_fade_steps_end_on_target():
    steps = style.fade_steps(0.0, 0.96, 130)
    assert steps[-1] == 0.96 and all(a <= b for a, b in zip(steps, steps[1:]))
    assert style.fade_steps(0.9, 0.0, 160)[-1] == 0.0


# ---- sons doux
def test_tone_wav_is_a_valid_wav_scaled_by_volume():
    loud = core.tone_wav(core.SOUND_NOTES["ok"], 1.0)
    assert loud[:4] == b"RIFF" and loud[8:12] == b"WAVE"
    def peak(data):
        n = (len(data) - 44) // 2
        return max(abs(v) for v in struct.unpack(f"<{n}h", data[44:44 + 2 * n]))
    assert peak(core.tone_wav(core.SOUND_NOTES["ok"], 0.0)) == 0
    assert peak(core.tone_wav(core.SOUND_NOTES["ok"], 0.3)) < peak(loud) <= 32767
    assert set(core.SOUND_NOTES) == {"ok", "warn", "error", "done"}


def test_beep_respects_the_switch(monkeypatch):
    played = []
    monkeypatch.setattr(core, "IS_WINDOWS", True)
    monkeypatch.setattr(core.threading, "Thread", lambda target, args, daemon: played.append(args) or
                        type("T", (), {"start": lambda self: None})())
    cfg = core.Config()
    cfg.sound = False
    core.beep("ok", cfg)
    assert played == []
    core.beep("done", cfg, force=True)                    # bouton « Tester »
    assert len(played) == 1


# ---- calibration décalée
def test_calib_drift():
    assert core.calib_drift(None, (0, 0, 1920, 1080), False) is None
    assert core.calib_drift([0, 0, 1920, 1080], (0, 0, 1920, 1080), False) is None
    assert "taille" in core.calib_drift([0, 0, 1920, 1080], (0, 0, 2560, 1440), True)
    assert core.calib_drift([0, 0, 1600, 900], (100, 50, 1600, 900), True) is None   # repère : zones suivent
    assert "bougé" in core.calib_drift([0, 0, 1600, 900], (100, 50, 1600, 900), False)
    assert core.calib_drift([0, 0, 1600, 900], (2, 1, 1601, 900), False) is None      # petite tolérance


def test_zones_off_screen():
    cfg = core.Config()
    cfg.table_region, cfg.qty_region, cfg.price_field = [100, 100, 300, 150], [2000, 100, 80, 30], [50, 3000]
    assert core.zones_off_screen(cfg, (0, 0, 1920, 1080)) == ["qty", "price_field"]
    assert core.zones_off_screen(cfg, (0, 0, 2560, 3200)) == []


def test_new_config_fields_round_trip(tmp_path):
    cfg = core.Config()
    assert (cfg.theme, cfg.accent, cfg.animations, cfg.tray, cfg.tray_minimize) == ("dark", "blue", True, True, False)
    assert "calib_window" in core.PROFILE_FIELDS
    cfg.theme, cfg.accent, cfg.sound_volume = "light", "green", 0.25
    cfg.calib_window, cfg.cheatsheet_pos = [0, 0, 1920, 1080], [40, 60]
    path = tmp_path / "c.json"
    cfg.save(path)
    back = core.Config.load(path)
    assert (back.theme, back.accent, back.sound_volume) == ("light", "green", 0.25)
    assert back.calib_window == [0, 0, 1920, 1080] and back.cheatsheet_pos == [40, 60]


# ---- raccourcis de la fenêtre, journal
def test_tab_shortcuts_work_in_azerty():
    assert gui.tab_index_for_key(49, "ampersand") == 0          # Ctrl+& (touche 1 en AZERTY)
    assert gui.tab_index_for_key(54, "minus") == 5
    assert gui.tab_index_for_key(99, "KP_3") == 2               # pavé numérique
    assert gui.tab_index_for_key(0, "4") == 3
    assert gui.tab_index_for_key(55, "egrave") is None          # 7 : pas d'onglet
    assert len(gui.TAB_NAMES) == 6


def test_log_kind_and_icons():
    assert gui.log_kind("   [VENTE] Lot 10 | mis en vente", "OK") == "sale"
    assert gui.log_kind("[MAJ] Lot 1 | modifié", "OK") == "update"
    assert gui.log_kind("[VENTE] SUSPECT", "WARN") == "warn"
    assert gui.log_kind("[Erreur] x", "ERROR") == "error"
    assert gui.log_kind("[Calib] Tableau", "CAL") == "cal"
    assert gui.log_kind("[Hotkeys] Prêt.", "INFO") == "info"
    assert set(gui.LOG_ICONS) == set(gui.App.ICON_COLORS)


# ---- zone de notification, logo
def test_tray_icon_and_logo_images(tmp_path):
    img = gui.tray_image("#3ecf8e", 64)
    assert img.size == (64, 64) and img.mode == "RGBA"
    assert img.getpixel((51, 51))[:3] == (0x3e, 0xcf, 0x8e)     # pastille d'état
    logo = dofus_logo.logo_image(128)
    assert logo.size == (128, 128) and logo.getpixel((0, 0))[3] == 0 and logo.getpixel((64, 64))[3] == 255
    ico = tmp_path / "l.ico"
    dofus_logo.write_ico(ico)
    assert ico.read_bytes()[:4] == b"\x00\x00\x01\x00"
    assert set(gui.TRAY_STATES) == {"ok", "pause", "loop", "calib"}


def test_relaunch_command(monkeypatch):
    import sys
    monkeypatch.setattr(sys, "argv", ["dofus_price_helper_psg.py"])
    assert gui.relaunch_command() == [sys.executable, "dofus_price_helper_psg.py"]
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "argv", ["DofusPriceHelper.exe"])
    assert gui.relaunch_command() == [sys.executable]
