import csv
import json
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import dofus_core as core  # noqa: E402


# ---------------- compute_price / smart_round ----------------
@pytest.mark.parametrize("price,mode,value,rounding,expected", [
    (3969, "fixed", 1, "none", 3968),
    (1002, "fixed", 1, "end_9", 999),      # ancien bug : donnait 1009 (> concurrent)
    (1010, "fixed", 1, "end_9", 1009),
    (1019, "fixed", 1, "end_9", 1009),
    (1250, "fixed", 1, "down_100", 1200),
    (1200, "fixed", 0, "down_100", 1199),  # arrondi = prix -> forcé à prix-1
    (36, "percent", 1, "none", 35),        # 1% de 36 arrondi donnait 36 (pas d'undercut)
    (10000, "percent", 5, "none", 9500),
    (1, "fixed", 1, "none", 1),            # plancher min_price
])
def test_compute_price(price, mode, value, rounding, expected):
    assert core.compute_price(price, mode, value, rounding, 1) == expected


def test_compute_price_always_below_competitor():
    for p in range(2, 3000):
        for mode, val in (("fixed", 1), ("fixed", 0), ("percent", 0.5), ("percent", 3)):
            for rnd in ("none", "down_10", "down_100", "end_9"):
                assert core.compute_price(p, mode, val, rnd, 1) < p


def test_compute_price_none_and_bad_value():
    assert core.compute_price(None, "fixed", 1, "none", 1) is None
    assert core.compute_price(100, "fixed", "abc", "none", 1) == 99


# ---------------- pick_best_lot / coherence / derive ----------------
def test_pick_best_lot():
    # valeurs de la capture HDV : 35 / 184 / 1789 / 17875
    assert core.pick_best_lot({1: 35, 10: 184, 100: 1789, 1000: 17875}) == 1
    assert core.pick_best_lot({1: 100, 10: 1200, 100: 8000}) == 10
    assert core.pick_best_lot({1: 100, 10: 1005}, 0.01) == 1      # ex aequo -> petit lot
    assert core.pick_best_lot({1: 100, 10: 1005}, 0.0) == 10
    assert core.pick_best_lot({1: None, 10: None}) is None


def test_coherence():
    assert core.check_coherence(100, {1: 1240, 10: 12398, 100: 12398}, 5) is not None
    assert core.check_coherence(1, {1: 35, 10: 184, 100: 1789, 1000: 17875}, 5) is None
    assert core.check_coherence(1, {1: 50, 10: None}, 5) is None


def test_derive_price():
    assert core.derive_price(1000, {1: 35, 10: 184, 100: 1789}) == 17890  # 17.89/u
    assert core.derive_price(10, {10: None}) is None


def test_rect_from_points_any_order():
    assert core.rect_from_points((232, 620), (88, 482)) == (88, 482, 144, 138)


# ---------------- OCR parsing ----------------
def _data(rows):
    keys = ["text", "left", "top", "width", "height", "conf", "block_num", "par_num", "line_num"]
    return {k: [r[i] for r in rows] for i, k in enumerate(keys)}


def test_parse_table_maps_rows_by_lot_column():
    # largeur utile 200 px, bordure 10 : lot à gauche (x<0.45), prix à droite
    data = _data([
        ("1", 15, 10, 8, 20, 96, 1, 1, 1), ("35", 170, 10, 20, 20, 95, 1, 1, 1),
        ("100", 15, 60, 25, 20, 96, 1, 1, 2), ("789", 180, 60, 25, 20, 90, 1, 1, 2),
        ("1", 160, 60, 8, 20, 88, 1, 1, 2),        # "1 789" dans le désordre
        ("7", 15, 110, 8, 20, 50, 1, 1, 3), ("12", 170, 110, 20, 20, 90, 1, 1, 3),  # lot inconnu
    ])
    out = core.parse_table(data, (0, 200), 200, 0.45, [1, 10, 100, 1000])
    assert {l: (r.value, r.confidence) for l, r in out.items()} == {1: (35, 95), 100: (1789, 88)}


def test_parse_number_and_empty():
    data = _data([("1", 15, 10, 8, 20, 91, 1, 1, 1)])
    assert core.parse_number(data, (0, 50)).value == 1
    assert core.parse_number(data, (60, 90)).value is None


def test_stack_images():
    imgs = [np.full((20, 50), 255, np.uint8), np.full((30, 80), 255, np.uint8)]
    comp, bounds = core.stack_images(imgs, gap=10)
    assert comp.shape == (60, 80) and bounds == [(0, 20), (30, 60)]


def test_preprocess_inverts_and_removes_colored_icons():
    img = np.full((20, 60, 3), 30, np.uint8)     # fond sombre
    img[5:15, 10:20] = 255                       # texte blanc
    img[5:15, 40:50] = (0, 200, 255)             # icône jaune (BGR)
    out = core.preprocess(img, scale=2)
    b = core.BORDER
    assert out.mean() > 127                      # fond devenu blanc
    assert out[b + 20, b + 30] == 0              # texte devenu noir
    assert out[b + 20, b + 90] == 255            # icône effacée


# ---------------- Config ----------------
def test_config_v1_migration(tmp_path):
    v1 = {"PRICE_REGIONS": {"1": [1041, 825, 130, 36]}, "UNDERCUT_MODE": "percent",
          "UNDERCUT_VALUE": 1.5, "AUTO_PASTE": True, "WINDOW_TITLE": "Dofus",
          "HOTKEYS": {"read": {"1": "f1"}, "calibrate_field": "ctrl+alt+f4", "optimize": "f4"}}
    p = tmp_path / "cfg.json"
    p.write_text(json.dumps(v1))
    cfg = core.Config.load(p)
    assert cfg.undercut_value == 1.5 and cfg.auto_paste is True
    assert cfg.hotkeys == core.DEFAULT_HOTKEYS           # raccourcis v1 remplacés
    assert cfg.window_title == " - Release"
    assert cfg.lots == [1, 10, 100, 1000] and cfg.table_region is None
    cfg.save(p)
    data = json.loads(p.read_text())
    assert data["CONFIG_VERSION"] == core.CONFIG_VERSION and "PRICE_REGIONS" not in data
    assert cfg.input_method == "paste" and cfg.clear_method == "backspace"


def test_config_v2_keeps_custom_hotkeys(tmp_path):
    p = tmp_path / "cfg.json"
    p.write_text(json.dumps({"CONFIG_VERSION": 4, "HOTKEYS": {"sell": "f6"}, "MIN_PRICE": "abc",
                             "INPUT_METHOD": "type"}))
    cfg = core.Config.load(p)
    assert cfg.hotkeys["sell"] == "f6" and cfg.hotkeys["optimize"] == "f4"
    assert cfg.min_price == 1
    assert cfg.input_method == "type"                # choix explicite v4 conservé


# ---------------- Historique ----------------
def test_history_rotates_legacy_file(tmp_path):
    h = tmp_path / "hist.csv"
    h.write_text("ts,action,lot\n1,x,1\n")
    core.log_history("sell", 1, 1, core.Reading(100, 90), 99, "collé", core.Config(), path=h)
    assert h.read_text().splitlines()[0] == ",".join(core.HISTORY_HEADER)
    assert len(list(tmp_path.glob("hist_old_*.csv"))) == 1


