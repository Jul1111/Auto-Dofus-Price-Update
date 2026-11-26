"""Mise à jour en un clic (version exe) et rapport de problème.

Mise à jour : le zip de la dernière version (GitHub Releases) est téléchargé et vérifié
(taille, empreinte SHA-256), décompressé dans un dossier temporaire, puis un petit script
PowerShell attend la fermeture de l'outil, remplace ses fichiers (l'ancien dossier _internal
est gardé jusqu'à la fin de la copie, et remis en place si elle échoue) et relance l'outil.
Les réglages et la calibration sont dans %APPDATA%, ils ne sont pas touchés.

Rapport : un zip avec ce qui sert à comprendre un problème (journal, réglages, captures
de diagnostic, image de l'HDV), à envoyer à la main. Rien n'est envoyé automatiquement.
"""
from __future__ import annotations

import hashlib
import json
import os
import platform
import shutil
import subprocess
import sys
import tempfile
import time
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, List, Optional

import dofus_core as core

APP_NAME = "DofusPriceHelper"
ISSUES_URL = f"https://github.com/{core.GITHUB_REPO}/issues/new"
REPORT_DIR = core.BASE_DIR / "rapports"


# --------------------------------------------------------------------------
# Mise à jour
# --------------------------------------------------------------------------
@dataclass
class Update:
    tag: str
    page_url: str
    zip_url: str = ""
    size: int = 0
    sha256: str = ""       # vide si GitHub ne la donne pas

    @property
    def installable(self) -> bool:
        """Installable en un clic : version exe et zip publié."""
        return bool(self.zip_url) and core.IS_FROZEN


def find_update(current: str, fetch=None, timeout: float = 5.0) -> Optional[Update]:
    """Version plus récente publiée (avec son zip), sinon None. Hors ligne : None."""
    found = core.newer_release(current, fetch=_remember(fetch), timeout=timeout)
    if found is None:
        return None
    tag, url = found
    up = Update(tag, url)
    for a in (_last_release or {}).get("assets") or []:
        name = str(a.get("name", ""))
        if name.startswith(APP_NAME) and name.endswith(".zip"):
            up.zip_url = str(a.get("browser_download_url", ""))
            up.size = int(a.get("size") or 0)
            digest = str(a.get("digest") or "")
            up.sha256 = digest.split(":", 1)[1] if digest.startswith("sha256:") else ""
            break
    return up


_last_release: Optional[dict] = None


def _remember(fetch):
    """Garde la réponse de GitHub (liste des fichiers de la version) en plus du numéro."""
    def wrapped(timeout):
        global _last_release
        _last_release = (fetch or core._fetch_latest_release)(timeout)
        return _last_release
    return wrapped


def download(up: Update, dest: Path, progress: Optional[Callable[[int, int], None]] = None,
             opener=None) -> Path:
    """Télécharge le zip dans `dest` et vérifie taille + empreinte. Lève RuntimeError sinon."""
    import urllib.request
    dest.mkdir(parents=True, exist_ok=True)
    out = dest / f"{APP_NAME}-{up.tag}.zip"
    req = urllib.request.Request(up.zip_url, headers={"User-Agent": APP_NAME})
    h = hashlib.sha256()
    done = 0
    with (opener or urllib.request.urlopen)(req, timeout=30) as r, open(out, "wb") as f:
        while True:
            chunk = r.read(1 << 16)
            if not chunk:
                break
            f.write(chunk)
            h.update(chunk)
            done += len(chunk)
            if progress:
                progress(done, up.size)
    if up.size and done != up.size:
        raise RuntimeError(f"téléchargement incomplet ({done} octets sur {up.size})")
    if up.sha256 and h.hexdigest() != up.sha256.lower():
        raise RuntimeError("fichier téléchargé corrompu (empreinte SHA-256 différente)")
    return out


def unpack(zip_path: Path, dest: Path) -> Path:
    """Décompresse et retourne le dossier de l'outil (celui qui contient l'exe).
    Refuse un zip qui écrirait hors de `dest` ou qui ne contient pas l'outil."""
    dest = dest.resolve()
    with zipfile.ZipFile(zip_path) as z:
        for name in z.namelist():
            target = (dest / name).resolve()
            if dest != target and dest not in target.parents:
                raise RuntimeError(f"zip refusé (chemin suspect : {name})")
        z.extractall(dest)
    app = dest / APP_NAME
    if not (app / f"{APP_NAME}.exe").is_file() or not (app / "_internal").is_dir():
        raise RuntimeError("zip inattendu : DofusPriceHelper.exe ou _internal introuvable")
    return app


