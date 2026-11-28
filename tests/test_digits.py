"""Lecture rapide des chiffres : un modèle mal appris ne doit pas fausser les lectures."""
import sys
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from dofus_helper.digits import DigitReader  # noqa: E402

VARIANTS = [(1.0, 2), (1.1, 2), (1.2, 3), (1.3, 3)]


def render(text, scale=1.2, thick=3):
    """Nombre en noir sur blanc, binarisé comme pour Tesseract."""
    img = np.full((60, 40 + 34 * len(text)), 255, np.uint8)
    cv2.putText(img, text, (10, 45), cv2.FONT_HERSHEY_SIMPLEX, scale, 0, thick)
    return np.where(img < 128, 0, 255).astype(np.uint8)


def glyph(d, scale, thick):
    b = render(str(d), scale, thick) < 128
    ys, xs = np.where(b)
    return b[ys.min():ys.max() + 1, xs.min():xs.max() + 1]


def trained(bad_five_as_eight=False):
    r = DigitReader(None)
    for d in range(10):
        for sc, th in VARIANTS:
            r.add(d, glyph(d, sc, th), sure=True)
    if bad_five_as_eight:       # Tesseract a lu « 8 » un 5 : appris comme 8
        r.samples[8].append(__import__("dofus_helper.digits", fromlist=["x"]).normalize(glyph(5, 1.15, 3)))
    return r


def text_of(r, img):
    data = r.read_data(img)
    return "".join(data["text"]) if data else None


def test_mislearned_sample_breaks_reading_then_correct_fixes_it():
    r = trained(bad_five_as_eight=True)
    img = render("4725", 1.15, 3)
    assert text_of(r, img) != "4725"              # le faux 8 gagne (ou doute)
    assert r.correct(img, "4725") >= 1
    assert text_of(r, img) == "4725"
    assert text_of(r, render("4728", 1.15, 3)) == "4728"   # les vrais 8 restent


def test_purge_on_load_removes_only_the_mislabeled_sample(tmp_path):
    r = trained(bad_five_as_eight=True)
    r.path = tmp_path / "d.npz"
    r.save()
    counts = {d: len(v) for d, v in r.samples.items()}
    again = DigitReader(tmp_path / "d.npz")
    assert len(again.samples[8]) == counts[8] - 1
    assert all(len(again.samples[d]) == counts[d] for d in range(10) if d != 8)


def test_learning_refuses_a_digit_that_looks_like_another():
    r = trained()
    n8 = len(r.samples[8])
    r.add(8, glyph(5, 1.15, 3))                   # Tesseract : « 8 » ; la forme est un 5
    assert len(r.samples[8]) == n8
    r.add(8, glyph(8, 1.15, 3))                   # un vrai 8 : appris
    assert len(r.samples[8]) == n8 + 1