# ---------------- Détection de la fenêtre du jeu ----------------
@pytest.mark.parametrize("title,exe,expected", [
    ("Ungrottas - Sadida - 3.4.12.5 - Release", "Dofus.exe", True),
    ("Ungrottas - Sadida - 3.4.12.5 - Release", "", True),
    ("Autre - Iop - 3.4 - Release", "Dofus.exe", True),
    ("Discord", "Discord.exe", False),
    ("Dofus wiki - Chrome", "chrome.exe", False),
])
def test_is_game_window(title, exe, expected):
    assert core.is_game_window(title, exe, core.Config()) is expected


# ---------------- Moteur (sans écran) ----------------
R = core.Reading
FULL = {1: R(35, 95), 10: R(184, 96), 100: R(1789, 90), 1000: R(17875, 92)}


@pytest.fixture
def engine(monkeypatch):
    calls = []
    monkeypatch.setattr(core, "input_price", lambda v, c, paste=True, validate=False:
                        calls.append((v, paste, validate)) or
                        ("collé + mis en vente" if validate else "collé" if paste else "copié"))
    monkeypatch.setattr(core, "log_history", lambda *a, **k: None)
    cfg = core.Config(table_region=[0, 0, 1, 1], qty_region=[0, 0, 1, 1],
                      auto_paste=True, auto_validate=True)
    eng = core.PriceEngine(cfg)

    def screen(prices, selected):
        monkeypatch.setattr(core, "read_screen", lambda c, d=None: core.ScreenRead(dict(prices), selected))
    return eng, calls, screen


def test_sell_selected_quantity(engine):
    eng, calls, screen = engine
    screen(FULL, 100)
    res = eng.sell()
    assert res.level == "ok" and res.lot == 100
    assert calls == [(1788, True, True)]


def test_sell_selected_quantity_unreadable(engine):
    eng, calls, screen = engine
    screen(FULL, None)
    assert eng.sell().level == "error" and calls == []


def test_optimize_asks_to_change_quantity(engine):
    eng, calls, screen = engine
    screen({1: R(35, 95), 10: R(184, 96)}, 10)       # meilleur = lot 1 (35/u), quantité = 10
    res = eng.sell(optimize=True)
    assert res.level == "warn" and res.lot == 1 and "quantité 1" in res.hint
    assert calls == []                                 # rien collé : mauvaise quantité


def test_optimize_matching_quantity(engine):
    eng, calls, screen = engine
    screen(FULL, 1)
    res = eng.sell(optimize=True)
    assert res.level == "ok" and calls == [(34, True, True)]


def test_missing_lot_is_estimated_then_forced(engine):
    eng, calls, screen = engine
    screen({1: R(35, 95), 10: R(184, 96), 100: R(1789, 90)}, 1000)  # personne ne vend lot 1000
    r1 = eng.sell()
    assert r1.level == "warn" and calls[-1] == (17889, False, False)
    r2 = eng.sell()                                     # 2e appui = forcer, sans validation auto
    assert r2.level == "ok" and calls[-1] == (17889, True, False)


def test_low_confidence_never_autovalidates(engine):
    eng, calls, screen = engine
    screen({1: R(500, 30)}, 1)
    assert eng.sell().level == "warn"
    assert calls == [(499, False, False)]


def test_calibrate_rect_two_presses(tmp_path, monkeypatch):
    monkeypatch.setattr(core.Config, "save", lambda self, path=None: None)
    eng = core.PriceEngine(core.Config())
    assert eng.calibrate_rect("table", (232, 620))[0] == "first"
    state, region = eng.calibrate_rect("table", (88, 482))
    assert state == "done" and eng.cfg.table_region == [88, 482, 144, 138]
    eng.calibrate_point("price_field", (100, 205))
    assert eng.cfg.click_field is True


# ---------------- Saisie dans le jeu (claviers simulés) ----------------
class _Fake:
    def __init__(self):
        self.log = []
        self.clip = "ancien"


@pytest.fixture
def fake_io(monkeypatch):
    import types
    f = _Fake()
    kb = types.SimpleNamespace(press_and_release=lambda k: f.log.append(k))
    pg = types.SimpleNamespace(click=lambda x, y: f.log.append(f"click{(x, y)}"),
                               moveTo=lambda x, y: f.log.append(f"move{(x, y)}"),
                               position=lambda: (5, 5))
    pc = types.SimpleNamespace(copy=lambda t: setattr(f, "clip", t), paste=lambda: f.clip)
    monkeypatch.setitem(sys.modules, "keyboard", kb)
    monkeypatch.setitem(sys.modules, "pyautogui", pg)
    monkeypatch.setitem(sys.modules, "pyperclip", pc)
    monkeypatch.setattr(core.time, "sleep", lambda s: None)
    monkeypatch.setattr(core, "_clip_timer", None)   # pas d'état partagé entre tests
    monkeypatch.setattr(core, "_clip_saved", None)
    return f


def _flush_restore():
    t = core._clip_timer
    if t is not None:
        t.cancel()
        t.function()                                 # exécute la restauration tout de suite


def test_input_default_clears_then_pastes(fake_io, monkeypatch):
    monkeypatch.setattr(core, "read_mine", lambda c, **k: core.Reading(689, 95))  # champ relu = bon prix
    cfg = core.Config(price_field=[100, 205], click_field=True, sell_button=[110, 370])
    assert core.input_price(689, cfg, paste=True, validate=True) == "saisi + mis en vente"
    assert fake_io.log == (["click(100, 205)", "end"] + ["backspace"] * 12
                           + ["ctrl+v", "enter", "move(5, 5)"])  # Entrée par défaut, pas de clic
    assert fake_io.clip == "689"                     # prix encore là pendant que le jeu colle
    _flush_restore()
    assert fake_io.clip == "ancien"                  # presse-papier de l'utilisateur restauré


def test_rapid_pastes_never_paste_user_text(fake_io, monkeypatch):
    # « Tout vendre » : ventes enchaînées avant la restauration -> chaque Ctrl+V doit voir le prix
    seen = []
    kb = sys.modules["keyboard"]
    monkeypatch.setattr(kb, "press_and_release",
                        lambda k: seen.append(fake_io.clip) if k == "ctrl+v" else None)
    for _ in range(3):
        core.input_price(69, core.Config())
    assert seen == ["69", "69", "69"]
    _flush_restore()
    assert fake_io.clip == "ancien"                  # le texte d'origine, pas "69"


def test_clipboard_failure_does_not_paste(fake_io, monkeypatch):
    pc = sys.modules["pyperclip"]
    monkeypatch.setattr(pc, "copy", lambda t: None)  # presse-papier bloqué : reste "ancien"
    with pytest.raises(RuntimeError):
        core.input_price(69, core.Config())
    assert "ctrl+v" not in fake_io.log


def test_input_type_mode(fake_io):
    cfg = core.Config(input_method="type")
    core.input_price(689, cfg)
    assert fake_io.log[-3:] == ["6", "8", "9"] and fake_io.clip == "ancien"


