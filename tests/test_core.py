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
    state["opinions"] = []                         # 2e et 3e lectures de « ton prix » (vide = d'accord)
    monkeypatch.setattr(core, "mine_second_opinions", lambda c: state["opinions"].pop(0) if state["opinions"] else [])
    state["dialog"] = []                           # fenêtre « Confirmer la mise en vente » vue ?
    monkeypatch.setattr(core, "find_confirm_dialog",
                        lambda c, *a, **k: state["dialog"].pop(0) if state["dialog"] else None)
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


def test_relist_unconfirmed(relist_engine, monkeypatch):
    eng, calls, st = relist_engine
    monkeypatch.setattr(core, "RELIST_CONFIRM_WAIT", 0.05)
    st["screens"] = [scr({1: 760})]
    st["mine"] = [774] * 100000                    # « Modifier » sans effet, même après Entrée
    res = eng.relist()
    assert res.level == "warn" and "NON confirmée" in res.message and "enter" in calls


def test_relist_waits_while_old_price_still_shown(relist_engine):
    # Bout de Blop Coco : après « Modifier », le jeu réaffiche un instant l'ancien prix (798)
    # puis vide le panneau : c'est une réussite, pas un arrêt de Ctrl+F3.
    eng, calls, st = relist_engine
    st["screens"] = [scr({1: 760})]
    st["mine"] = [798, 798, 798, None]
    res = eng.relist()
    assert res.level == "ok" and "modifié" in res.message
    assert calls == [("paste", 759), "modify"]     # pas d'Entrée inutile


def test_relist_validates_confirmation_window_with_enter(relist_engine):
    # Prix loin du prix moyen (pas à jour) : le jeu demande confirmation -> Entrée, et on continue.
    eng, calls, st = relist_engine
    st["screens"] = [scr({1: 165})]
    st["mine"] = [622, 164, 164, None]              # pendant la fenêtre : le champ montre le NOUVEAU prix
    st["dialog"] = [None, (500, 300), None]         # la fenêtre arrive un peu après
    res = eng.relist()
    assert res.level == "ok" and "confirmation validée" in res.message
    assert calls == [("paste", 164), "modify", "enter"]


def test_relist_stops_when_confirmation_window_stays_open(relist_engine, monkeypatch):
    eng, calls, st = relist_engine
    monkeypatch.setattr(core, "CONFIRM_CLOSE_WAIT", 0.01)
    monkeypatch.setattr(core, "find_confirm_dialog", lambda c, *a, **k: (500, 300))
    st["screens"] = [scr({1: 165})]
    st["mine"] = [622, 622, 622]
    res = eng.relist()
    assert res.level == "warn" and res.hint == "Confirmation bloquée"
    assert calls == [("paste", 164), "modify", "enter", "enter"]


FIX = Path(__file__).resolve().parent / "fixtures"


def test_find_confirm_dialog_on_screen():
    import cv2
    ref = cv2.imread(str(FIX / "hdv_echelles" / "2560x1440_90.png"))
    dlg = cv2.imread(str(FIX / "confirmation_prix.png"))
    for f in (1.0, 0.8, 1.15):
        core._confirm_cache.pop("scale", None)
        screen = np.full((1440, 2560, 3), 30, np.uint8)
        screen[:ref.shape[0], :ref.shape[1]] = ref
        cfg = core.Config(relist_step=round(core.MODEL_ROW_STEP * f))
        assert core.find_confirm_dialog(cfg, screen) is None          # HDV seul : pas de fenêtre
        d = cv2.resize(dlg, None, fx=f, fy=f, interpolation=cv2.INTER_AREA)
        screen[500:500 + d.shape[0], 900:900 + d.shape[1]] = d
        x, y = core.find_confirm_dialog(cfg, screen)
        assert abs(x - (900 + 60 * f)) <= 3 and abs(y - (500 + 6 * f)) <= 3


def test_vote_mine():
    R = core.Reading
    assert core.vote_mine(R(489, 95), [R(459, 92), R(459, 90)], 60) == (459, "489 / 459 / 459")
    assert core.vote_mine(R(489, 95), [R(489, 92), R(459, 90)], 60)[0] == 489
    assert core.vote_mine(R(489, 95), [R(459, 92), R(None, -1)], 60)[0] is None
    assert core.vote_mine(R(489, 95), [], 60)[0] == 489


def test_relist_rereads_own_price_before_modifying(relist_engine, monkeypatch):
    # Crocs de Rats : ta vente est à 459, lue 489 -> la majorité dit 459 : rien à faire
    eng, calls, st = relist_engine
    monkeypatch.setattr(core, "mine_field_image", lambda c, *a: None)
    st["screens"] = [scr({1: 459})]
    st["mine"] = [489]
    st["opinions"] = [[core.Reading(459, 92), core.Reading(459, 90)]]
    res = eng.relist()
    assert "déjà le moins cher" in res.message and calls == []
    st["screens"] = [scr({1: 459})]                # pas de majorité : ligne passée, rien collé
    st["mine"] = [489]
    st["opinions"] = [[core.Reading(459, 92), core.Reading(None, -1)]]
    res = eng.relist()
    assert res.hint == "Ton prix douteux" and calls == []


