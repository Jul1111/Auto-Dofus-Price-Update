"""Interface : panneau Activité, progression des boucles, notification, aide-mémoire."""
import pytest

import dofus_core as core

pytest.importorskip("customtkinter")
import dofus_price_helper_psg as gui  # noqa: E402


def R(msg, level="ok", lot=1, new=None, old=None, hint=""):
    return core.Result(lot, level, msg, new_price=new, old_price=old, hint=hint)


# ---- panneau Activité
def test_action_entry_sale():
    e = gui.action_entry(R("[VENTE] Lot 10 | Lu: 9500 -> 9499 | mis en vente", lot=10, new=9499,
                           hint="Mis en vente"), when=0)
    assert e["text"] == "Vente · lot 10 → 9 499" and e["hint"] == "Mis en vente" and e["level"] == "ok"


def test_action_entry_update_shows_old_and_new():
    e = gui.action_entry(R("   [MAJ] Lot 1 | modifié", new=1099, old=1200))
    assert e["text"] == "Mise à jour · lot 1 : 1 200 → 1 099"


def test_action_entry_whole_list_and_errors():
    assert gui.action_entry(R("[MAJ TOUT] 12 lignes", lot=None, hint="3 modifiées"))["text"] == "Toute la liste"
    e = gui.action_entry(R("[VENTE] Lot 1 : aucun prix lu", "error", hint=""))
    assert e["text"] == "Vente · lot 1" and e["hint"] == "erreur"
    assert gui.action_entry(R("Lecture déjà en cours", "warn", lot=None))["text"] == "Action"


# ---- progression
def test_progress_text_with_total():
    text, frac = gui.progress_text({"row": 34, "changed": 12, "bad": 2, "total": 87})
    assert text == "Ligne 34 / 87 · 12 modifiées · 2 à revoir" and frac == pytest.approx(34 / 87)


def test_progress_text_without_total():
    text, frac = gui.progress_text({"row": 5, "changed": 1, "bad": 0, "total": None})
    assert text == "Ligne 5 · 1 modifiée" and frac is None
    assert gui.progress_text({"row": None})[0] == "Démarrage…"
    assert gui.progress_text({"row": 120, "total": 100})[1] == 1.0     # jamais plus que plein


# ---- notification Windows
def test_windows_notify_passes_text_by_environment(monkeypatch):
    import subprocess
    import sys
    monkeypatch.setattr(sys, "platform", "win32")
    seen = {}

    def fake_popen(cmd, env=None, **kw):
        seen["cmd"], seen["env"], seen["kw"] = cmd, env, kw
    monkeypatch.setattr(subprocess, "Popen", fake_popen)
    title, body = "Fin « $(rm) »", "<b>12</b> prix ; 'x'"
    assert gui.windows_notify(title, body) is True
    script = seen["cmd"][-1]
    assert title not in script and body not in script                  # jamais dans le code exécuté
    assert seen["env"]["DPH_TITLE"] == title and seen["env"]["DPH_BODY"] == body
    assert "SecurityElement]::Escape" in script                         # échappé pour le XML
    assert seen["kw"]["creationflags"] == 0x08000000                    # pas de fenêtre de console
    assert "\\WindowsPowerShell\\v1.0\\powershell.exe" in script


def test_windows_notify_off_windows(monkeypatch):
    import sys
    monkeypatch.setattr(sys, "platform", "linux")
    assert gui.windows_notify("a", "b") is False


# ---- aide-mémoire
def test_cheatsheet_keys_exist():
    assert set(gui.App.CHEAT_KEYS) <= set(core.DEFAULT_HOTKEYS)
    assert set(gui.App.CHEAT_KEYS) == set(gui.App.CHEAT_TEXT)
    assert core.DEFAULT_HOTKEYS["cheatsheet"] == "ctrl+alt+h"
    others = {k: v for k, v in core.DEFAULT_HOTKEYS.items() if k != "cheatsheet"}
    assert gui.hotkey_problem("cheatsheet", "ctrl+alt+h", others) is None   # libre, pas une touche d'écriture


def test_first_steps_and_new_config_fields(tmp_path):
    assert [k for k, _ in gui.FIRST_STEPS] == ["calib", "read", "sell"]
    path = tmp_path / "cfg.json"
    cfg = core.Config()
    assert cfg.notify is True and cfg.first_steps == []
    cfg.first_steps, cfg.notify = ["read"], False
    cfg.save(path)
    back = core.Config.load(path)
    assert back.first_steps == ["read"] and back.notify is False
    assert back.hotkeys["cheatsheet"] == "ctrl+alt+h"