def test_validate_with_enter_when_no_button(fake_io):
    core.input_price(689, core.Config(), validate=True)
    assert fake_io.log[-1] == "enter"


def test_validate_click_option(fake_io):
    cfg = core.Config(validate_method="click", sell_button=[110, 370])
    core.input_price(689, cfg, validate=True)
    assert fake_io.log[-2:] == ["click(110, 370)", "move(5, 5)"]
    fake_io.log.clear()
    core.press_validate(cfg)
    assert fake_io.log == ["click(110, 370)", "move(5, 5)"]


def test_press_validate_default_is_enter(fake_io):
    core.press_validate(core.Config(sell_button=[110, 370]))
    assert fake_io.log == ["enter"]


def test_input_copy_only(fake_io):
    assert core.input_price(689, core.Config(), paste=False) == "copié"
    assert fake_io.log == [] and fake_io.clip == "689"


def test_input_paste_mode(fake_io):
    cfg = core.Config(input_method="paste", clear_method="ctrl_a")
    core.input_price(689, cfg)
    assert fake_io.log == ["ctrl+a", "ctrl+v"]
    _flush_restore()


def test_ocr_config_survives_windows_shlex():
    # pytesseract sous Windows : shlex.split(config, posix=False)
    import shlex
    for posix in (False, True):
        args = shlex.split(core.OCR_CONFIG, posix=posix)
        assert args[:3] == ["--psm", "6", "-c"] and len(args) == 4
    assert not any(q in core.OCR_CONFIG for q in "\"'\\")
    assert not any(d in args[3] for d in "0123456789")  # les chiffres ne sont pas bloqués


def test_optimize_ignores_lots_above_displayed_quantity(engine):
    # quantité affichée 1 = moins de 10 objets : lot 100 impossible même s'il est meilleur
    eng, calls, screen = engine
    screen({1: R(600, 95), 10: R(6939, 95), 100: R(99997, 95)}, 1)
    res = eng.sell(optimize=True)
    assert res.level == "ok" and res.lot == 1 and calls == [(599, True, True)]


def test_optimize_can_suggest_smaller_lot(engine):
    eng, calls, screen = engine
    screen({1: R(900, 95), 10: R(6939, 95), 100: R(69997, 95)}, 100)  # lot 1 = 900/u
    res = eng.sell(optimize=True)
    assert res.level == "warn" and res.lot == 1 and calls == []


# ---------------- « Tout vendre » (F2) et prix déjà à toi ----------------
@pytest.fixture
def seq_engine(monkeypatch):
    """Moteur dont read_screen renvoie une suite d'écrans."""
    calls = []
    monkeypatch.setattr(core, "input_price", lambda v, c, paste=True, validate=False:
                        calls.append((v, paste, validate)) or
                        ("saisi + mis en vente" if validate else "saisi" if paste else "copié"))
    monkeypatch.setattr(core, "log_history", lambda *a, **k: None)
    monkeypatch.setattr(core, "press_validate", lambda c, expected=None: calls.append("enter") or True)
    monkeypatch.setattr(core.time, "sleep", lambda s: None)
    monkeypatch.setattr(core, "grab_screen", lambda r: np.zeros((2, 2, 3), np.uint8))
    monkeypatch.setattr(core, "wait_any_change", lambda *a, **k: False)
    cfg = core.Config(table_region=[0, 0, 1, 1], qty_region=[0, 0, 1, 1], auto_paste=True)
    eng = core.PriceEngine(cfg)

    def screens(*items):
        it = iter([core.ScreenRead(dict(p), q) for p, q in items])
        monkeypatch.setattr(core, "read_screen", lambda c, d=None: next(it))
    return eng, calls, screens


def test_sell_all_until_stock_empty(seq_engine):
    eng, calls, screens = seq_engine
    screens(({1: R(70, 95), 10: R(739, 95)}, 1),   # 1er : concurrent à 70 -> 69
            ({1: R(69, 95), 10: R(739, 95)}, 1),   # notre lot en tête -> on remet
            ({1: R(69, 95), 10: R(739, 95)}, 1),
            ({}, None))                            # objet épuisé
    res = eng.sell_all()
    assert res.level == "ok" and "3×1 à 69" in res.message and "stock épuisé" in res.message
    assert calls == [(69, True, True), "enter", "enter"]  # prix collé 1 fois, puis Entrée


def test_sell_all_stops_on_other_item(seq_engine):
    eng, calls, screens = seq_engine
    screens(({1: R(70, 95)}, 1), ({1: R(120, 95)}, 1))  # autre objet sélectionné
    res = eng.sell_all()
    assert "1×1 à 69" in res.message and "≠ 69" in res.message and calls == [(69, True, True)]


def test_sell_all_continues_with_smaller_lot(seq_engine):
    # 42 cuivres : 4×10 puis 2×1
    eng, calls, screens = seq_engine
    screens(({1: R(80, 95), 10: R(740, 95)}, 10),
            ({1: R(80, 95), 10: R(739, 95)}, 10), ({1: R(80, 95), 10: R(739, 95)}, 10),
            ({1: R(80, 95), 10: R(739, 95)}, 10),
            ({1: R(80, 95), 10: R(739, 95)}, 1),   # reste 2 : quantité passe à 1, même objet
            ({1: R(79, 95), 10: R(739, 95)}, 1),
            ({}, None))
    res = eng.sell_all()
    assert res.message.startswith("[TOUT] 4×10 à 739 + 2×1 à 79") and "stock épuisé" in res.message
    assert calls == [(739, True, True)] + ["enter"] * 3 + [(79, True, True), "enter"]


def test_sell_all_quantity_drop_on_other_item_stops(seq_engine):
    eng, calls, screens = seq_engine
    screens(({1: R(80, 95), 10: R(740, 95)}, 10),
            ({1: R(50, 95), 10: R(900, 95)}, 1))   # autre objet : notre 739 n'est pas en tête
    res = eng.sell_all()
    assert "≠ 739" in res.message and calls == [(739, True, True)]


def test_sell_all_never_goes_to_bigger_lot(seq_engine):
    eng, calls, screens = seq_engine
    screens(({1: R(80, 95), 10: R(740, 95)}, 1), ({1: R(79, 95), 10: R(740, 95)}, 10))
    res = eng.sell_all()
    assert "quantité passée à 10" in res.message and calls == [(79, True, True)]


def test_sell_all_smaller_lot_suspect_stops(seq_engine):
    eng, calls, screens = seq_engine
    screens(({10: R(740, 95)}, 10), ({10: R(739, 95)}, 1))  # lot 1 absent : prix estimé
    res = eng.sell_all()
    assert "lot 1 non vendu" in res.message
    assert calls == [(739, True, True), (72, False, False)]  # estimé : copié seulement


def test_sell_all_never_loops_on_suspect(seq_engine):
    eng, calls, screens = seq_engine
    screens(({1: R(70, 30)}, 1))                   # confiance faible
    assert eng.sell_all().level == "warn" and calls == [(69, False, False)]


def test_no_undercut_against_own_listing(seq_engine):
    eng, calls, screens = seq_engine
    screens(({1: R(70, 95)}, 1), ({1: R(69, 95)}, 1), ({1: R(69, 95)}, 10))
    eng.sell()                                      # 70 -> 69
    res = eng.sell()                                # en tête : 69 = notre prix -> 69
    assert calls[-1][0] == 69 and "(ton prix)" in res.message
    eng.sell()                                      # autre lot (10) : pas concerné
    assert len(calls) == 3