def test_relist_force_suspect_option(relist_engine, monkeypatch):
    # Marché qui chute : 774 -> 100 = « baisse énorme ». Option active + 2e lecture identique : modifié.
    eng, calls, st = relist_engine
    eng.cfg.relist_force_suspect = True
    monkeypatch.setattr(core, "table_second_read", lambda c: scr({1: 100}))
    st["screens"] = [scr({1: 100})]
    st["mine"] = [774, None]
    res = eng.relist()
    assert res.level == "ok" and "suspect accepté" in res.message and "baisse énorme" in res.message
    assert calls == [("paste", 99), "modify"]


def test_relist_force_suspect_needs_same_second_read(relist_engine, monkeypatch):
    eng, calls, st = relist_engine
    eng.cfg.relist_force_suspect = True
    monkeypatch.setattr(core, "table_second_read", lambda c: scr({1: 3000}))   # lu autrement : doute
    st["screens"] = [scr({1: 100})]
    st["mine"] = [774]
    res = eng.relist()
    assert res.hint == "Suspect" and "2e lecture différente (3000)" in res.message
    assert ("paste", 99) not in calls


def test_relist_force_suspect_never_skips_unreliable_reading(relist_engine, monkeypatch):
    eng, calls, st = relist_engine
    eng.cfg.relist_force_suspect = True
    seen = []
    monkeypatch.setattr(core, "table_second_read", lambda c: seen.append(1) or scr({1: 100}))
    s1 = scr({1: 100})
    s1.prices[1] = R(100, 20)                     # confiance OCR trop basse
    st["screens"] = [s1]
    st["mine"] = [774]
    res = eng.relist()
    assert res.hint == "Suspect" and "confiance OCR" in res.message and not seen


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


def _relist_loop_setup(eng, st, monkeypatch):
    """Même liste que test_relist_all_scrolls_until_list_stops (5 lignes, 1 modifiée)."""
    eng.cfg.relist_auto, eng.cfg.relist_row, eng.cfg.relist_step, eng.cfg.relist_rows = True, [100, 100], 50, 2
    monkeypatch.setattr(core, "click_at", lambda p: None)
    monkeypatch.setattr(core, "mouse_position", lambda: (0, 0))
    moves = iter([(50, None), (0, None)])
    monkeypatch.setattr(eng, "_scroll_page", lambda box, target: next(moves))
    n = [0]
    monkeypatch.setattr(core, "grab_screen", lambda r: n.__setitem__(0, n[0] + 1) or
                        np.random.default_rng(n[0]).integers(0, 255, (8, 8, 3)).astype(np.uint8))
    st["screens"] = [scr({1: 760}), scr({1: 759}), scr({1: 87}), scr({1: 87}), scr({1: 76})]
    st["mine"] = [774, None, 759, 87, 87, 76]


def test_relist_all_reports_progress_with_total(relist_engine, monkeypatch):
    eng, calls, st = relist_engine
    _relist_loop_setup(eng, st, monkeypatch)
    eng.cfg.count_region = [0, 0, 10, 10]
    monkeypatch.setattr(core, "read_counter", lambda cfg: (3, 100))   # « 3/100 lots en vente »
    seen = []
    eng.on_loop_progress = seen.append
    eng.relist_all()
    assert seen[0]["row"] == 1 and seen[0]["total"] == 3 and seen[0]["changed"] == 0
    assert any(d["changed"] == 1 for d in seen)              # la ligne modifiée est comptée
    assert seen[-1]["finished"] and seen[-1]["done"] == 5


def test_relist_all_stop_button(relist_engine, monkeypatch):
    eng, calls, st = relist_engine
    _relist_loop_setup(eng, st, monkeypatch)
    eng.on_loop_progress = lambda d: setattr(eng, "stop_requested", d["done"] >= 2)
    res = eng.relist_all()
    assert "arrêt demandé" in res.message and not eng.paused     # « Arrêter » ne met pas en pause
    eng.stop_requested = True
    eng.on_loop_progress = None
    _relist_loop_setup(eng, st, monkeypatch)
    assert "arrêt demandé" not in eng.relist_all().message       # remis à zéro au départ suivant


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


def test_scroll_page_retries_when_the_game_ignores_the_wheel(relist_engine, monkeypatch):
    # 13:57 : la molette ignorée une fois (liste redessinée) -> avant, « fin de la liste »
    eng, calls, st = relist_engine
    eng.cfg.relist_row, eng.cfg.relist_step, eng.cfg.relist_rows = [60, 25], 50, 8
    full = _list_image(40)
    pos, ignored = [0], [2]
    def wheel(p, n):
        if ignored[0]:
            ignored[0] -= 1
            return
        pos[0] = min(pos[0] + 30 * n, 1600)
    monkeypatch.setattr(core, "scroll_at", wheel)
    monkeypatch.setattr(core, "grab_screen", lambda r: full[pos[0]:pos[0] + 400])
    moved, err = eng._scroll_page((0, 0, 120, 400), 350)
    assert err is None and moved >= 350