def _ps(s: str) -> str:
    """Chaîne PowerShell entre apostrophes (rien n'y est interprété)."""
    return "'" + str(s).replace("'", "''") + "'"


def installer_script(new_dir: Path, app_dir: Path, pid: int, work_dir: Path, log: Path,
                     relaunch: bool = True) -> str:
    """Script PowerShell : attend la fin de l'outil, remplace ses fichiers, relance."""
    app, new = Path(app_dir), Path(new_dir)
    internal, old = app / "_internal", app / "_internal.old"
    exe = app / f"{APP_NAME}.exe"
    return f"""$ErrorActionPreference = 'Stop'
$log = {_ps(log)}
function Note($m) {{ Add-Content -LiteralPath $log -Value ("$(Get-Date -Format s)  [MAJ] " + $m) -Encoding UTF8 }}
try {{ Wait-Process -Id {int(pid)} -Timeout 60 -ErrorAction SilentlyContinue }} catch {{}}
Start-Sleep -Milliseconds 500
$stage = 'internal'
try {{
    if (Test-Path -LiteralPath {_ps(old)}) {{ Remove-Item -LiteralPath {_ps(old)} -Recurse -Force }}
    if (Test-Path -LiteralPath {_ps(internal)}) {{ Rename-Item -LiteralPath {_ps(internal)} -NewName '_internal.old' }}
    Copy-Item -LiteralPath {_ps(new / "_internal")} -Destination {_ps(app)} -Recurse -Force
    $stage = 'files'
    Get-ChildItem -LiteralPath {_ps(new)} | Where-Object {{ $_.Name -ne '_internal' }} |
        Copy-Item -Destination {_ps(app)} -Recurse -Force
    Remove-Item -LiteralPath {_ps(old)} -Recurse -Force -ErrorAction SilentlyContinue
    Note 'installée'
}} catch {{
    Note ('échec (' + $stage + ') : ' + $_.Exception.Message)
    if ($stage -eq 'internal' -and (Test-Path -LiteralPath {_ps(old)})) {{
        Remove-Item -LiteralPath {_ps(internal)} -Recurse -Force -ErrorAction SilentlyContinue
        Rename-Item -LiteralPath {_ps(old)} -NewName '_internal' -ErrorAction SilentlyContinue
        Note 'ancienne version remise en place'
    }}
    Start-Process {_ps(core.RELEASES_URL)}
}}
{"Start-Process -FilePath " + _ps(exe) if relaunch else ""}
Remove-Item -LiteralPath {_ps(work_dir)} -Recurse -Force -ErrorAction SilentlyContinue
"""


def work_dir(new_dir: Path) -> Path:
    """Dossier temporaire de la mise à jour (…/dph-maj-xxx/nouveau/DofusPriceHelper)."""
    return Path(new_dir).parent.parent


def launch_installer(new_dir: Path, work_dir: Path) -> None:
    """Lance le script (détaché, sans fenêtre). L'appelant doit ensuite fermer l'outil."""
    app_dir = Path(sys.executable).parent
    core.LOG_DIR.mkdir(parents=True, exist_ok=True)
    script = work_dir / "installer.ps1"
    script.write_text(installer_script(new_dir, app_dir, os.getpid(), work_dir,
                                       core.LOG_DIR / "mise-a-jour.log"), encoding="utf-8-sig")
    flags = 0x00000008 | 0x00000200 | 0x08000000   # DETACHED, NEW_PROCESS_GROUP, NO_WINDOW
    subprocess.Popen(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-WindowStyle", "Hidden",
                      "-File", str(script)], creationflags=flags, close_fds=True)


def prepare(up: Update, progress=None) -> Path:
    """Téléchargement + vérification + décompression. Retourne le dossier de la nouvelle
    version, prêt à copier (dossier de travail = work_dir(retour))."""
    work = Path(tempfile.mkdtemp(prefix="dph-maj-"))
    try:
        z = download(up, work, progress)
        new = unpack(z, work / "nouveau")
        z.unlink(missing_ok=True)
        return new
    except Exception:
        shutil.rmtree(work, ignore_errors=True)
        raise