def test_parse_table_infers_unreadable_lot_from_row_order():
    data = _data([
        ("27", 170, 10, 20, 20, 95, 1, 1, 1),                                   # « 1 » illisible
        ("10", 15, 60, 16, 20, 96, 1, 1, 2), ("248", 170, 60, 25, 20, 96, 1, 1, 2),
        ("1000", 15, 110, 30, 20, 96, 1, 1, 3), ("570", 180, 110, 25, 20, 92, 1, 1, 3),
        ("28", 160, 110, 15, 20, 92, 1, 1, 3),
    ])
    out = core.parse_table(data, (0, 200), 200, 0.45, [1, 10, 100, 1000])
    assert {l: r.value for l, r in out.items()} == {1: 27, 10: 248, 1000: 28570}


def test_parse_table_does_not_guess_when_ambiguous():
    data = _data([
        ("10", 15, 10, 16, 20, 96, 1, 1, 1), ("248", 170, 10, 25, 20, 96, 1, 1, 1),
        ("2390", 170, 60, 25, 20, 90, 1, 1, 2),                                 # 100 ou 1000 ?
    ])
    out = core.parse_table(data, (0, 200), 200, 0.45, [1, 10, 100, 1000])
    assert out == {10: out[10]}


# --- Prix moyen / compteur de lots
def test_parse_counter():
    assert core.parse_counter("21/100 lots en vente") == (21, 100)
    assert core.parse_counter("12 / 98") == (12, 98)
    assert core.parse_counter("lots en vente") is None
    assert core.parse_counter("120/100") is None


def test_avg_guard_blocks_too_cheap(seq_engine, monkeypatch):
    eng, calls, screens = seq_engine
    eng.cfg.auto_validate = True
    eng.cfg.floor_mode = "stop"                            # ancien comportement : arrêt
    sr = core.ScreenRead({1: R(30, 95), 10: R(290, 95)}, 1)
    sr.avg = 100                                           # 29/u < 50 % de 100
    monkeypatch.setattr(core, "read_screen", lambda c, d=None: sr)
    res = eng.sell()
    assert res.level == "warn" and "prix moyen" in res.message and calls == [(29, False, False)]


def test_avg_guard_ok_when_close(seq_engine, monkeypatch):
    eng, calls, screens = seq_engine
    sr = core.ScreenRead({1: R(80, 95)}, 1)
    sr.avg = 100
    monkeypatch.setattr(core, "read_screen", lambda c, d=None: sr)
    res = eng.sell()
    assert res.level == "ok" and calls == [(79, True, False)]


@pytest.fixture
def counter(monkeypatch):
    seq = []
    monkeypatch.setattr(core, "read_counter", lambda c: seq.pop(0) if seq else None)
    return seq


def test_sell_all_counter_ok(seq_engine, counter):
    eng, calls, screens = seq_engine
    eng.cfg.count_region = [0, 0, 1, 1]
    counter += [(5, 100), (6, 100), (7, 100), (7, 100)]
    screens(({1: R(70, 95)}, 1), ({1: R(69, 95)}, 1), ({}, None))
    res = eng.sell_all()
    assert res.level == "ok" and "2×1 à 69" in res.message and "compteur 5→7" in res.message


def test_sell_all_counter_mismatch_stops(seq_engine, counter):
    eng, calls, screens = seq_engine
    eng.cfg.count_region = [0, 0, 1, 1]
    counter += [(5, 100), (5, 100), (5, 100)]          # la vente n'a pas été prise en compte
    screens(({1: R(70, 95)}, 1), ({1: R(69, 95)}, 1))
    res = eng.sell_all()
    assert res.level == "warn" and "non confirmée" in res.message and calls == [(69, True, True)]


def test_sell_all_counter_retry_when_slow(seq_engine, counter):
    eng, calls, screens = seq_engine
    eng.cfg.count_region = [0, 0, 1, 1]
    counter += [(5, 100), (5, 100), (6, 100), (6, 100)]   # jeu lent : 2e lecture OK
    screens(({1: R(70, 95)}, 1), ({}, None))
    res = eng.sell_all()
    assert res.level == "ok" and "stock épuisé" in res.message


def test_sell_all_stops_when_full(seq_engine, counter):
    eng, calls, screens = seq_engine
    eng.cfg.count_region = [0, 0, 1, 1]
    counter += [(99, 100), (100, 100)]
    screens(({1: R(70, 95)}, 1), ({1: R(69, 95)}, 1))
    res = eng.sell_all()
    assert "plus de place" in res.message and calls == [(69, True, True)]


def test_sell_all_refuses_when_already_full(seq_engine, counter):
    eng, calls, screens = seq_engine
    eng.cfg.count_region = [0, 0, 1, 1]
    counter += [(100, 100)]
    res = eng.sell_all()
    assert res.level == "error" and calls == []


# --- Mes ventes : mise à jour des prix (F3 / Ctrl+F3)
@pytest.fixture
def relist_engine(monkeypatch):
    calls = []
    state = {"mine": [], "screens": []}
    monkeypatch.setattr(core, "input_price", lambda v, c, paste=True, validate=False:
                        calls.append(("paste" if paste else "copy", v)) or "saisi")
    monkeypatch.setattr(core, "press_modify", lambda c: calls.append("modify"))
    monkeypatch.setattr(core, "press_enter", lambda: calls.append("enter"))
    monkeypatch.setattr(core, "log_history", lambda *a, **k: None)
    monkeypatch.setattr(core.time, "sleep", lambda s: None)
    monkeypatch.setattr(core, "read_mine",
                        lambda c, **k: core.Reading(state["mine"].pop(0), 95) if state["mine"] else core.Reading(None, -1))
    monkeypatch.setattr(core, "read_screen", lambda c, d=None, with_mine=False: state["screens"].pop(0))
    monkeypatch.setattr(core, "grab_screen", lambda r: np.zeros((2, 2, 3), np.uint8))
    monkeypatch.setattr(core, "wait_change", lambda *a, **k: None)
    cfg = core.Config(table_region=[0, 0, 1, 1], qty_region=[0, 0, 1, 1], mine_region=[0, 0, 1, 1],
                      verify_before_enter=False)  # vérification testée à part
    return core.PriceEngine(cfg), calls, state


def scr(prices, sel=1, avg=None):
    s = core.ScreenRead({l: R(p, 95) for l, p in prices.items()}, sel)
    s.avg = avg
    return s


def test_relist_undercuts_competitor(relist_engine):
    eng, calls, st = relist_engine
    st["screens"] = [scr({1: 760, 10: 6999})]
    st["mine"] = [774, None]                       # avant / après « Modifier » (panneau vidé)
    res = eng.relist()
    assert res.level == "ok" and "modifié" in res.message and calls == [("paste", 759), "modify"]


def test_relist_nothing_when_cheapest(relist_engine):
    eng, calls, st = relist_engine
    st["screens"] = [scr({1: 774})]
    st["mine"] = [774]
    res = eng.relist()
    assert "déjà le moins cher" in res.message and calls == []


