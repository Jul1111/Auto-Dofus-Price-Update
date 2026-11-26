import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import dofus_core as core  # noqa: E402
from dofus_digits import DigitReader  # noqa: E402


@pytest.fixture(autouse=True)
def fresh_digits(monkeypatch):
    """Chaque test part de modèles de chiffres vides, en mémoire (aucun fichier écrit)."""
    monkeypatch.setattr(core, "_digits", DigitReader(None))
    monkeypatch.setattr(core, "_fast_count", 0)


@pytest.fixture(autouse=True)
def no_my_prices_file(monkeypatch, tmp_path):
    """« Tes prix » écrits dans un dossier temporaire, jamais à côté du projet."""
    monkeypatch.setattr(core, "MY_PRICES_PATH", tmp_path / "my_prices.json")
