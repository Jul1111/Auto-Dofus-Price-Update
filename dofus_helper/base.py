"""Socle : dossiers, version, nouvelle version publiée, fichier journal, DPI."""
from __future__ import annotations

import json
import os
import re
import sys
import threading
from pathlib import Path
from typing import Optional, Tuple


IS_FROZEN = bool(getattr(sys, "frozen", False))   # lancé depuis l'exe (PyInstaller)
# Fichiers livrés avec l'outil (Tesseract inclus, version) : dossier de l'exe, sinon du projet.
APP_DIR = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[1]))


def _data_dir() -> Path:
    """Où ranger config, calibration, chiffres appris, historique.
    Depuis le code source : à côté du script (comme avant). Depuis l'exe : %APPDATA%, pour que
    les réglages survivent aux mises à jour (une nouvelle version = un nouveau dossier)."""
    if not IS_FROZEN:
        return Path(__file__).resolve().parents[1]     # dossier du projet
    d = Path(os.environ.get("APPDATA") or Path.home()) / "Dofus Price Helper"
    d.mkdir(parents=True, exist_ok=True)
    return d


BASE_DIR = _data_dir()


def app_version() -> str:
    """Version de l'exe (fichier version.txt ajouté à la construction), sinon « dev »."""
    try:
        return (APP_DIR / "version.txt").read_text(encoding="utf-8").strip() or "dev"
    except OSError:
        return "dev"


# --------------------------------------------------------------------------
# Nouvelle version publiée ? (GitHub Releases)
# --------------------------------------------------------------------------
GITHUB_REPO = "Jul1111/Auto-Dofus-Price-Update"
RELEASES_URL = f"https://github.com/{GITHUB_REPO}/releases/latest"


def parse_version(v: str) -> Optional[Tuple[int, int, int]]:
    """« v1.2.3 » -> (1, 2, 3). None pour « dev », « dev-abc1234 »…"""
    m = re.fullmatch(r"v?(\d+)\.(\d+)\.(\d+)", (v or "").strip())
    return (int(m.group(1)), int(m.group(2)), int(m.group(3))) if m else None


def _fetch_latest_release(timeout: float) -> dict:
    import urllib.request
    req = urllib.request.Request(f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest",
                                 headers={"Accept": "application/vnd.github+json",
                                          "User-Agent": "DofusPriceHelper"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def newer_release(current: str, fetch=None, timeout: float = 5.0) -> Optional[Tuple[str, str]]:
    """(tag, lien) si une version plus récente que `current` est publiée, sinon None.
    Version « dev » (code source) : pas de vérification. Hors ligne : None, sans erreur."""
    cur = parse_version(current)
    if cur is None:
        return None
    try:
        data = (fetch or _fetch_latest_release)(timeout)
        tag = str(data.get("tag_name", ""))
        latest = parse_version(tag)
    except Exception:
        return None
    if latest and latest > cur:
        return tag, str(data.get("html_url") or RELEASES_URL)
    return None


# --------------------------------------------------------------------------
# Fichier journal : ce que montre le Journal + messages du moteur + plantages
# (dans l'exe il n'y a pas de console : sans ce fichier, tout cela était perdu)
# --------------------------------------------------------------------------
LOG_DIR = BASE_DIR / "journaux"
LOG_MAX_BYTES = 1_000_000           # journal.log, puis journal.log.1 … .3 (4 Mo au plus)
_file_log = None


class _TeeStream:
    """Copie ce qui est écrit sur stdout / stderr (print du moteur) dans le fichier journal."""

    def __init__(self, original, write_line):
        self.original, self.write_line, self._buf = original, write_line, ""

    def write(self, text):
        if self.original is not None:
            try:
                self.original.write(text)
            except Exception:
                pass
        self._buf += text
        while "\n" in self._buf:
            line, self._buf = self._buf.split("\n", 1)
            if line.strip():
                self.write_line(line)
        return len(text)

    def flush(self):
        if self.original is not None:
            try:
                self.original.flush()
            except Exception:
                pass

    def isatty(self):
        return False


def setup_file_log(capture_std: bool = True) -> Path:
    """Active le fichier journal (une seule fois). Retourne son chemin."""
    global _file_log
    import logging
    import logging.handlers
    path = LOG_DIR / "journal.log"
    if _file_log is not None:
        return path
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    handler = logging.handlers.RotatingFileHandler(path, maxBytes=LOG_MAX_BYTES, backupCount=3,
                                                   encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s  %(message)s", "%Y-%m-%d %H:%M:%S"))
    lg = logging.getLogger("dofus_price_helper")
    lg.setLevel(logging.INFO)
    lg.propagate = False
    lg.addHandler(handler)
    _file_log = lg
    if capture_std:
        sys.stdout = _TeeStream(sys.stdout, lg.info)
        sys.stderr = _TeeStream(sys.stderr, lg.error)

        def hook(exc_type, exc, tb):
            import traceback
            lg.error("Erreur non gérée :\n" + "".join(traceback.format_exception(exc_type, exc, tb)))
        sys.excepthook = hook
        threading.excepthook = lambda a: hook(a.exc_type, a.exc_value, a.exc_traceback)
    lg.info(f"===== Démarrage Dofus Price Helper {app_version()} | Python {sys.version.split()[0]} "
            f"| {sys.platform} =====")
    return path


def log_line(msg: str, level: str = "INFO") -> None:
    """Une ligne dans le fichier journal (rien si le fichier journal n'est pas activé)."""
    if _file_log is not None:
        try:
            (_file_log.error if level == "ERROR" else _file_log.warning if level == "WARN"
             else _file_log.info)(msg)
        except Exception:
            pass
CONFIG_PATH = BASE_DIR / "dofus_price_helper_config.json"
HISTORY_PATH = BASE_DIR / "dofus_price_history.csv"
DIGITS_PATH = BASE_DIR / "digit_templates.npz"   # modèles de chiffres appris (lecture rapide)
ANCHOR_PATH = BASE_DIR / "hdv_anchor.png"        # image du titre « Hôtel de vente » (repère)
HISTORY_HEADER = ["ts", "datetime", "action", "lot", "selected_qty", "read_price", "confidence",
                  "new_price", "status", "mode", "value", "rounding", "item"]
CONFIG_VERSION = 7

IS_WINDOWS = sys.platform == "win32"


# --------------------------------------------------------------------------
# DPI : sans ça, pyautogui et mss n'ont pas le même repère sous Windows
# quand l'affichage est à 125 % / 150 %. Doit être appelé avant Tk.
# --------------------------------------------------------------------------
def enable_dpi_awareness() -> None:
    if not IS_WINDOWS:
        return
    import ctypes
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)  # per-monitor
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass


enable_dpi_awareness()

