"""OCR de bout en bout avec le vrai Tesseract sur une capture réelle de l'HDV
(ignoré si Tesseract n'est pas installé)."""
import shutil
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import dofus_core as core  # noqa: E402

pytest.importorskip("pytesseract")
if not shutil.which("tesseract"):
    pytest.skip("tesseract absent", allow_module_level=True)

from PIL import Image  # noqa: E402

FIXTURE = Path(__file__).parent / "fixtures" / "hdv_vente.png"
# Capture : panneau gauche de l'onglet Vente (Bois de Châtaignier).
# Tableau : lot 1 = 35, 10 = 184, 100 = 1 789, 1000 = 17 875. Quantité affichée : 1.
EXPECTED = {1: 35, 10: 184, 100: 1789, 1000: 17875}
QTY = ((18, 12), (100, 36))


@pytest.fixture
def screen(monkeypatch):
    src = np.array(Image.open(FIXTURE).convert("RGB"))[:, :, ::-1]
    monkeypatch.setattr(core, "grab_screen", lambda r: src[r[1]:r[1] + r[3], r[0]:r[0] + r[2]].copy())
    assert core.setup_tesseract(core.Config()) is None


@pytest.mark.parametrize("p1,p2", [
    ((48, 242), (192, 380)),   # précis : colonnes Lot + Prix, sans icônes
    ((48, 242), (208, 380)),   # inclut les icônes kamas
    ((10, 242), (192, 380)),   # inclut les icônes objet
    ((8, 236), (215, 384)),    # large partout
    ((48, 230), (192, 372)),   # décalé vers le haut
])
def test_reads_real_hdv_table(screen, p1, p2):
    cfg = core.Config(table_region=list(core.rect_from_points(p1, p2)),
                      qty_region=list(core.rect_from_points(*QTY)))
    sr = core.read_screen(cfg)
    assert sr.values == EXPECTED
    assert sr.selected == 1
    assert all(r.confidence >= cfg.min_confidence for r in sr.prices.values())


def test_missing_row_does_not_shift(screen):
    # tableau sans la ligne 1000 : les 3 autres restent bien associées
    cfg = core.Config(table_region=list(core.rect_from_points((48, 242), (192, 345))))
    assert core.read_screen(cfg).values == {1: 35, 10: 184, 100: 1789}


FIXTURE2 = Path(__file__).parent / "fixtures" / "hdv_corne.png"
# Corne de Boufton : icône bleue à gauche des lots, qui masquait le « 1 » avant correction.


@pytest.mark.parametrize("p1,p2", [((50, 242), (195, 380)), ((10, 235), (227, 385)), ((5, 230), (234, 389))])
def test_reads_table_with_item_icons(monkeypatch, p1, p2):
    src = np.array(Image.open(FIXTURE2).convert("RGB"))[:, :, ::-1]
    monkeypatch.setattr(core, "grab_screen", lambda r: src[r[1]:r[1] + r[3], r[0]:r[0] + r[2]].copy())
    assert core.setup_tesseract(core.Config()) is None
    cfg = core.Config(table_region=list(core.rect_from_points(p1, p2)))
    assert core.read_screen(cfg).values == {1: 27, 10: 248, 100: 2390, 1000: 28570}


# --- Compteur « x/100 lots en vente » et « Prix moyen » (captures réelles, zone = image entière)
SMALL = {
    "bois": ((12, 98), 16), "scalp": ((12, 100), 967),
    "cuir": ((17, 100), 81), "corne": ((21, 100), 18),
}


def _patch_fixture(monkeypatch, name):
    src = np.array(Image.open(Path(__file__).parent / "fixtures" / name).convert("RGB"))[:, :, ::-1]
    monkeypatch.setattr(core, "grab_screen", lambda r: src[r[1]:r[1] + r[3], r[0]:r[0] + r[2]].copy())
    assert core.setup_tesseract(core.Config()) is None
    return src.shape[1], src.shape[0]


@pytest.mark.parametrize("item", SMALL)
def test_reads_real_counter(monkeypatch, item):
    w, h = _patch_fixture(monkeypatch, f"compteur_{item}.png")
    cfg = core.Config(count_region=[0, 0, w, h])
    assert core.read_counter(cfg) == SMALL[item][0]


@pytest.mark.parametrize("item", SMALL)
def test_reads_real_avg_price(monkeypatch, item):
    w, h = _patch_fixture(monkeypatch, f"prixmoyen_{item}.png")
    # le tableau est obligatoire : on réutilise la même petite image (aucun lot valide dedans)
    cfg = core.Config(table_region=[0, 0, w, h], avg_region=[0, 0, w, h])
    assert core.read_screen(cfg).avg == SMALL[item][1]


def test_reads_real_own_price_highlighted(monkeypatch):
    # « Prix du lot » d'une vente sélectionnée : 774 surligné en bleu
    w, h = _patch_fixture(monkeypatch, "tonprix_laine.png")
    r = core.read_mine(core.Config(mine_region=[0, 0, w, h]))
    assert r.value == 774 and r.confidence >= 60


def test_reads_real_my_sales_panel(monkeypatch):
    # Onglet « mes ventes » complet : tableau, quantité, prix moyen, ton prix, compteur
    _patch_fixture(monkeypatch, "hdv_mesventes.png")
    cfg = core.Config(table_region=[30, 462, 180, 128], qty_region=[16, 229, 90, 22],
                      avg_region=[14, 331, 60, 20], mine_region=[16, 172, 125, 22],
                      count_region=[238, 673, 135, 20])
    sr = core.read_screen(cfg)
    assert sr.values == {1: 760, 10: 6999, 100: 83199, 1000: 844000}
    assert sr.selected == 1 and sr.avg == 1189
    assert core.read_mine(cfg).value == 774
    assert core.read_counter(cfg) == (51, 104)


@pytest.mark.parametrize("name", ["quantite_grisee.png", "quantite_vente.png"])
def test_reads_quantity_with_dropdown_frame(monkeypatch, name):
    # zone qui inclut le cadre gris du menu : Otsu séparait le cadre du fond, le « 1 » disparaissait
    w, h = _patch_fixture(monkeypatch, name)
    q = core.preprocess(core.grab_screen((0, 0, w, h)), 2)
    import pytesseract
    d = pytesseract.image_to_data(q, config=core.OCR_CONFIG, output_type=pytesseract.Output.DICT)
    assert core.parse_number(d, (0, q.shape[0])).value == 1


def test_reads_own_price_in_same_ocr_call(monkeypatch):
    # F3 / Ctrl+F3 : ton prix lu dans le MÊME appel Tesseract que le tableau (plus rapide)
    _patch_fixture(monkeypatch, "hdv_mesventes.png")
    cfg = core.Config(table_region=[30, 462, 180, 128], qty_region=[16, 229, 90, 22],
                      avg_region=[14, 331, 60, 20], mine_region=[16, 172, 125, 22])
    sr = core.read_screen(cfg, with_mine=True)
    assert sr.mine_r.value == 774 and sr.selected == 1 and sr.avg == 1189 and sr.values[1] == 760


def test_reads_table_with_pale_item_icons(monkeypatch):
    # Laine Céleste : icônes blanches (pas assez colorées pour le masque) -> lots perdus avant
    w, h = _patch_fixture(monkeypatch, "tableau_laine_celeste.png")
    sr = core.read_screen(core.Config(table_region=[0, 0, w, h]))
    assert sr.values == {1: 149, 10: 1499, 100: 22294}
