"""Calibration automatique sur de vraies captures de l'HDV à plusieurs tailles
(résolution 1920 / 2560, interface 80 / 90 / 100 %)."""
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from dofus_helper import autocal as ac  # noqa: E402
from dofus_helper import core  # noqa: E402

cv2 = pytest.importorskip("cv2")

FX = Path(__file__).parent / "fixtures"
# capture -> (tableau, compteur, ton prix, prix moyen) ; une de tes ventes sélectionnée
SALE = ({1: 1989, 10: 39999, 100: 159996, 1000: 1599960}, (113, 210), 1989, 2092)
CAPTURES = {
    "hdv_echelles/2560x1440_90.png": SALE,
    "hdv_echelles/2560x1440_80.png": (SALE[0], (106, 210), 1989, 2092),
    "hdv_echelles/2560x1440_100.png": (SALE[0], (106, 210), 1989, 2092),
    "hdv_echelles/1920x1080_90.png": SALE,
    # texte adouci (jeu mis à l'échelle) : en noir et blanc, « 1 989 » était lu « 1909 »
    "hdv_echelles/1920x1200_90.png": (SALE[0], (108, 210), 1989, 2092),
    "hdv_mesventes.png": ({1: 760, 10: 6999, 100: 83199, 1000: 844000}, (51, 104), 774, 1189),
}
SCALES = {"2560x1440_90": 1.0, "2560x1440_80": 0.876, "2560x1440_100": 1.124, "1920x1080_90": 1.0,
          "1920x1200_90": 0.90, "hdv_mesventes": 1.0}
OFFSET = (700, 300)      # place de la capture dans un faux écran 2560 x 1440


def fake_screen(name: str) -> np.ndarray:
    img = cv2.imread(str(FX / name))
    screen = (np.random.default_rng(1).random((1440, 2560, 3)) * 60).astype(np.uint8)
    x, y = OFFSET
    screen[y:y + img.shape[0], x:x + img.shape[1]] = img
    return screen


@pytest.fixture(scope="module")
def located():
    return {name: (fake_screen(name), ac.locate(fake_screen(name))) for name in CAPTURES}


@pytest.mark.parametrize("name", CAPTURES)
def test_finds_hdv_and_scale(located, name):
    _, res = located[name]
    assert res.ok, res.message
    assert res.scale == pytest.approx(SCALES[Path(name).stem], abs=0.03)
    assert len(res.found) >= 4


def test_reference_capture_gives_the_manual_calibration(located):
    # capture du modèle : les zones retombent sur la calibration manuelle validée en jeu
    _, res = located["hdv_echelles/2560x1440_90.png"]
    f, (x, y) = res.fields, OFFSET
    assert f["anchor_region"] == [x + 303, y + 18, 149, 16]
    assert f["price_field"] == [x + 79, y + 195]
    assert f["modify_button"] == [x + 178, y + 387]
    assert f["table_region"] == [x + 62, y + 480, 155, 125]
    assert abs(f["relist_row"][1] - (y + 190)) <= 2
    assert f["relist_step"] in (49, 50)


def test_nothing_found_on_empty_screen():
    screen = (np.random.default_rng(2).random((1080, 1920, 3)) * 80).astype(np.uint8)
    res = ac.locate(screen)
    assert not res.ok and "français" in res.message


def test_apply_writes_profile_and_anchor(located, tmp_path):
    screen, res = located["hdv_echelles/2560x1440_80.png"]
    cfg = core.Config(mine_region=[1, 2, 3, 4])
    ac.apply(cfg, res, screen)
    assert cfg.table_region == res.fields["table_region"] and cfg.mine_region is None
    tpl = core.load_anchor(core.anchor_path(cfg))
    x, y, w, h = cfg.anchor_region
    assert tpl.shape[:2] == (h, w)
    assert core.anchor_score(screen[y:y + h, x:x + w], tpl) > 0.99


