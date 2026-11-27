"""HUD « 3 derniers prix » et récap de fin de Ctrl+F3."""
import pytest

import dofus_core as core

pytest.importorskip("customtkinter")
import dofus_price_helper_psg as gui  # noqa: E402


def R(msg, lot=10, price=9499, level="ok", old=None):
    return core.Result(lot, level, msg, new_price=price, old_price=old)


def test_hud_history_line_keeps_only_prices_set_or_proposed():
    text, level, hhmm = gui.hud_history_line(R("[VENTE] Lot 10 | Lu: 9500 -> 9499 | saisi"))
    assert text == "✓ Lot 10  9 499" and level == "ok" and len(hhmm) == 5
    text, _l, _t = gui.hud_history_line(R("[MAJ] Lot 100 | ton prix 52000 -> 49999 | modifié", 100, 49999,
                                          old=52000))
    assert text == "✓ Lot 100  52 000 → 49 999"
    assert gui.hud_history_line(R("[MAJ] Lot 10 | ... | SUSPECT (...)", level="warn"))[0].startswith("! ")
    assert gui.hud_history_line(R("   [MAJ] Lot 1 | déjà le moins cher, rien à faire", 1, 500, old=500)) is None
    assert gui.hud_history_line(R("[MAJ TOUT] 12 lignes vues", None, None)) is None
    assert gui.hud_history_line(R("[LECTURE] Lot 10", 10, None)) is None
    assert gui.hud_history_line(R("[TOUT] 3×10 | arrêt : fin")) is None     # fin de F2 : déjà ligne par ligne


def test_duration_text():
    assert gui.duration_text(None) == "0 s"
    assert gui.duration_text(42.4) == "42 s"
    assert gui.duration_text(125) == "2 min 05"


def test_runs_keep_summary_and_read_old_files(tmp_path):
    run = {"time": 1.0, "summary": {"seen": 12, "changed": 1, "same": 11, "complete": True, "seconds": 30.5},
           "log_ids": [4],
           "changes": [core.RowChange(1, 10, 500, 450, True)]}
    path = tmp_path / "runs.json"
    gui.save_runs([run], path)
    back = gui.load_runs(path)
    assert back[0]["summary"] == run["summary"] and "log_ids" not in back[0]
    assert back[0]["changes"][0].new == 450
    path.write_text('[{"time": 2, "changes": []}]', encoding="utf-8")        # avant le récap
    assert gui.load_runs(path)[0]["summary"] == {}