# --------------------------------------------------------------------------
# Rapport de problème
# --------------------------------------------------------------------------
def hdv_box(cfg: core.Config, margin: int = 40) -> Optional[core.Region]:
    """Rectangle qui englobe toutes les zones calibrées (= l'HDV), avec une marge."""
    xs, ys = [], []
    for f in core.REGION_FIELDS:
        r = getattr(cfg, f)
        if r:
            xs += [r[0], r[0] + r[2]]
            ys += [r[1], r[1] + r[3]]
    for f in core.POINT_FIELDS:
        p = getattr(cfg, f)
        if p:
            xs.append(p[0])
            ys.append(p[1])
    if not xs:
        return None
    x0, y0 = min(xs) - margin, min(ys) - margin
    return x0, y0, max(xs) + margin - x0, max(ys) + margin - y0


def system_info(cfg: core.Config) -> str:
    lines = [f"Dofus Price Helper {core.app_version()}",
             f"Date : {time.strftime('%Y-%m-%d %H:%M:%S')}",
             f"Windows : {platform.platform()}",
             f"Python : {sys.version.split()[0]} ({'exe' if core.IS_FROZEN else 'code source'})",
             f"OCR : {core.TESSERACT_USED or '?'}",
             f"Profil : {cfg.profile} (profils : {', '.join(cfg.profile_names())})"]
    try:
        import mss
        with mss.mss() as s:
            lines.append("Écrans : " + " | ".join(f"{m['width']}x{m['height']} en ({m['left']},{m['top']})"
                                                for m in s.monitors[1:]))
    except Exception as e:
        lines.append(f"Écrans : ? ({e})")
    try:
        lines.append(f"Chiffres appris : {len(core.digit_reader().known())}/10")
    except Exception:
        pass
    lines.append("Zones calibrées : " + ", ".join(f for f in core.REGION_FIELDS + core.POINT_FIELDS
                                                 if getattr(cfg, f)))
    lines.append("")
    lines.append("Non inclus (vie privée) : historique des ventes, tes prix mémorisés.")
    return "\n".join(lines) + "\n"


def make_report(cfg: core.Config, dest: Path = REPORT_DIR, screenshot: bool = True) -> Path:
    """Crée le zip du rapport et retourne son chemin."""
    dest.mkdir(parents=True, exist_ok=True)
    out = dest / f"rapport-{time.strftime('%Y%m%d-%H%M%S')}.zip"
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("infos.txt", system_info(cfg))
        if core.CONFIG_PATH.exists():
            z.write(core.CONFIG_PATH, "reglages.json")
        else:
            z.writestr("reglages.json", json.dumps({k.upper(): getattr(cfg, k) for k in cfg.__dataclass_fields__},
                                                   indent=2, ensure_ascii=False))
        for f in sorted(core.LOG_DIR.glob("*.log*")):
            z.write(f, f"journaux/{f.name}")
        caps = sorted(core.DEBUG_DIR.glob("*.png"), key=lambda p: p.stat().st_mtime)[-20:] \
            if core.DEBUG_DIR.exists() else []
        for f in caps:
            z.write(f, f"captures/{f.name}")
        anchor = core.anchor_path(cfg)
        if anchor.exists():
            z.write(anchor, "repere.png")
        if screenshot:
            box = hdv_box(cfg)
            if box is not None:
                try:
                    import cv2
                    ok, png = cv2.imencode(".png", core.grab_screen(box))
                    if ok:
                        z.writestr("hdv.png", png.tobytes())
                except Exception as e:
                    z.writestr("hdv_erreur.txt", str(e))
    return out


def reveal(path: Path) -> None:
    """Ouvre l'Explorateur sur le fichier (sélectionné)."""
    try:
        subprocess.Popen(["explorer", "/select,", str(path)])
    except OSError:
        os.startfile(path.parent)   # type: ignore[attr-defined]


def report_files(path: Path) -> List[str]:
    with zipfile.ZipFile(path) as z:
        return z.namelist()