def test_relist_aligns_on_own_other_listing(relist_engine):
    # 3 lignes du même objet : la 1re passe à 759, les suivantes s'alignent (pas 758, 757…)
    eng, calls, st = relist_engine
    st["screens"] = [scr({1: 760}), scr({1: 759})]
    st["mine"] = [774, None, 774, None]
    eng.relist()
    res = eng.relist()
    assert calls == [("paste", 759), "modify", ("paste", 759), "modify"] and "aligné" in res.message


def test_relist_unconfirmed(relist_engine):
    eng, calls, st = relist_engine
    st["screens"] = [scr({1: 760})]
    st["mine"] = [774, 774, 774]                   # « Modifier » sans effet, même après Entrée
    res = eng.relist()
    assert res.level == "warn" and "NON confirmée" in res.message


def test_relist_avg_guard_then_force(relist_engine):
    eng, calls, st = relist_engine
    eng.cfg.floor_mode = "stop"
    st["screens"] = [scr({1: 300}, avg=1189), scr({1: 300}, avg=1189)]
    st["mine"] = [774, 774, None]
    res = eng.relist()
    assert res.level == "warn" and "prix moyen" in res.message and calls == [("copy", 299)]
    res = eng.relist()                             # ré-appui = forcer
    assert "forcé" in res.message and calls[-2:] == [("paste", 299), "modify"]


def test_relist_all_disabled_by_default(relist_engine):
    eng, calls, st = relist_engine
    res = eng.relist_all()
    assert res.level == "warn" and "désactivé" in res.message


def test_relist_all_scrolls_until_list_stops(relist_engine, monkeypatch):
    eng, calls, st = relist_engine
    eng.cfg.relist_auto, eng.cfg.relist_row, eng.cfg.relist_step, eng.cfg.relist_rows = True, [100, 100], 50, 2
    clicks = []
    monkeypatch.setattr(core, "click_at", lambda p: clicks.append(p))
    monkeypatch.setattr(core, "mouse_position", lambda: (0, 0))
    moves = iter([(50, None), (0, None)])            # 1 ligne de plus, puis en bas
    monkeypatch.setattr(eng, "_scroll_page", lambda box, target: next(moves))
    n = [0]                                          # chaque capture différente : rien d'identique
    monkeypatch.setattr(core, "grab_screen", lambda r: n.__setitem__(0, n[0] + 1) or
                        np.random.default_rng(n[0]).integers(0, 255, (8, 8, 3)).astype(np.uint8))
    # page 1 : ligne à modifier (panneau vidé ensuite = accepté) -> la liste a bougé :
    # reprise en 1re ligne (déjà OK), 2e ligne OK ; page 2 : seule la nouvelle ligne est lue
    # page 2 : la dernière ligne vue est relue (marge de sécurité), puis la nouvelle
    st["screens"] = [scr({1: 760}), scr({1: 759}), scr({1: 87}), scr({1: 87}), scr({1: 76})]
    st["mine"] = [774, None, 759, 87, 87, 76]
    res = eng.relist_all()
    assert res.level == "ok" and "5 lignes" in res.message and "1 modifiées" in res.message
    assert clicks == [(100, 100), (100, 100), (100, 150), (100, 100), (100, 150)]


def test_visible_rows_after_pixel_scroll():
    eng = core.PriceEngine(core.Config(relist_row=[0, 100], relist_step=50, relist_rows=4))
    assert eng._visible_rows(0) == [(100, 0), (150, 1), (200, 2), (250, 3)]
    assert eng._visible_rows(10) == [(90, 0), (140, 1), (190, 2), (240, 3)]  # petit décalage
    assert eng._visible_rows(40)[0] == (110, 1)           # 1re ligne trop coupée : ignorée
    assert eng._visible_rows(150)[0] == (100, 3)


def _list_image(n_rows=20, step=50, seed=0, identical=False):
    rng = np.random.default_rng(seed)
    rows = []
    for i in range(n_rows):
        v = 0 if identical else i
        r = np.full((step, 120), 40, np.uint8)
        r[0:2] = 90                                       # séparation de ligne
        r[15:35, 10:10 + 5 * ((v % 9) + 1)] = 200         # « texte » variable
        r[15:35, 80:90] = 120 + (v * 13) % 100
        rows.append(r)
    return np.vstack(rows) + rng.integers(0, 3, (n_rows * step, 120)).astype(np.uint8)


@pytest.mark.parametrize("d", [0, 7, 23, 50, 73, 140])
def test_measure_shift(d):
    full = _list_image()
    a, b = full[0:400], full[d:d + 400]
    assert core.measure_shift(a, b, 50) == d


def test_measure_shift_identical_rows_uses_expected():
    full = _list_image(identical=True)
    a, b = full[0:400], full[30:430]
    assert core.measure_shift(a, b, 50, expected=30) == 30
    assert core.measure_shift(a, b, 50) == 30            # plus petit candidat


def test_scroll_page_measures_until_target(relist_engine, monkeypatch):
    eng, calls, st = relist_engine
    eng.cfg.relist_row, eng.cfg.relist_step, eng.cfg.relist_rows = [60, 25], 50, 8
    full = _list_image(40)
    pos = [0]
    steps = []
    monkeypatch.setattr(core, "scroll_at", lambda p, n: steps.append(n) or
                        pos.__setitem__(0, min(pos[0] + 30 * n, 1600)))
    monkeypatch.setattr(core, "grab_screen", lambda r: full[pos[0]:pos[0] + 400])
    moved, err = eng._scroll_page((0, 0, 120, 400), 350)
    assert err is None and moved == pos[0] and moved >= 350
    assert steps[0] == 1 and max(steps) > 1 and len(steps) <= 4   # crans groupés après la mesure


def test_scroll_page_bottom(relist_engine, monkeypatch):
    eng, calls, st = relist_engine
    eng.cfg.relist_row, eng.cfg.relist_step = [60, 25], 50
    img = _list_image()[0:400]
    monkeypatch.setattr(core, "scroll_at", lambda p, n: None)
    monkeypatch.setattr(core, "grab_screen", lambda r: img)
    assert eng._scroll_page((0, 0, 120, 400), 350) == (0, None)


def test_relist_panel_cleared_means_done(relist_engine):
    # le jeu désélectionne la vente après « Modifier » : plus rien à lire = accepté
    eng, calls, st = relist_engine
    st["screens"] = [scr({1: 60})]
    st["mine"] = [61, None]
    res = eng.relist()
    assert res.level == "ok" and "modifié" in res.message and calls == [("paste", 59), "modify"]


