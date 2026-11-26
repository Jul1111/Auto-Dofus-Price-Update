"""Mise à jour en un clic et rapport de problème."""
import hashlib
import io
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import dofus_core as core  # noqa: E402
import dofus_update as du  # noqa: E402


def release(tag="v1.2.0", digest="sha256:abc", with_zip=True):
    assets = [{"name": "notes.txt", "browser_download_url": "https://x/notes.txt", "size": 3}]
    if with_zip:
        assets.append({"name": f"DofusPriceHelper-{tag}.zip", "browser_download_url": f"https://x/{tag}.zip",
                       "size": 1234, "digest": digest})
    return lambda timeout: {"tag_name": tag, "html_url": f"https://x/{tag}", "assets": assets}


def test_find_update_reads_zip_asset(monkeypatch):
    up = du.find_update("v1.1.0", release())
    assert (up.tag, up.page_url, up.zip_url, up.size, up.sha256) == \
        ("v1.2.0", "https://x/v1.2.0", "https://x/v1.2.0.zip", 1234, "abc")
    assert not up.installable                       # code source : pas d'installation
    monkeypatch.setattr(core, "IS_FROZEN", True)
    assert up.installable
    assert not du.find_update("v1.1.0", release(with_zip=False)).installable   # pas de zip : page
    assert du.find_update("v1.2.0", release()) is None
    assert du.find_update("dev", release()) is None


class _Resp(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def test_download_checks_size_and_hash(tmp_path):
    data = b"x" * 5000
    good = du.Update("v1.2.0", "", "https://x/z.zip", len(data), hashlib.sha256(data).hexdigest())
    seen = []
    out = du.download(good, tmp_path, lambda d, t: seen.append(d), opener=lambda req, timeout: _Resp(data))
    assert out.read_bytes() == data and seen[-1] == 5000
    short = du.Update("v1.2.0", "", "https://x/z.zip", 9999)
    with pytest.raises(RuntimeError, match="incomplet"):
        du.download(short, tmp_path, opener=lambda req, timeout: _Resp(data))
    bad = du.Update("v1.2.0", "", "https://x/z.zip", len(data), "0" * 64)
    with pytest.raises(RuntimeError, match="corrompu"):
        du.download(bad, tmp_path, opener=lambda req, timeout: _Resp(data))


def _zip(path, names):
    with zipfile.ZipFile(path, "w") as z:
        for n in names:
            z.writestr(n, "x")
    return path


def test_unpack_checks_content(tmp_path):
    ok = _zip(tmp_path / "ok.zip", ["DofusPriceHelper/DofusPriceHelper.exe", "DofusPriceHelper/_internal/a.dll"])
    app = du.unpack(ok, tmp_path / "a")
    assert (app / "DofusPriceHelper.exe").is_file()
    with pytest.raises(RuntimeError, match="suspect"):
        du.unpack(_zip(tmp_path / "evil.zip", ["../../evil.exe"]), tmp_path / "b")
    with pytest.raises(RuntimeError, match="inattendu"):
        du.unpack(_zip(tmp_path / "other.zip", ["autre/chose.txt"]), tmp_path / "c")


def test_installer_script_quotes_paths(tmp_path):
    s = du.installer_script(Path("C:/n"), Path("C:/Jeux d'été/DofusPriceHelper"), 42, Path("C:/w"),
                            Path("C:/l.log"))
    assert "Jeux d''été" in s and "Wait-Process -Id 42" in s and "Start-Process -FilePath" in s
    assert "Start-Process -FilePath" not in du.installer_script(Path("C:/n"), Path("C:/a"), 1, Path("C:/w"),
                                                                 Path("C:/l"), relaunch=False)


@pytest.mark.skipif(sys.platform != "win32" or shutil.which("powershell") is None, reason="Windows seulement")
def test_installer_replaces_files_and_keeps_user_files(tmp_path):
    app = tmp_path / "Mes jeux d'été [x]" / "DofusPriceHelper"
    work = tmp_path / "work"
    new = work / "nouveau" / "DofusPriceHelper"
    for d, ver in ((app, "old"), (new, "new")):
        (d / "_internal").mkdir(parents=True)
        (d / "DofusPriceHelper.exe").write_text(ver)
        (d / "_internal" / f"{ver}.dll").write_text(ver)
    (app / "mes notes.txt").write_text("à garder", encoding="utf-8")
    log = tmp_path / "maj.log"
    script = tmp_path / "installer.ps1"
    script.write_text(du.installer_script(new, app, 999999, work, log, relaunch=False), encoding="utf-8-sig")
    subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script)],
                   check=True, capture_output=True, timeout=120)
    assert (app / "DofusPriceHelper.exe").read_text() == "new"
    assert (app / "_internal" / "new.dll").exists() and not (app / "_internal" / "old.dll").exists()
    assert not (app / "_internal.old").exists() and not work.exists()
    assert (app / "mes notes.txt").read_text(encoding="utf-8") == "à garder"
    assert "installée" in log.read_text(encoding="utf-8-sig")