# --- De bout en bout : les zones trouvées se lisent vraiment (Tesseract)
@pytest.mark.parametrize("name", CAPTURES)
def test_found_zones_read_correctly(located, monkeypatch, name):
    pytest.importorskip("pytesseract")
    if core.setup_tesseract(core.Config()) is not None:
        pytest.skip("tesseract absent")
    screen, res = located[name]
    monkeypatch.setattr(core, "grab_screen",
                        lambda r: screen[r[1]:r[1] + r[3], r[0]:r[0] + r[2]].copy())
    cfg = core.Config()
    ac.apply(cfg, res, screen)
    values, counter, mine, avg = CAPTURES[name]
    sr = core.read_screen(cfg, with_mine=True)
    assert sr.values == values
    assert sr.selected == 1
    assert sr.avg == avg
    # ton prix, comme F3 : lecture groupée, relue seule (et en gris) si peu sûre
    got = sr.mine_r
    if got is None or got.value is None or got.confidence < core.MINE_SURE:
        got = core.surer(got, core.read_mine(cfg))
    assert got.value == mine
    assert core.read_mine(cfg).value == mine
    assert core.read_counter(cfg) == counter
    assert core.detect_panel(cfg) == "relist"
    assert core.item_key(core.grab_name(cfg)) is not None
    for zone in core.CUT_CHECK_ZONES:
        assert core.cut_text_hint(zone, getattr(cfg, f"{zone}_region")) is None, zone


# --- Repère perdu (taille de l'HDV changée) : calibration automatique refaite toute seule
def _engine_on(monkeypatch, screen, **kw):
    monkeypatch.setattr(core, "grab_screen", lambda r: screen[r[1]:r[1] + r[3], r[0]:r[0] + r[2]].copy())
    monkeypatch.setattr(core, "screen_bounds", lambda: (0, 0, screen.shape[1], screen.shape[0]))
    cfg = core.Config(**kw)
    cfg.save = lambda *a, **k: None
    return core.PriceEngine(cfg)


def test_lost_anchor_triggers_auto_recalibration(located, monkeypatch):
    # calibré à 90 %, puis l'interface passe à 80 % : le repère n'est plus retrouvé
    big, res90 = located["hdv_echelles/2560x1440_90.png"]
    small, res80 = located["hdv_echelles/2560x1440_80.png"]
    eng = _engine_on(monkeypatch, big)
    ac.apply(eng.cfg, res90, big)
    eng = _engine_on(monkeypatch, small, **{f: eng.cfg.__dict__[f] for f in core.PROFILE_FIELDS})
    assert eng._reanchor() is None
    assert eng.cfg.table_region == res80.fields["table_region"]
    assert "calibration automatique refaite" in eng.last_anchor_msg
    assert eng._reanchor() is None and eng.cfg.table_region == res80.fields["table_region"]  # stable


def test_auto_recalibration_off_or_failing_changes_nothing(located, monkeypatch):
    big, res90 = located["hdv_echelles/2560x1440_90.png"]
    eng = _engine_on(monkeypatch, big)
    ac.apply(eng.cfg, res90, big)
    fields = {f: eng.cfg.__dict__[f] for f in core.PROFILE_FIELDS}
    empty = (np.random.default_rng(3).random((1440, 2560, 3)) * 60).astype(np.uint8)   # HDV fermé
    calls = []
    real = ac.locate
    monkeypatch.setattr(ac, "locate", lambda *a, **k: calls.append(1) or real(*a, **k))
    eng = _engine_on(monkeypatch, empty, auto_recalibrate=False, **fields)
    eng._reanchor()
    assert not calls and "introuvable" in eng.last_anchor_msg
    eng = _engine_on(monkeypatch, empty, **fields)
    eng._reanchor()
    eng._reanchor()                       # 2e essai dans les 30 s : pas de nouvelle recherche
    assert len(calls) == 1 and "introuvable" in eng.last_anchor_msg
    assert eng.cfg.table_region == fields["table_region"]


# --- Ton prix : 2e avis en niveaux de gris
def test_gray_reading_of_field_with_caret(monkeypatch):
    pytest.importorskip("pytesseract")
    if core.setup_tesseract(core.Config()) is not None:
        pytest.skip("tesseract absent")
    img = cv2.imread(str(FX / "champ_curseur.png"))
    monkeypatch.setattr(core, "grab_screen", lambda r: img[r[1]:r[1] + r[3], r[0]:r[0] + r[2]].copy())
    h, w = img.shape[:2]
    assert core.read_mine_gray(core.Config(mine_region=[0, 0, w, h])).value == 496


def test_surer_keeps_the_surest_reading():
    R = core.Reading
    assert core.surer(R(1909, 62.0, "1909"), R(1989, 88.0, "1989")).value == 1989
    assert core.surer(R(None, -1.0, ""), R(774, 50.0, "774")).value == 774
    assert core.surer(R(774, 96.0, "774"), R(None, -1.0, "")).value == 774
    assert core.surer(None, None).value is None