def test_relist_all_skips_suspect_row_and_continues(relist_engine, monkeypatch):
    eng, calls, st = relist_engine
    eng.cfg.relist_auto, eng.cfg.relist_row, eng.cfg.relist_step, eng.cfg.relist_rows = True, [100, 100], 50, 2
    monkeypatch.setattr(core, "click_at", lambda p: None)
    monkeypatch.setattr(core, "mouse_position", lambda: (0, 0))
    monkeypatch.setattr(eng, "_scroll_page", lambda box, target: (0, None))
    n = [0]
    monkeypatch.setattr(core, "grab_screen", lambda r: n.__setitem__(0, n[0] + 1) or
                        np.random.default_rng(n[0]).integers(0, 255, (8, 8, 3)).astype(np.uint8))
    # ligne 1 incohérente (lue 2 fois) : laissée telle quelle ; ligne 2 normale
    st["screens"] = [scr({1: 100, 10: 9000}), scr({1: 100, 10: 9000}), scr({1: 87})]
    st["mine"] = [774, 774, 87]
    res = eng.relist_all()
    assert res.level == "warn" and "1 ligne(s) douteuse(s)" in res.message and "fin de la liste" in res.message
    assert ("paste", 99) not in calls


def test_relist_all_stops_after_3_doubtful(relist_engine, monkeypatch):
    eng, calls, st = relist_engine
    eng.cfg.relist_auto, eng.cfg.relist_row, eng.cfg.relist_step, eng.cfg.relist_rows = True, [100, 100], 50, 5
    monkeypatch.setattr(core, "click_at", lambda p: None)
    monkeypatch.setattr(core, "mouse_position", lambda: (0, 0))
    n = [0]
    monkeypatch.setattr(core, "grab_screen", lambda r: n.__setitem__(0, n[0] + 1) or
                        np.random.default_rng(n[0]).integers(0, 255, (8, 8, 3)).astype(np.uint8))
    st["screens"] = [scr({1: 50}) for _ in range(6)]
    st["mine"] = [None] * 6                               # ton prix illisible partout
    res = eng.relist_all()
    assert "3 lignes douteuses" in res.message and calls == []


def test_relist_all_skips_identical_rows(relist_engine, monkeypatch):
    # 3 lignes identiques (même objet, même prix) déjà au bon prix : 1 seule lue
    eng, calls, st = relist_engine
    eng.cfg.relist_auto, eng.cfg.relist_row, eng.cfg.relist_step, eng.cfg.relist_rows = True, [100, 100], 50, 3
    clicks = []
    monkeypatch.setattr(core, "click_at", lambda p: clicks.append(p))
    monkeypatch.setattr(core, "mouse_position", lambda: (0, 0))
    monkeypatch.setattr(eng, "_scroll_page", lambda box, target: (0, None))
    st["screens"] = [scr({1: 34})]
    st["mine"] = [34]
    res = eng.relist_all()
    assert clicks == [(100, 100)] and "2 identiques sautées" in res.message and res.level == "ok"


def test_zone_hint():
    assert core.zone_hint("count", (0, 0, 49, 11))       # zone du compteur trop petite
    assert core.zone_hint("avg", (0, 0, 17, 15))
    assert core.zone_hint("count", (0, 0, 140, 22)) is None
    assert core.zone_hint("mine", (0, 0, 667, 513)) is None  # grande zone : le champ est retrouvé


def test_find_field_in_large_zone():
    img = np.full((300, 600, 3), 40, np.uint8)
    img[100:125, 50:180] = 27                            # champ non sélectionné
    img[105:118, 60:75] = 220                            # « 76 »
    f = core._find_field(img)
    assert f is not None and f.shape[:2] == (25, 130)
    img[100:125, 50:180] = 40                            # vente désélectionnée : plus de champ
    assert core._find_field(img) is None


# --- Prix plancher (FLOOR_MODE / FLOOR_RATIO)
def test_floor_price():
    assert core.floor_price(1, 1189, 0.7) == 833          # 832,3 -> arrondi au-dessus
    assert core.floor_price(10, 81, 0.7) == 567
    assert core.floor_price(10, 3, 0.8) == 24             # 24,000000000000004 en flottant : pas 25
    assert core.floor_price(1, None, 0.7) is None and core.floor_price(1, 100, 0) is None


def test_sell_goes_to_floor_not_dumper(seq_engine, monkeypatch):
    eng, calls, screens = seq_engine
    eng.cfg.auto_validate = True
    sr = core.ScreenRead({1: R(300, 95), 10: R(8000, 95)}, 1)
    sr.avg = 1189                                        # quelqu'un brade à 300 (prix moyen 1 189)
    monkeypatch.setattr(core, "read_screen", lambda c, d=None: sr)
    res = eng.sell()
    assert res.level == "ok" and "plancher" in res.message and calls == [(833, True, True)]


def test_sell_all_continues_at_floor(seq_engine, monkeypatch):
    eng, calls, screens = seq_engine
    a = core.ScreenRead({1: R(300, 95)}, 1)
    a.avg = 1189
    b = core.ScreenRead({1: R(300, 95)}, 1)               # en tête : toujours le brader
    b.avg = 1189
    it = iter([a, b, core.ScreenRead({}, None)])
    monkeypatch.setattr(core, "read_screen", lambda c, d=None: next(it))
    res = eng.sell_all()
    assert "2×1 à 833" in res.message and "stock épuisé" in res.message
    assert calls == [(833, True, True), "enter"]


def test_relist_floor(relist_engine):
    eng, calls, st = relist_engine
    st["screens"] = [scr({1: 300}, avg=1189)]
    st["mine"] = [1200, None]
    res = eng.relist()
    assert res.level == "ok" and "plancher" in res.message and calls == [("paste", 833), "modify"]


def test_relist_already_at_floor(relist_engine):
    eng, calls, st = relist_engine
    st["screens"] = [scr({1: 300}, avg=1189)]
    st["mine"] = [833]
    res = eng.relist()
    assert "déjà au plancher" in res.message and calls == []


def test_relist_keep_mode(relist_engine):
    eng, calls, st = relist_engine
    eng.cfg.floor_mode = "keep"
    st["screens"] = [scr({1: 300}, avg=1189)]
    st["mine"] = [1200]
    res = eng.relist()
    assert "ton prix gardé" in res.message and calls == []


def test_relist_above_floor_normal_undercut(relist_engine):
    eng, calls, st = relist_engine
    st["screens"] = [scr({1: 1000}, avg=1189)]            # 999 >= plancher 833 : undercut normal
    st["mine"] = [1100, None]
    eng.relist()
    assert calls == [("paste", 999), "modify"]


def test_same_row_sees_one_digit_change():
    row = np.full((40, 400, 3), 45, np.uint8)
    row[12:28, 350:358] = 230                             # « 7 »
    row[12:28, 360:368] = 230                             # « 6 »
    other = row.copy()
    other[12:28, 362:366] = 45                            # un seul chiffre change (76 -> 75)
    assert core._same_row(row, row.copy())
    assert not core._same_row(row, other)


def test_relist_confirmation_popup_enter(relist_engine):
    # après « Modifier » le panneau reste affiché (fenêtre de confirmation) : Entrée, puis vidé
    eng, calls, st = relist_engine
    st["screens"] = [scr({1: 760})]
    st["mine"] = [774, 759, None]
    res = eng.relist()
    assert res.level == "ok" and "confirmation validée" in res.message
    assert calls == [("paste", 759), "modify", "enter"]


