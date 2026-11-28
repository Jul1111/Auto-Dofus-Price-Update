"""Fonctions pures de l'interface : aperçu des prix, filtres du journal, historique Ctrl+F3."""
import pytest

from dofus_helper import core

pytest.importorskip("customtkinter")
from dofus_helper import gui  # noqa: E402


# ---- aperçu des prix (onglet Prix)
def test_preview_default_settings():
    lines = gui.price_preview("fixed", 1, "none", 1, 0.7, "floor")
    assert lines[0] == "Moins cher 1 000 → ton prix 999   (plancher 700)"
    assert lines[1].endswith("→ ton prix 700 (plancher)")


def test_preview_percent_and_rounding():
    lines = gui.price_preview("percent", 5, "down_100", 1, 0, "floor")
    assert lines[0] == "Moins cher 1 000 → ton prix 900"          # 950 arrondi à la centaine inférieure
    assert lines[1].endswith("→ ton prix 400")                     # pas de plancher


def test_preview_keep_mode():
    assert "garde son prix" in gui.price_preview("fixed", 1, "none", 1, 0.7, "keep")[1]


def test_preview_stop_mode_is_suspect():
    lines = gui.price_preview("fixed", 1, "none", 1, 0.7, "stop", min_avg_ratio=0.5)
    assert "plancher" not in lines[0]                              # « arrêt » : pas de plancher
    assert "suspect" in lines[1]


def test_preview_matches_engine_functions():
    # l'aperçu utilise exactement le calcul du moteur
    new = core.compute_price(1000, "fixed", 25, "end_9", 1)
    assert gui.price_preview("fixed", 25, "end_9", 1, 0, "floor")[0].endswith(gui.fmt(new))


# ---- journal
@pytest.mark.parametrize("msg,tag,cat", [
    ("[VENTE] Lot 1 | Lu: 1000 -> 999 | mis en vente", "OK", "sale"),
    ("   [MAJ] Lot 10 | modifié", "OK", "sale"),
    ("[OPT] Lot 100", "OPT", "sale"),
    ("[VENTE] Lot 1 | SUSPECT", "WARN", "problem"),
    ("[Hotkeys] Prêt.", "INFO", "info"),
    ("[Calib] Tableau = (1, 2, 3, 4)", "CAL", "info"),
    ("[Erreur] boom", "ERROR", "problem"),
])
def test_log_category(msg, tag, cat):
    assert gui.log_category(msg, tag) == cat


def test_log_visible():
    assert gui.log_visible("info", "all")
    assert not gui.log_visible("info", "sale")
    assert gui.log_visible("info", "sale", in_block=True)    # tout le bloc Ctrl+F3 est une vente
    assert gui.log_visible("problem", "problem")
    assert not gui.log_visible("sale", "problem")


# ---- historique des parcours Ctrl+F3
def test_runs_round_trip(tmp_path):
    import numpy as np
    path = tmp_path / "runs.json"
    runs = [{"time": 1000.0 + i, "changes": [
        core.RowChange(1, 10, 1200, 1099, True, img=np.zeros((5, 5, 3), np.uint8)),
        core.RowChange(2, None, None, None, False, "ton prix illisible")]} for i in range(gui.MAX_RUNS + 3)]
    gui.save_runs(runs, path)
    back = gui.load_runs(path)
    assert len(back) == gui.MAX_RUNS                           # les plus anciens sont oubliés
    assert back[-1]["time"] == runs[-1]["time"]
    c1, c2 = back[-1]["changes"]
    assert (c1.row, c1.lot, c1.old, c1.new, c1.modified, c1.img) == (1, 10, 1200, 1099, True, None)
    assert (c2.modified, c2.note) == (False, "ton prix illisible")
    assert "1 prix modifié" in gui.run_title(back[-1]) and "1 à revoir" in gui.run_title(back[-1])


def test_load_runs_tolerates_bad_files(tmp_path):
    assert gui.load_runs(tmp_path / "absent.json") == []
    bad = tmp_path / "bad.json"
    bad.write_text("{pas du json", encoding="utf-8")
    assert gui.load_runs(bad) == []
    bad.write_text('[{"time": 1}, {"time": 2, "changes": []}]', encoding="utf-8")
    assert [r["time"] for r in gui.load_runs(bad)] == [2.0]


# ---- fenêtre
@pytest.mark.parametrize("geom,ok", [
    ("1120x800+40+40", True),
    ("1120x800+-1000+40", True),            # en partie à gauche : encore attrapable
    ("1120x800+5000+40", False),            # écran débranché
    ("1120x800+40+2000", False),
    ("50x50+10+10", False),                 # trop petite
    ("", False), ("zoomed", False), ("n'importe quoi", False),
])
def test_geometry_on_screen(geom, ok):
    assert gui.geometry_on_screen(geom, (0, 0, 1920, 1080)) is ok


def test_scale_label():
    assert gui.scale_label(1.0) == "100 %"
    assert gui.scale_label(1.24) == "125 %"
    assert gui.scale_label(7) == "150 %"


def test_new_config_fields_round_trip(tmp_path):
    path = tmp_path / "cfg.json"
    cfg = core.Config()
    cfg.ui_scale, cfg.window_geometry = 1.25, "1200x850+10+20"
    cfg.save(path)
    back = core.Config.load(path)
    assert (back.ui_scale, back.window_geometry) == (1.25, "1200x850+10+20")