def _rows_test_engine(relist_engine, monkeypatch, scrolls, counter):
    eng, calls, st = relist_engine
    eng.cfg.relist_auto, eng.cfg.relist_row, eng.cfg.relist_step, eng.cfg.relist_rows = True, [100, 100], 50, 2
    eng.cfg.count_region = [0, 0, 10, 10]
    monkeypatch.setattr(core, "click_at", lambda p: None)
    monkeypatch.setattr(core, "mouse_position", lambda: (0, 0))
    monkeypatch.setattr(core, "read_counter", lambda c: counter)
    moves = iter(scrolls)
    monkeypatch.setattr(eng, "_scroll_page", lambda box, target: next(moves))
    n = [0]
    monkeypatch.setattr(core, "grab_screen", lambda r: n.__setitem__(0, n[0] + 1) or
                        np.random.default_rng(n[0]).integers(0, 255, (8, 8, 3)).astype(np.uint8))
    return eng, st


def test_relist_all_says_scroll_blocked_when_counter_shows_more(relist_engine, monkeypatch):
    eng, st = _rows_test_engine(relist_engine, monkeypatch, [(0, None), (0, None)], (40, 100))
    st["screens"] = [scr({1: 87}), scr({1: 50})]
    st["mine"] = [87, 50]
    res = eng.relist_all()
    assert "défilement bloqué" in res.message and "fin de la liste" not in res.message


def test_relist_all_retries_scroll_then_continues(relist_engine, monkeypatch):
    scrolls = [(0, None), (50, None), (0, None)]
    eng, st = _rows_test_engine(relist_engine, monkeypatch, scrolls, (5, 100))
    st["screens"] = [scr({1: 87}), scr({1: 50})] + [scr({1: 26}) for _ in range(6)]
    st["mine"] = [87, 50] + [26] * 6
    calls = []
    inner = eng._scroll_page
    monkeypatch.setattr(eng, "_scroll_page", lambda box, target: calls.append(1) or inner(box, target))
    res = eng.relist_all()
    # 1er défilement ignoré, relancé (le compteur dit qu'il en reste), puis vrai bas de liste
    assert len(calls) == 3 and "fin de la liste" in res.message and "bloqué" not in res.message


def test_relist_all_real_bottom_with_counter(relist_engine, monkeypatch):
    eng, st = _rows_test_engine(relist_engine, monkeypatch, [(0, None)], (2, 100))
    st["screens"] = [scr({1: 87}), scr({1: 50})]
    st["mine"] = [87, 50]
    res = eng.relist_all()
    assert "fin de la liste" in res.message


def _gray_fixture(name, crop=None):
    import cv2
    img = cv2.imread(str(FIX / name))
    g = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    return g if crop is None else g[crop[1]:crop[1] + crop[3], crop[0]:crop[0] + crop[2]]


def test_find_scrollbar_on_real_captures():
    # capture « mes ventes » : 51 ventes, poignée au milieu de sa piste
    t0, t1, a, b = core.find_scrollbar(_gray_fixture("hdv_mesventes.png", (600, 140, 98, 540)))
    assert a + 5 < t0 and t1 < b - 5
    # captures du joueur : liste en haut, puis en bas
    t0, t1, a, b = core.find_scrollbar(_gray_fixture("barre_defilement_haut.png"))
    assert t0 <= a + 3 and t1 < b - 100
    t0, t1, a, b = core.find_scrollbar(_gray_fixture("barre_defilement_bas.png"))
    assert t1 >= b - 2 and t0 > a + 100
    assert core.find_scrollbar(_gray_fixture("hdv_mesventes.png", (240, 140, 300, 540))) is None   # pas de barre