def test_relist_all_continues_at_modified_position(relist_engine, monkeypatch):
    # modification sur la 2e ligne : on reprend à la 2e ligne (relue), pas en haut de page
    eng, calls, st = relist_engine
    eng.cfg.relist_auto, eng.cfg.relist_row, eng.cfg.relist_step, eng.cfg.relist_rows = True, [100, 100], 50, 3
    clicks = []
    monkeypatch.setattr(core, "click_at", lambda p: clicks.append(p))
    monkeypatch.setattr(core, "mouse_position", lambda: (0, 0))
    monkeypatch.setattr(eng, "_scroll_page", lambda box, target: (0, None))
    n = [0]
    monkeypatch.setattr(core, "grab_screen", lambda r: n.__setitem__(0, n[0] + 1) or
                        np.random.default_rng(n[0]).integers(0, 255, (8, 8, 3)).astype(np.uint8))
    st["screens"] = [scr({1: 87}), scr({1: 760}), scr({1: 50}), scr({1: 26})]
    st["mine"] = [87, 774, None, 50, 26]
    res = eng.relist_all()
    assert "1 modifiées" in res.message
    assert clicks == [(100, 100), (100, 150), (100, 150), (100, 200)]


def test_config_v4_gets_new_relist_max(tmp_path):
    p = tmp_path / "cfg.json"
    p.write_text(json.dumps({"CONFIG_VERSION": 4, "RELIST_MAX": 120}))
    assert core.Config.load(p).relist_max == 400


# --- Repère HDV : les zones suivent la fenêtre
def _fake_screen(win, x, y, bg):
    sc = bg.copy()
    h, w = win.shape[:2]
    sc[y:y + h, x:x + w] = win
    return sc


def test_reanchor_follows_moved_hdv(monkeypatch, tmp_path):
    rng = np.random.default_rng(1)
    bg = rng.integers(20, 60, (700, 1000, 3)).astype(np.uint8)
    win = rng.integers(0, 255, (200, 300, 3)).astype(np.uint8)  # « fenêtre HDV » texturée
    cur = {"img": _fake_screen(win, 100, 50, bg)}
    monkeypatch.setattr(core, "grab_screen", lambda r: cur["img"][r[1]:r[1] + r[3], r[0]:r[0] + r[2]])
    monkeypatch.setattr(core, "screen_bounds", lambda: (0, 0, 1000, 700))
    monkeypatch.setattr(core, "ANCHOR_PATH", tmp_path / "anchor.png")
    monkeypatch.setattr(core.Config, "save", lambda self, path=None: None)
    cfg = core.Config(anchor_region=[110, 55, 120, 20], table_region=[130, 150, 100, 60],
                      price_field=[150, 100], relist_row=[300, 120])
    core.save_anchor(cur["img"][55:75, 110:230])
    eng = core.PriceEngine(cfg)
    assert eng._reanchor() is None                       # pas bougé
    cur["img"] = _fake_screen(win, 420, 310, bg)          # HDV déplacé de (+320, +260)
    assert eng._reanchor() == (320, 260)
    assert cfg.table_region == [450, 410, 100, 60] and cfg.price_field == [470, 360]
    assert cfg.relist_row == [620, 380] and cfg.anchor_region == [430, 315, 120, 20]
    assert "recalées" in eng.last_anchor_msg


def test_reanchor_hdv_closed_keeps_zones(monkeypatch, tmp_path):
    rng = np.random.default_rng(2)
    bg = rng.integers(20, 60, (400, 600, 3)).astype(np.uint8)
    win = rng.integers(0, 255, (100, 200, 3)).astype(np.uint8)
    cur = {"img": _fake_screen(win, 50, 50, bg)}
    monkeypatch.setattr(core, "grab_screen", lambda r: cur["img"][r[1]:r[1] + r[3], r[0]:r[0] + r[2]])
    monkeypatch.setattr(core, "screen_bounds", lambda: (0, 0, 600, 400))
    monkeypatch.setattr(core, "ANCHOR_PATH", tmp_path / "anchor.png")
    cfg = core.Config(anchor_region=[60, 60, 100, 20], table_region=[70, 90, 50, 40])
    core.save_anchor(cur["img"][60:80, 60:160])
    cur["img"] = bg                                       # HDV fermé
    eng = core.PriceEngine(cfg)
    assert eng._reanchor() is None and cfg.table_region == [70, 90, 50, 40]
    assert "introuvable" in eng.last_anchor_msg


# --- Tableau de bord
def test_dashboard_builds(tmp_path):
    import dofus_dashboard as dash
    h = tmp_path / "dofus_price_history.csv"
    h.write_text(",".join(core.HISTORY_HEADER) + "\n"
                 "1794603901,2026-11-13 22:05:01,sell,1,1,600,95,599,saisi + mis en vente,fixed,1.0,none\n"
                 "1794603917,2026-11-13 22:05:17,sell,10,10,6000,95,5999,sell_all,fixed,1.0,none\n"
                 "1794651321,2026-11-14 11:15:21,relist,1,1,757,83,756,modified,fixed,1.0,none\n"
                 "1794651322,2026-11-14 11:15:22,read,1,1,757,40,756,suspect,fixed,1.0,none\n",
                 encoding="utf-8")
    data = dash.compute(dash.load_rows(h))
    assert data["count"]["vente"] == 2 and data["count"]["modif"] == 1 and data["count"]["suspect"] == 1
    assert data["kamas"] == 599 + 5999 and data["lots"] == {1: 1, 10: 1}
    assert dash.fmt(data["kamas"]) == "6 598" and list(data["days"]) == ["2026-11-13", "2026-11-14"]


# --- Nom des objets
def test_clean_name():
    from dofus_items import clean_name
    assert clean_name("Nageoire de\nCompétition\nNIV. 18") == "Nageoire de Compétition"
    assert clean_name("Laine Céleste\nNIv, 3") == "Laine Céleste"
    assert clean_name("Cuivre\n") == "Cuivre"
    assert clean_name("|\n,,") == ""


def test_name_snap_and_group():
    from dofus_items import NameBook, group_names
    book = NameBook(["Nageoire de Compétition"] * 5 + ["Cuivre"])
    assert book.snap("Nagcoire de Compétition") == "Nageoire de Compétition"
    assert book.snap("Bec du Tofu") is None
    g = group_names(["Poils du Milimulou"] * 4 + ["Poiis du Milimulou", "Cuivre"])
    assert g["Poiis du Milimulou"] == "Poils du Milimulou" and g["Cuivre"] == "Cuivre"


def test_history_migrates_old_header_and_writes_item(tmp_path, monkeypatch):
    h = tmp_path / "h.csv"
    old = core.HISTORY_HEADER[:-1]
    h.write_text(",".join(old) + "\n1,2026-11-13 22:05:01,sell,1,1,600,95,599,saisi,fixed,1.0,none\n",
                 encoding="utf-8")

    class FakeReader:
        def read(self, img):
            return "Cuivre"
    monkeypatch.setattr(core, "name_reader", lambda: FakeReader())
    cfg = core.Config()
    core.log_history("relist", 1, 1, core.Reading(77, 95), 76, "modified", cfg, path=h,
                     item_img=np.zeros((4, 4, 3), np.uint8))
    core.flush_history(3)
    rows = list(csv.DictReader(h.open(encoding="utf-8")))
    assert list(rows[0]) == core.HISTORY_HEADER and len(rows) == 2
    assert rows[0]["item"] == "" and rows[1]["item"] == "Cuivre" and rows[1]["new_price"] == "76"
    assert not list(tmp_path.glob("*_old_*"))          # rien d'archivé, colonne ajoutée