@pytest.mark.skipif(sys.platform != "win32" or shutil.which("powershell") is None, reason="Windows seulement")
def test_spawned_script_really_runs(tmp_path):
    # v1.3.0 / v1.4.0 : lancé « détaché », PowerShell ne s'exécutait jamais (rien d'installé)
    import time
    out = tmp_path / "ok.txt"
    script = tmp_path / "s.ps1"
    script.write_text(f"Set-Content -LiteralPath '{out}' -Value 'ok'", encoding="utf-8-sig")
    du.spawn_script(script)
    end = time.time() + 20
    while not out.exists() and time.time() < end:
        time.sleep(0.2)
    assert out.exists()


@pytest.mark.skipif(sys.platform != "win32" or shutil.which("powershell") is None, reason="Windows seulement")
def test_installer_waits_while_internal_is_busy(tmp_path):
    # Fichier de _internal encore ouvert quelques secondes (antivirus, 2e fenêtre qui se ferme) :
    # avant, « accès refusé » et échec immédiat.
    app = tmp_path / "app" / "DofusPriceHelper"
    work = tmp_path / "work"
    new = work / "nouveau" / "DofusPriceHelper"
    for d, ver in ((app, "old"), (new, "new")):
        (d / "_internal").mkdir(parents=True)
        (d / "DofusPriceHelper.exe").write_text(ver)
        (d / "_internal" / f"{ver}.dll").write_text(ver)
    locker = subprocess.Popen([sys.executable, "-c",
                               "import sys, time; f = open(sys.argv[1]); time.sleep(3)",
                               str(app / "_internal" / "old.dll")])
    import time
    time.sleep(0.5)
    log = tmp_path / "maj.log"
    script = tmp_path / "installer.ps1"
    script.write_text(du.installer_script(new, app, 999999, work, log, relaunch=False), encoding="utf-8-sig")
    subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script)],
                   check=True, capture_output=True, timeout=120)
    locker.wait()
    assert (app / "DofusPriceHelper.exe").read_text() == "new"
    assert "installée" in log.read_text(encoding="utf-8-sig")


@pytest.mark.skipif(sys.platform != "win32", reason="Windows seulement")
def test_single_instance_waits_for_the_closing_copy():
    # Changement de thème : l'ancien exemplaire se ferme pendant que le nouveau démarre
    import threading
    import time
    name = rf"Local\DofusPriceHelper-wait-{__import__('os').getpid()}"
    import ctypes
    k32 = ctypes.WinDLL("kernel32")
    k32.CreateMutexW.restype = ctypes.c_void_p
    old = k32.CreateMutexW(None, False, name)          # « ancien exemplaire »
    threading.Timer(0.6, lambda: k32.CloseHandle(ctypes.c_void_p(old))).start()
    t0 = time.time()
    keep = du._instance_mutex
    assert du.single_instance(name, wait=5.0)
    assert 0.4 < time.time() - t0 < 4
    du._instance_mutex = keep


def test_single_instance():
    name = rf"Local\DofusPriceHelper-test-{__import__('os').getpid()}"
    assert du.single_instance(name)
    keep = du._instance_mutex
    assert not du.single_instance(name)          # déjà ouvert (aucune fenêtre à ramener ici)
    du._instance_mutex = keep


# --- Rapport de problème
def test_report_contains_what_helps_and_no_sales(tmp_path, monkeypatch):
    monkeypatch.setattr(core, "LOG_DIR", tmp_path / "journaux")
    monkeypatch.setattr(core, "DEBUG_DIR", tmp_path / "captures")
    monkeypatch.setattr(core, "CONFIG_PATH", tmp_path / "config.json")
    core.LOG_DIR.mkdir()
    (core.LOG_DIR / "journal.log").write_text("ligne")
    core.DEBUG_DIR.mkdir()
    (core.DEBUG_DIR / "champ.png").write_bytes(b"png")
    core.CONFIG_PATH.write_text("{}")
    monkeypatch.setattr(core, "grab_screen", lambda r: np.zeros((r[3], r[2], 3), np.uint8))
    cfg = core.Config(table_region=[100, 200, 50, 40], price_field=[80, 150])
    out = du.make_report(cfg, tmp_path / "rapports")
    names = du.report_files(out)
    assert {"infos.txt", "reglages.json", "journaux/journal.log", "captures/champ.png", "hdv.png"} <= set(names)
    assert not any("history" in n or "my_prices" in n for n in names)
    with zipfile.ZipFile(out) as z:
        assert "Non inclus" in z.read("infos.txt").decode("utf-8")


def test_hdv_box_covers_all_zones():
    cfg = core.Config(table_region=[100, 200, 50, 40], price_field=[80, 150], relist_row=[400, 120])
    assert du.hdv_box(cfg, margin=10) == (70, 110, 340, 140)
    assert du.hdv_box(core.Config(), margin=10) is None