def test_find_scrollbar_ignores_bright_scenery_right_of_the_hdv():
    # Décor du jeu à droite de l'HDV : une bande claire « en bas » ne doit pas être prise
    g = _gray_fixture("barre_defilement_haut.png")
    h, w = g.shape
    wide = np.full((h, w + 80), 33, np.uint8)
    wide[:, :w] = g
    wide[h - 60:h, w + 40:w + 48] = 200             # tache claire collée en bas, sans piste
    sb = core.find_scrollbar(wide, min_len=16, expect_x=w // 2, min_track=150)
    t0, t1, a, b = sb
    assert t1 < b - 100                              # la vraie barre (poignée en haut)


def test_scrollbar_at_bottom(monkeypatch):
    cfg = core.Config(relist_row=[100, 100], relist_step=50, relist_rows=10)
    bas = np.dstack([_gray_fixture("barre_defilement_bas.png")] * 3)
    haut = np.dstack([_gray_fixture("barre_defilement_haut.png")] * 3)
    monkeypatch.setattr(core, "grab_screen", lambda r: bas)
    assert core.scrollbar_at_bottom(cfg) is True
    monkeypatch.setattr(core, "grab_screen", lambda r: haut)
    assert core.scrollbar_at_bottom(cfg) is False
    monkeypatch.setattr(core, "grab_screen", lambda r: np.full((300, 200, 3), 33, np.uint8))
    assert core.scrollbar_at_bottom(cfg) is None


def test_relist_all_scrollbar_not_at_bottom_means_blocked(relist_engine, monkeypatch):
    eng, st = _rows_test_engine(relist_engine, monkeypatch, [(0, None), (0, None)], None)
    eng.cfg.count_region = None
    monkeypatch.setattr(core, "scrollbar_at_bottom", lambda c: False)
    st["screens"] = [scr({1: 87}), scr({1: 50})]
    st["mine"] = [87, 50]
    res = eng.relist_all()
    assert "défilement bloqué" in res.message and "barre de défilement" in res.message


def test_relist_all_scrollbar_at_bottom_wins_over_counter(relist_engine, monkeypatch):
    eng, st = _rows_test_engine(relist_engine, monkeypatch, [(0, None)], (40, 100))
    monkeypatch.setattr(core, "scrollbar_at_bottom", lambda c: True)
    st["screens"] = [scr({1: 87}), scr({1: 50})]
    st["mine"] = [87, 50]
    res = eng.relist_all()
    assert "fin de la liste" in res.message


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


def test_relist_confirmation_popup_enter(relist_engine, monkeypatch):
    # fenêtre de confirmation NON reconnue à l'écran : le panneau reste affiché jusqu'au bout
    # de l'attente -> Entrée de secours, comme avant
    eng, calls, st = relist_engine
    monkeypatch.setattr(core, "RELIST_CONFIRM_WAIT", 0)
    st["screens"] = [scr({1: 760})]
    st["mine"] = [774, 759, 759]
    res = eng.relist()
    assert res.level == "ok" and "Entrée de secours" in res.message
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


def test_relist_all_skips_a_row_modified_twice_the_same_way(relist_engine, monkeypatch):
    # « modifié » mais rien n'a changé (prix déjà en place) : la même ligne revient -> passée
    eng, calls, st = relist_engine
    eng.cfg.relist_auto, eng.cfg.relist_row, eng.cfg.relist_step, eng.cfg.relist_rows = True, [100, 100], 50, 3
    clicks = []
    monkeypatch.setattr(core, "click_at", lambda p: clicks.append(p))
    monkeypatch.setattr(core, "mouse_position", lambda: (0, 0))
    monkeypatch.setattr(eng, "_scroll_page", lambda box, target: (0, None))
    n = [0]
    monkeypatch.setattr(core, "grab_screen", lambda r: n.__setitem__(0, n[0] + 1) or
                        np.random.default_rng(n[0]).integers(0, 255, (8, 8, 3)).astype(np.uint8))
    st["screens"] = [scr({1: 87}), scr({1: 760}), scr({1: 760}), scr({1: 50})]
    st["mine"] = [87, 774, None, 774, None, 50]
    res = eng.relist_all()
    assert clicks == [(100, 100), (100, 150), (100, 150), (100, 200)]
    assert "modification répétée sans effet" in res.message and "fin de la liste" in res.message


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


# --- Historique
def test_history_migrates_old_header(tmp_path):
    h = tmp_path / "h.csv"
    old = core.HISTORY_HEADER[:-1]
    h.write_text(",".join(old) + "\n1,2026-11-13 22:05:01,sell,1,1,600,95,599,saisi,fixed,1.0,none\n",
                 encoding="utf-8")
    core.log_history("relist", 1, 1, core.Reading(77, 95), 76, "modified", core.Config(), path=h)
    rows = list(csv.DictReader(h.open(encoding="utf-8")))
    assert list(rows[0]) == core.HISTORY_HEADER and len(rows) == 2
    assert rows[1]["item"] == "" and rows[1]["new_price"] == "76"
    assert not list(tmp_path.glob("*_old_*"))          # rien d'archivé, colonne ajoutée


# --- Tes prix : pas d'undercut contre toi-même
def _name(seed: int) -> np.ndarray:
    """Fausse image de nom d'objet (texte blanc), différente selon `seed`."""
    img = np.zeros((20, 60, 3), np.uint8)
    img[5:15, 4 + seed * 3:20 + seed * 5] = 255
    return img


def test_item_key():
    assert core.item_key(_name(1)) == core.item_key(_name(1).copy())
    assert core.item_key(_name(1)) != core.item_key(_name(2))
    assert core.item_key(np.zeros((20, 60, 3), np.uint8)) is None      # panneau vide
    assert core.item_key(None) is None


def test_my_prices_persist_replace_and_expire(tmp_path, monkeypatch):
    path = tmp_path / "p.json"
    mp = core.MyPrices(path)
    mp.add("abc", 100, 520)
    mp.add("abc", 100, 499, replaces=520)                # vente modifiée : 520 n'existe plus
    again = core.MyPrices(path)                          # nouvelle session
    assert again.has("abc", 100, 499, 0) and not again.has("abc", 100, 520, 0)
    assert not again.has("abc", 10, 499, 0) and not again.has("xyz", 100, 499, 0)
    now = core.time.time()
    monkeypatch.setattr(core.time, "time", lambda: now + core.MY_PRICES_TTL + 1)
    assert not core.MyPrices(path).has("abc", 100, 499, 0)


def test_my_prices_unknown_item_is_short_memory(tmp_path):
    mp = core.MyPrices(tmp_path / "p.json")
    mp.add(None, 1, 75)
    assert mp.has(None, 1, 75, 60) and mp.has("abc", 1, 75, 60)      # par lot seulement, comme avant
    assert not core.MyPrices(tmp_path / "p.json").has(None, 1, 75, 60)  # rien sur le disque
    mp.add("abc", 1, 80, sure=False)
    assert not core.MyPrices(tmp_path / "p.json").has("abc", 1, 80, 60)


def test_relist_never_undercuts_own_listing_next_session(relist_engine, monkeypatch):
    # Tu as 2 ventes du même objet : A à 500 (le moins cher du tableau, c'est toi) et B à 520.
    eng, calls, st = relist_engine
    monkeypatch.setattr(core, "grab_name", lambda c: _name(1))
    st["screens"], st["mine"] = [scr({1: 500})], [500]
    assert "déjà le moins cher" in eng.relist().message       # ligne A : prix noté
    eng2 = core.PriceEngine(eng.cfg)                           # outil relancé
    st["screens"], st["mine"] = [scr({1: 500})], [520, None]
    res = eng2.relist()                                        # ligne B
    assert calls == [("paste", 500), "modify"] and "aligné" in res.message   # pas 499


def test_relist_other_item_same_price_is_undercut(relist_engine, monkeypatch):
    eng, calls, st = relist_engine
    names = iter([_name(1), _name(2)])
    monkeypatch.setattr(core, "grab_name", lambda c: next(names))
    st["screens"], st["mine"] = [scr({1: 500})], [500]
    eng.relist()                                               # objet 1 à 500 : le tien
    st["screens"], st["mine"] = [scr({1: 500})], [520, None]
    eng.relist()                                               # objet 2 : 500 est un concurrent
    assert calls == [("paste", 499), "modify"]


def test_sell_does_not_undercut_own_listing(engine, monkeypatch):
    eng, calls, screen = engine
    monkeypatch.setattr(core, "grab_name", lambda c: _name(3))
    screen({1: R(60, 95), 10: R(590, 95)}, 1)
    eng.sell()                                                 # mis en vente à 59
    screen({1: R(59, 95), 10: R(590, 95)}, 1)
    res = core.PriceEngine(eng.cfg).sell()                     # nouvelle session, même objet
    assert calls[-1] == (59, True, True) and "ton prix" in res.message


def test_relist_all_reports_each_row(relist_engine, monkeypatch):
    eng, calls, st = relist_engine
    seen = []
    eng.progress = seen.append
    eng.cfg.relist_auto, eng.cfg.relist_row, eng.cfg.relist_step = True, [100, 100], 20
    monkeypatch.setattr(core, "click_at", lambda p: None)
    monkeypatch.setattr(core, "mouse_position", lambda: (0, 0))
    monkeypatch.setattr(eng, "_page_rows", lambda shift, base: [(100, 0), (120, 1)])
    monkeypatch.setattr(eng, "_scroll_page", lambda box, target: (0, None))
    monkeypatch.setattr(core, "_same_row", lambda a, b: False)
    st["screens"] = [scr({1: 774}), scr({1: 800})]
    st["mine"] = [774, 800]
    eng.relist_all()
    assert len(seen) == 2 and all("déjà le moins cher" in r.message for r in seen)


def test_relist_logs_observation_when_cheapest(relist_engine, monkeypatch):
    eng, calls, st = relist_engine
    logged = []
    monkeypatch.setattr(core, "log_history", lambda *a, **k: logged.append(a[0]))
    st["screens"] = [scr({1: 774})]
    st["mine"] = [774]
    eng.relist()
    assert logged == ["observe"]


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


# --- Choix de Tesseract : installé (>= 5) sinon celui inclus dans l'exe
@pytest.fixture
def fake_tesseracts(tmp_path, monkeypatch):
    pt = pytest.importorskip("pytesseract")
    monkeypatch.setattr(pt.pytesseract, "tesseract_cmd", pt.pytesseract.tesseract_cmd)  # remis après
    monkeypatch.setattr(core, "TESSERACT_USED", core.TESSERACT_USED)
    installed, bundled = tmp_path / "installed.exe", tmp_path / "bundled" / "tesseract.exe"
    versions = {}

    def setup(installed_ver=None, bundled_ver=None):
        for f, v in ((installed, installed_ver), (bundled, bundled_ver)):
            if v:
                f.parent.mkdir(exist_ok=True)
                f.write_text("")
                versions[str(f)] = v
        monkeypatch.setattr(core, "BUNDLED_TESSERACT", bundled)
        monkeypatch.setattr(core.shutil, "which", lambda name: None)
        monkeypatch.setattr(core, "tesseract_version", lambda cmd: versions.get(str(cmd)))
        return core.Config(tesseract_cmd=str(installed))
    return setup, installed, bundled


def _used():
    import pytesseract
    return pytesseract.pytesseract.tesseract_cmd


def test_tesseract_prefers_recent_installed(fake_tesseracts):
    setup, installed, bundled = fake_tesseracts
    assert core.setup_tesseract(setup((5, 5), (5, 4))) is None
    assert _used() == str(installed) and "installé" in core.TESSERACT_USED


def test_tesseract_old_installed_uses_bundled(fake_tesseracts):
    setup, installed, bundled = fake_tesseracts
    assert core.setup_tesseract(setup((4, 1), (5, 4))) is None
    assert _used() == str(bundled) and core.TESSERACT_USED == "Tesseract 5.4 (inclus)"


def test_tesseract_none_installed_uses_bundled(fake_tesseracts):
    setup, installed, bundled = fake_tesseracts
    assert core.setup_tesseract(setup(None, (5, 4))) is None and _used() == str(bundled)


def test_tesseract_old_without_bundled_warns(fake_tesseracts):
    setup, installed, bundled = fake_tesseracts
    err = core.setup_tesseract(setup((4, 1), None))
    assert "ancien" in err and _used() == str(installed)


def test_tesseract_missing(fake_tesseracts):
    setup, *_ = fake_tesseracts
    assert "introuvable" in core.setup_tesseract(setup(None, None))


# --- Touche restée « enfoncée » dans `keyboard` : plus aucun raccourci ne répondait
def test_release_stuck_keys_fake_module():
    import threading
    import types
    ev = lambda name: types.SimpleNamespace(name=name)
    kb = types.SimpleNamespace(
        _pressed_events={29: ev("ctrl"), 47: ev("v"), 61: ev("f3")},
        _pressed_events_lock=threading.Lock(),
        _logically_pressed_keys={47: ev("v")},
        _listener=types.SimpleNamespace(active_modifiers={29}))
    down = {29: True, 47: False, 61: None}          # ctrl tenu, v relâché (raté), f3 inconnu
    assert core.release_stuck_keys(kb, lambda sc: down[sc]) == ["v"]
    assert set(kb._pressed_events) == {29, 61}       # ctrl gardé, f3 inconnu gardé (prudence)
    assert 47 not in kb._logically_pressed_keys and kb._listener.active_modifiers == {29}


@pytest.mark.skipif(sys.platform != "win32", reason="état réel du clavier : Windows")
def test_release_stuck_keys_real_keyboard():
    import types
    kb = pytest.importorskip("keyboard")
    sc_v = kb.key_to_scan_codes("v")[0]
    with kb._pressed_events_lock:
        saved = dict(kb._pressed_events)
        kb._pressed_events[sc_v] = types.SimpleNamespace(name="v")   # relâchement raté
    try:
        assert "v" in core.release_stuck_keys()      # V n'est pas enfoncée en vrai
        assert sc_v not in kb._pressed_events
    finally:
        with kb._pressed_events_lock:
            kb._pressed_events.clear()
            kb._pressed_events.update(saved)


# --- Nouvelle version publiée ?
@pytest.mark.parametrize("v,parsed", [("v1.2.3", (1, 2, 3)), ("1.10.0", (1, 10, 0)), ("dev", None),
                                      ("dev-abc1234", None), ("v1.2", None), ("", None)])
def test_parse_version(v, parsed):
    assert core.parse_version(v) == parsed


def test_newer_release():
    rel = lambda tag: (lambda timeout: {"tag_name": tag, "html_url": f"https://x/{tag}"})
    assert core.newer_release("v1.0.0", rel("v1.1.0")) == ("v1.1.0", "https://x/v1.1.0")
    assert core.newer_release("v1.0.9", rel("v1.0.10")) == ("v1.0.10", "https://x/v1.0.10")  # pas alphabétique
    assert core.newer_release("v1.1.0", rel("v1.1.0")) is None
    assert core.newer_release("v1.2.0", rel("v1.1.0")) is None
    assert core.newer_release("dev", rel("v9.0.0")) is None              # code source : jamais
    assert core.newer_release("v1.0.0", rel("nightly")) is None

    def offline(timeout):
        raise OSError("pas de réseau")
    assert core.newer_release("v1.0.0", offline) is None                  # hors ligne : silencieux


# --- Fichier journal
def test_file_log_and_tee(tmp_path, monkeypatch):
    import io
    import logging
    monkeypatch.setattr(core, "LOG_DIR", tmp_path / "journaux")
    monkeypatch.setattr(core, "_file_log", None)
    path = core.setup_file_log(capture_std=False)
    try:
        core.log_line("[MAJ] Lot 1 | modifié", "OK")
        core.log_line("[Erreur] boum", "ERROR")
        out = io.StringIO()
        tee = core._TeeStream(out, core._file_log.info)
        print("[Champ] message du moteur", file=tee)
        print("début…", end="", file=tee)                 # ligne incomplète : attend la fin
        print(" fin", file=tee)
        for h in core._file_log.handlers:
            h.flush()
        text = path.read_text(encoding="utf-8")
        assert "Démarrage Dofus Price Helper" in text and "[MAJ] Lot 1 | modifié" in text
        assert "[Erreur] boum" in text and "[Champ] message du moteur" in text and "début… fin" in text
        assert out.getvalue().startswith("[Champ] message du moteur\n")   # la console garde tout
    finally:
        lg = logging.getLogger("dofus_price_helper")
        for h in list(lg.handlers):
            h.close()
            lg.removeHandler(h)


# --- Résumé de fin de Ctrl+F3
def test_relist_all_summary(relist_engine, monkeypatch):
    eng, calls, st = relist_engine
    eng.cfg.relist_auto, eng.cfg.relist_row, eng.cfg.relist_step = True, [100, 100], 20
    monkeypatch.setattr(core, "click_at", lambda p: None)
    monkeypatch.setattr(core, "mouse_position", lambda: (0, 0))
    monkeypatch.setattr(eng, "_page_rows", lambda shift, base: [(100, 0), (120, 1)])
    monkeypatch.setattr(eng, "_scroll_page", lambda box, target: (0, None))
    monkeypatch.setattr(core, "_same_row", lambda a, b: False)
    monkeypatch.setattr(core, "grab_name", lambda c: _name(4))
    st["screens"] = [scr({1: 760}),                 # ligne 1 : concurrent à 760, toi à 774 -> 759
                     scr({1: 759}),                 # ligne 1 relue après modification : c'est toi
                     scr({1: 800})]                 # ligne 2 : déjà le moins cher
    st["mine"] = [774, None, 759, 800]
    res = eng.relist_all()
    assert [(c.row, c.lot, c.old, c.new, c.modified) for c in res.changes] == [(1, 1, 774, 759, True)]
    assert res.changes[0].img is not None              # image du nom gardée pour la fenêtre
    assert res.changes[0].text() == "ligne 1 · lot 1 : 774 → 759 (-1.9%)"


def test_row_change_text_not_modified():
    c = core.RowChange(7, 100, 5200, 4999, False, "Suspect")
    assert c.text() == "ligne 7 · lot 100 : NON modifiée (Suspect)"
    big = core.RowChange(2, 1000, 1520000, 1499999, True)
    assert big.text() == "ligne 2 · lot 1000 : 1 520 000 → 1 499 999 (-1.3%)"


# --- Profils de calibration
def test_profiles_switch_save_load(tmp_path, monkeypatch):
    monkeypatch.setattr(core, "ANCHOR_PATH", tmp_path / "hdv_anchor.png")
    core.ANCHOR_PATH.write_bytes(b"repere-principal")
    path = tmp_path / "cfg.json"
    cfg = core.Config(table_region=[10, 10, 100, 80], price_field=[50, 50], relist_step=24)
    cfg.new_profile("Runes")                                   # copie du profil actuel, activée
    assert cfg.profile == "Runes" and cfg.table_region == [10, 10, 100, 80]
    assert core.anchor_path(cfg).read_bytes() == b"repere-principal"   # repère copié
    cfg.table_region, cfg.relist_step = [300, 20, 100, 80], 30          # recalibré pour les runes
    cfg.save(path)

    again = core.Config.load(path)
    assert again.profile == "Runes" and again.table_region == [300, 20, 100, 80]
    assert again.profile_names() == ["Principal", "Runes"]
    again.switch_profile("Principal")
    assert again.table_region == [10, 10, 100, 80] and again.relist_step == 24
    again.switch_profile("Runes")
    assert again.table_region == [300, 20, 100, 80] and again.relist_step == 30


def test_profiles_names_and_delete(tmp_path, monkeypatch):
    monkeypatch.setattr(core, "ANCHOR_PATH", tmp_path / "hdv_anchor.png")
    cfg = core.Config()
    for bad in ("", "x" * 31, "principal"):                   # vide, trop long, déjà pris
        with pytest.raises(ValueError):
            cfg.new_profile(bad)
    cfg.new_profile("Équipements !")
    a = core.anchor_path(cfg)
    a.write_bytes(b"x")
    assert a.parent == tmp_path and a.name.startswith("hdv_anchor_quipements")
    with pytest.raises(ValueError):
        cfg.delete_profile("Équipements !")                   # actif : refusé
    cfg.switch_profile("Principal")
    cfg.delete_profile("Équipements !")
    assert cfg.profile_names() == ["Principal"] and not a.exists()
    with pytest.raises(KeyError):
        cfg.switch_profile("Équipements !")


def test_reanchor_uses_profile_anchor(tmp_path, monkeypatch):
    monkeypatch.setattr(core, "ANCHOR_PATH", tmp_path / "hdv_anchor.png")
    cfg = core.Config()
    cfg.new_profile("Runes")
    seen = []
    monkeypatch.setattr(core, "load_anchor", lambda p=None: seen.append(p) or None)
    cfg.anchor_region = [0, 0, 10, 10]
    core.PriceEngine(cfg)._reanchor()
    assert seen == [core.anchor_path(cfg)] and seen[0] != core.ANCHOR_PATH


# --- Ctrl+F3 : chronométrage par étape et attente « liste immobile »
def test_timing_text():
    t = {"clic": 2.0, "lecture": 3.0, "saisie": 1.0, "validation": 2.0, "défilement": 0.5}
    txt = core.timing_text(10.0, 10, t)
    assert txt.startswith("durée 10,0 s, 1,00 s/ligne (clic 0,20 · lecture 0,30")
    assert "autre 0,15" in txt
    assert core.timing_text(75.0, 0, {}) == "durée 1 min 15 s"


def test_wait_still_returns_as_soon_as_list_stops(monkeypatch):
    frames = iter([1, 2, 3, 3, 3, 3])                 # la liste bouge 2 fois puis s'arrête
    grabs = []
    monkeypatch.setattr(core, "grab_screen", lambda r: grabs.append(1) or np.full((2, 2), next(frames)))
    monkeypatch.setattr(core.time, "sleep", lambda s: None)
    core.wait_still((0, 0, 2, 2), timeout=5.0)
    assert len(grabs) == 4


def test_relist_all_reports_time_per_row(relist_engine, monkeypatch):
    eng, calls, st = relist_engine
    eng.cfg.relist_auto, eng.cfg.relist_row, eng.cfg.relist_step = True, [100, 100], 20
    monkeypatch.setattr(core, "click_at", lambda p: None)
    monkeypatch.setattr(core, "mouse_position", lambda: (0, 0))
    monkeypatch.setattr(eng, "_page_rows", lambda shift, base: [(100, 0)])
    monkeypatch.setattr(eng, "_scroll_page", lambda box, target: (0, None))
    st["screens"] = [scr({1: 800})]
    st["mine"] = [800]
    res = eng.relist_all()
    assert "s/ligne" in res.message and "lecture" in res.message and "clic" in eng.timing


def test_relist_all_continues_after_many_suspect_rows(relist_engine, monkeypatch):
    # 4 prix suspects de suite : non modifiés, mais le parcours va jusqu'au bout
    eng, calls, st = relist_engine
    eng.cfg.relist_auto, eng.cfg.relist_row, eng.cfg.relist_step, eng.cfg.relist_rows = True, [100, 100], 50, 5
    monkeypatch.setattr(core, "click_at", lambda p: None)
    monkeypatch.setattr(core, "mouse_position", lambda: (0, 0))
    monkeypatch.setattr(eng, "_scroll_page", lambda box, target: (0, None))
    n = [0]
    monkeypatch.setattr(core, "grab_screen", lambda r: n.__setitem__(0, n[0] + 1) or
                        np.random.default_rng(n[0]).integers(0, 255, (8, 8, 3)).astype(np.uint8))
    suspect = lambda: scr({1: 199, 10: 11200})          # prix unitaire x0,2 des autres lots
    st["screens"] = [suspect() for _ in range(8)] + [scr({1: 87})]
    st["mine"] = [614] * 8 + [87]
    res = eng.relist_all()
    assert "fin de la liste" in res.message and "douteuses de suite" not in res.message
    assert sum(1 for c in res.changes if not c.modified) == 4 and ("paste", 198) not in calls


# --- Raccourcis lus dans l'état réel du clavier
class _Keys:
    def __init__(self):
        self.down = set()

    def state(self, vk):
        return 0x8000 if vk in self.down else 0


def _poller():
    k = _Keys()
    p = core.HotkeyPoller(state=k.state)
    p.start = lambda: None                                # pas de fil : on lit à la main
    return k, p


def test_poller_exact_modifiers_and_one_shot():
    k, p = _poller()
    hits = []
    p.add("f3", lambda: hits.append("f3"))
    p.add("ctrl+f3", lambda: hits.append("ctrl+f3"))
    p.poll_once()
    k.down = {0x11}; p.poll_once()                        # Ctrl
    k.down = {0x11, 0x72}; p.poll_once(); p.poll_once()   # Ctrl+F3 tenu : une seule fois
    assert hits == ["ctrl+f3"]
    k.down = set(); p.poll_once()
    k.down = {0x72}; p.poll_once()                        # F3 seul
    k.down = {0x11, 0x12, 0x72}; p.poll_once()            # Ctrl+Alt+F3 : rien (pas exact)
    assert hits == ["ctrl+f3", "f3"]


def test_poller_survives_errors_and_ignores_keys_held_at_registration():
    k, p = _poller()
    hits = []
    k.down = {0x11, 0x72}
    p.add("ctrl+f3", lambda: 1 / 0)                       # action en erreur
    p.add("ctrl+alt+p", lambda: hits.append("pause"))
    p.poll_once()                                         # Ctrl+F3 déjà tenu à l'ajout : rien
    k.down = set(); p.poll_once()
    k.down = {0x11, 0x72}; p.poll_once()                  # erreur notée, rien ne s'arrête
    k.down = {0x11, 0x12, 0x50}; p.poll_once()
    assert hits == ["pause"] and p.errors and "ctrl+f3" in p.errors[0]
    p.clear()
    k.down = set(); p.poll_once(); k.down = {0x11, 0x12, 0x50}; p.poll_once()
    assert hits == ["pause"]


def test_poller_sees_ctrl_through_hook_when_key_state_misses_it():
    k = _Keys()
    hook = core.ModifierHook()
    hook.start = lambda: None
    p = core.HotkeyPoller(state=k.state, hook=hook)
    p.start = lambda: None
    hits = []
    p.add("f3", lambda: hits.append("f3"))
    p.add("ctrl+f3", lambda: hits.append("ctrl+f3"))
    p.poll_once()
    hook.event(0xA2, True)                                # Ctrl tenu, absent de l'état Windows
    k.down = {0x72}; p.poll_once()
    assert hits == ["ctrl+f3"]
    k.down = set(); p.poll_once()
    hook.event(0xA2, False)
    k.down = {0x72}; p.poll_once()
    assert hits == ["ctrl+f3", "f3"]
    hook.event(0xA2, True, t=0.0)                         # relâchement manqué : périmé
    assert hook.mods(now=core.ModifierHook.FRESH + 1) == set()


def test_parse_combo():
    assert core.parse_combo("ctrl+alt+f12") == (frozenset({"ctrl", "alt"}), 0x7B)
    assert core.parse_combo("page up") == (frozenset(), 0x21)
    with pytest.raises(ValueError):
        core.parse_combo("ctrl+")
    with pytest.raises(ValueError):
        core.parse_combo("f3+f4")