def test_relist_logs_observation_when_cheapest(relist_engine, monkeypatch):
    eng, calls, st = relist_engine
    logged = []
    monkeypatch.setattr(core, "log_history", lambda *a, **k: logged.append(a[0]))
    st["screens"] = [scr({1: 774})]
    st["mine"] = [774]
    eng.relist()
    assert logged == ["observe"]


def test_dashboard_items(tmp_path):
    import dofus_dashboard as dash
    h = tmp_path / "dofus_price_history.csv"
    lines = [",".join(core.HISTORY_HEADER)]
    for i, (act, read, new, st, item) in enumerate([
            ("sell", 80, 79, "saisi + mis en vente", "Cuivre"),
            ("observe", 79, 79, "cheapest", "Cuivre"),
            ("relist", 75, 74, "modified", "Cuivrc"),            # variante de lecture
            ("relist", 400, 399, "modified", "Nageoire de Compétition")]):
        lines.append(f"{1794603900 + i * 60},2026-11-13 22:0{i}:00,{act},1,1,{read},95,{new},{st},fixed,1.0,none,{item}")
    h.write_text("\n".join(lines) + "\n", encoding="utf-8")
    items = dash.compute(dash.load_rows(h))["items"]
    assert list(items) == ["Cuivre", "Nageoire de Compétition"]
    c = items["Cuivre"]
    assert c["ventes"] == 1 and c["modifs"] == 1 and [p[1] for p in c["points"]] == [80, 79, 75]
    assert c["last_low"] == 75 and c["points"][1][2] == 79



# --- Vérification du prix avant validation
def test_input_price_blocks_wrong_paste(monkeypatch):
    sent = []
    import types
    kb = types.SimpleNamespace(press_and_release=lambda k: sent.append(k))
    monkeypatch.setitem(sys.modules, "keyboard", kb)
    monkeypatch.setitem(sys.modules, "pyautogui", types.SimpleNamespace(click=lambda *a: None,
                                                                         moveTo=lambda *a: None))
    monkeypatch.setitem(sys.modules, "pyperclip", types.SimpleNamespace(copy=lambda t: None,
                                                                         paste=lambda: "", ))
    monkeypatch.setattr(core, "_set_clipboard", lambda pc, t, tries=3: True)
    monkeypatch.setattr(core, "_take_clipboard", lambda pc, cfg: None)
    monkeypatch.setattr(core, "_schedule_restore", lambda pc, d=1.0: None)
    monkeypatch.setattr(core.time, "sleep", lambda s: None)
    monkeypatch.setattr(core, "read_mine", lambda c, **k: core.Reading(4, 95))  # le champ montre « 4 »
    monkeypatch.setattr(core, "save_field_debug", lambda c, tag: None)
    cfg = core.Config(price_field=[10, 10])
    done = core.input_price(69, cfg, paste=True, validate=True)
    assert "PAS validé" in done and "enter" not in sent
    reads2 = iter([core.Reading(69, 95)])
    monkeypatch.setattr(core, "read_mine", lambda c, **k: next(reads2))
    sent.clear()
    assert core.input_price(69, cfg, paste=True, validate=True) == "saisi + mis en vente" and "enter" in sent


def test_press_validate_checks_field(monkeypatch):
    import types
    sent = []
    monkeypatch.setitem(sys.modules, "keyboard", types.SimpleNamespace(press_and_release=lambda k: sent.append(k)))
    monkeypatch.setattr(core.time, "sleep", lambda s: None)
    monkeypatch.setattr(core, "read_mine", lambda c, **k: core.Reading(70, 95))
    monkeypatch.setattr(core, "save_field_debug", lambda c, tag: None)
    cfg = core.Config(price_field=[10, 10])
    assert core.press_validate(cfg, expected=69) is False and sent == []
    assert core.press_validate(cfg, expected=70) is True and sent == ["enter"]


def test_relist_not_modified_if_field_wrong(relist_engine):
    eng, calls, st = relist_engine
    eng.cfg.verify_before_enter = True
    st["screens"] = [scr({1: 760})]
    st["mine"] = [774, 774, 774]                  # après collage, le champ affiche encore 774
    res = eng.relist()
    assert res.level == "warn" and "PAS modifié" in res.message and "modify" not in calls


def test_smart_f1_routes_by_panel(monkeypatch):
    eng = core.PriceEngine(core.Config(modify_button=[1, 1]))
    monkeypatch.setattr(eng, "relist", lambda: "relist")
    monkeypatch.setattr(eng, "sell", lambda optimize=False: "sell")
    monkeypatch.setattr(core, "detect_panel", lambda c: "relist")
    assert eng.smart() == "relist"
    monkeypatch.setattr(core, "detect_panel", lambda c: "sell")
    assert eng.smart() == "sell"
    eng.cfg.smart_f1 = False
    monkeypatch.setattr(core, "detect_panel", lambda c: "relist")
    assert eng.smart() == "sell"


# --- Relecture du champ : curseur collé au dernier chiffre (448 relu 446, vente refusée à tort)
def test_drop_caret_keeps_glued_digit():
    th = np.full((40, 40), 255, np.uint8)
    th[12:28, 10:20] = 0            # chiffre (pavé) : colonnes 10 à 19
    th[13:27, 12:18] = 255          # … creux, comme un 0 / 8
    th[6:34, 20:22] = 0             # curseur collé : déborde au-dessus et en dessous
    out = core._drop_caret(th)
    assert (out[:, 20:22] == 255).all()                     # curseur effacé
    assert (out[12:28, 19] == 0).all()                      # bord droit du chiffre intact
    assert (out[12:28, 10:20] == th[12:28, 10:20]).all()


def test_field_check_second_opinion(monkeypatch):
    monkeypatch.setattr(core.time, "sleep", lambda s: None)
    saved = []
    monkeypatch.setattr(core, "save_field_debug", lambda c, tag: saved.append(tag))
    cfg = core.Config(price_field=[10, 10])
    # lecture rapide fausse (446), Tesseract sûr de 448 : validé
    monkeypatch.setattr(core, "read_mine", lambda c, tesseract_only=False:
                        core.Reading(448, 92) if tesseract_only else core.Reading(446, 95))
    assert core.field_check(cfg, 448) == (True, 448) and saved == []
    # Tesseract peu sûr : refus + image du champ gardée
    monkeypatch.setattr(core, "read_mine", lambda c, tesseract_only=False:
                        core.Reading(448, 40) if tesseract_only else core.Reading(446, 95))
    assert core.field_check(cfg, 448) == (False, 446) and saved == ["attendu448_lu446"]


def test_field_check_rereads_until_caret_gone(monkeypatch):
    monkeypatch.setattr(core.time, "sleep", lambda s: None)
    reads = iter([446, 446, 448])                           # curseur visible, puis éteint
    monkeypatch.setattr(core, "read_mine", lambda c, **k: core.Reading(next(reads), 95))
    assert core.field_check(core.Config(price_field=[10, 10]), 448) == (True, 448)
