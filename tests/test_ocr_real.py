"""OCR de bout en bout avec le vrai Tesseract sur une capture réelle de l'HDV
(ignoré si Tesseract n'est pas installé)."""
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from dofus_helper import core  # noqa: E402

pytest.importorskip("pytesseract")
# même recherche que l'outil : PATH, puis le dossier d'installation par défaut (souvent hors PATH)
if core.setup_tesseract(core.Config()) is not None:
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


# Les deux captures ont le « 1 » COUPÉ par le bas de la zone. Tesseract 5.5 lit encore
# celle du menu grisé ; sur l'autre il ne lit rien. « Rien » est le résultat sûr (quantité
# illisible : pas de vente) ; lire un AUTRE nombre ne doit jamais arriver.
@pytest.mark.parametrize("name,allowed", [("quantite_grisee.png", (1,)), ("quantite_vente.png", (1, None))])
def test_reads_quantity_with_dropdown_frame(monkeypatch, name, allowed):
    # zone qui inclut le cadre gris du menu : Otsu séparait le cadre du fond, le « 1 » disparaissait
    w, h = _patch_fixture(monkeypatch, name)
    q = core.preprocess(core.grab_screen((0, 0, w, h)), 2)
    import pytesseract
    d = pytesseract.image_to_data(q, config=core.OCR_CONFIG, output_type=pytesseract.Output.DICT)
    assert core.parse_number(d, (0, q.shape[0])).value in allowed


@pytest.mark.parametrize("name,cut", [
    ("quantite_grisee.png", True), ("quantite_vente.png", True),       # « 1 » coupé par le bas
    ("compteur_bois.png", False), ("compteur_scalp.png", False),
    ("prixmoyen_bois.png", False), ("prixmoyen_scalp.png", False), ("tonprix_laine.png", False)])
def test_detects_text_cut_by_zone(name, cut):
    import cv2
    img = cv2.imread(str(Path(__file__).parent / "fixtures" / name))
    assert core.text_touches_edge(img) is cut


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


# --- Lecture rapide des chiffres (apprise sur Tesseract)
PANELS = {
    "hdv_mesventes.png": (dict(table_region=[30, 462, 180, 128], qty_region=[16, 229, 90, 22],
                               avg_region=[14, 331, 60, 20], mine_region=[16, 172, 125, 22]),
                          {1: 760, 10: 6999, 100: 83199, 1000: 844000}, 1, 1189, 774),
    "hdv_mesventes_celeste.png": (dict(table_region=[16, 466, 215, 138], qty_region=[20, 238, 110, 24],
                                       avg_region=[18, 342, 60, 20], mine_region=[20, 182, 130, 26]),
                                  {1: 149, 10: 1499, 100: 22294}, 10, 282, 1662),
    "hdv_mesventes_cuir.png": (dict(table_region=[38, 466, 215, 138], qty_region=[42, 238, 90, 24],
                                    avg_region=[40, 342, 60, 20], mine_region=[40, 180, 130, 26]),
                               {1: 49, 10: 738, 100: 8989, 1000: 89999}, 1, 81, 49),
    "hdv_mesventes_cuivre.png": (dict(table_region=[32, 475, 216, 138], qty_region=[42, 243, 108, 23],
                                      avg_region=[36, 342, 60, 22], mine_region=[40, 169, 667, 513]),
                                 {1: 76, 10: 629, 100: 4367, 1000: 43677}, 1, 51, 76),
}


def _read_panel(monkeypatch, name):
    _patch_fixture(monkeypatch, name)
    regions, *_ = PANELS[name]
    return core.read_screen(core.Config(**regions), with_mine=True)


def _train_extra(monkeypatch):
    # tableaux de l'onglet vente (Bois 1789/17875, Corne 28570) : apportent des « 5 »
    for name, p1, p2 in (("hdv_vente.png", (48, 242), (192, 380)), ("hdv_corne.png", (50, 242), (195, 380))):
        _patch_fixture(monkeypatch, name)
        core.read_screen(core.Config(table_region=list(core.rect_from_points(p1, p2))))


