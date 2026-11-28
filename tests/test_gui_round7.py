"""Récap de fin de Ctrl+F3 (le HUD « objet sélectionné » : test_hud_selected.py)."""
import pytest

from dofus_helper import core

pytest.importorskip("customtkinter")
from dofus_helper import gui  # noqa: E402


def R(msg, lot=10, price=9499, level="ok", old=None):
    return core.Result(lot, level, msg, new_price=price, old_price=old)


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


def test_stop_key_only_stops_the_loop():
    calls = []
    fake = type("A", (), {})()
    fake.cfg = core.Config()
    fake._stop_loop = lambda: calls.append("stop")
    fake._hud_message = lambda *a, **k: calls.append("message")
    fake._loop = {"kind": "relist_all"}
    gui.App._on_pause_key(fake)                 # parcours en cours : arrêt
    fake._loop = None
    gui.App._on_pause_key(fake)                 # rien en cours : simple message, pas de pause
    assert calls == ["stop", "message"]
    assert not hasattr(gui.App, "_toggle_pause") and "pause" not in gui.TRAY_STATES