def test_fast_digits_learn_then_read(monkeypatch):
    # 1ers passages : Tesseract (et apprentissage) ; ensuite lecture rapide, mêmes valeurs
    for _ in range(2):
        _train_extra(monkeypatch)
        for name in PANELS:
            assert _read_panel(monkeypatch, name).engine == "tesseract" or core.digit_reader().ready
    assert core.digit_reader().ready
    fast = 0
    for name, (_, table, qty, avg, mine) in PANELS.items():
        sr = _read_panel(monkeypatch, name)
        fast += sr.engine == "chiffres"
        assert (sr.values, sr.selected, sr.avg, sr.mine_r.value) == (table, qty, avg, mine), name
    # Vitesse, pas justesse : ce qui est appris dépend des confiances de Tesseract (version).
    # Avec Tesseract 5.5, 2 chiffres de « Laine Céleste » scorent 0,79 (< 0,80) -> repli
    # Tesseract pour cette capture, valeurs toujours exactes (vérifiées ci-dessus).
    assert fast >= len(PANELS) - 1


def test_fast_digits_never_wrong_on_unseen_panel(monkeypatch):
    # appris sur 3 captures, testé sur la 4e : lecture rapide OU repli Tesseract, jamais faux
    names = list(PANELS)
    for held_out in names:
        monkeypatch.setattr(core, "_digits", core.digit_reader().__class__(None))
        for _ in range(2):
            _train_extra(monkeypatch)
            for name in names:
                if name != held_out:
                    _read_panel(monkeypatch, name)
        _, table, qty, avg, mine = PANELS[held_out]
        sr = _read_panel(monkeypatch, held_out)
        assert (sr.values, sr.selected, sr.avg, sr.mine_r.value) == (table, qty, avg, mine), held_out


NAME_FIXTURES = ["nom_b5958d42.png", "nom_fd90eefb.png", "nom_660bbef6.png", "nom_5bd9b7bc.png",
                 "nom_33bea070.png", "nom_7d72b9f1.png", "nom_b75f7ca5.png"]


def test_item_key_on_real_names():
    # 7 noms d'objets réels : une empreinte chacun, toutes différentes, stables
    import cv2
    imgs = [cv2.imread(str(Path(__file__).parent / "fixtures" / f)) for f in NAME_FIXTURES]
    keys = [core.item_key(i) for i in imgs]
    assert None not in keys and len(set(keys)) == len(keys)
    assert keys == [core.item_key(i.copy()) for i in imgs]


@pytest.mark.parametrize("fixture,mode", [("boutons_mesventes.png", "relist"), ("boutons_vente.png", "sell")])
def test_detect_panel_mode(monkeypatch, fixture, mode):
    # ligne des boutons : « Retirer | Modifier » (une de tes ventes) ou « Mettre en vente »
    _patch_fixture(monkeypatch, fixture)
    assert core.detect_panel(core.Config(modify_button=[165, 20])) == mode


def test_reads_field_with_text_caret(monkeypatch):
    # « 496| » : le curseur de saisie collé au 6 faisait lire 49 / 494 -> vente bloquée à tort
    _patch_fixture(monkeypatch, "champ_curseur.png")
    cfg = core.Config(price_field=[145, 35])
    assert core.read_mine(cfg).value == 496
    assert core.field_check(cfg, 496)[0]


def test_second_readings_still_read_real_captures(monkeypatch):
    # 2es lectures (image agrandie autrement) : elles doivent lire juste, sinon chaque
    # contrôle échouerait et les lignes resteraient « suspectes »
    _patch_fixture(monkeypatch, "hdv_mesventes.png")
    cfg = core.Config(table_region=[30, 462, 180, 128], qty_region=[16, 229, 90, 22],
                      mine_region=[16, 172, 125, 22], fast_digits=False)
    sr = core.table_second_read(cfg, "tesseract")
    assert sr.values == {1: 760, 10: 6999, 100: 83199, 1000: 844000} and sr.selected == 1
    assert core.mine_second_opinions(cfg)[0].value == 774


def test_second_opinion_reads_field_with_caret(monkeypatch):
    _patch_fixture(monkeypatch, "champ_curseur.png")
    assert core.mine_second_opinions(core.Config(price_field=[145, 35]))[0].value == 496


def test_second_opinion_reads_highlighted_field(monkeypatch):
    w, h = _patch_fixture(monkeypatch, "tonprix_laine.png")
    assert core.mine_second_opinions(core.Config(mine_region=[0, 0, w, h]))[0].value == 774
