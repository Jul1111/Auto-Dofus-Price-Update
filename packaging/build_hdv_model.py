"""Génère le modèle de l'HDV (dossier modele_hdv/) utilisé par la calibration automatique.

Source : une capture de l'HDV (onglet Vente, une de tes ventes sélectionnée) prise à
2560 x 1440, échelle d'interface 90 %, Dofus 3 en français. Les zones viennent d'une
calibration manuelle validée en jeu sur ce même écran ; elles sont exprimées par rapport au
coin haut-gauche du texte « Hôtel de vente » (le repère), à l'échelle de cette capture.

    python packaging/build_hdv_model.py

À relancer seulement si l'interface de l'HDV change (nouvelle version du jeu).
"""
import json
import sys
from pathlib import Path

import cv2

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "tests" / "fixtures" / "hdv_echelles" / "2560x1440_90.png"
OUT = ROOT / "modele_hdv"

# Coin haut-gauche du texte « Hôtel de vente » dans la capture source.
TITLE = (303, 18)

# Bandeau du haut (icône, titre, onglets Achat / Vente) : sert à trouver l'HDV et son échelle.
HEADER = (270, 8, 190, 66)

# Textes fixes (coordonnées dans la capture) : recalent finement les zones voisines.
# search = marge de recherche (px à l'échelle 1) en x et en y.
LANDMARKS = {
    "prix_du_lot": ((23, 162, 69, 16), (10, 10)),
    "quantite": ((23, 218, 60, 17), (10, 10)),
    "prix_moyen": ((23, 323, 75, 14), (10, 10)),
    "actuellement": ((23, 421, 149, 14), (10, 10)),
    "nom": ((296, 142, 33, 15), (10, 10)),
    # « 113/210 lots en vente » : la largeur du nombre change -> on ne garde que la hauteur
    "lots_en_vente": ((300, 688, 85, 15), (80, 10)),
}

# Zones et points (coordonnées dans la capture) + repère utilisé pour x et pour y.
ZONES = {
    "anchor_region": ([303, 18, 149, 16], None, None),
    "name_region": ([85, 100, 131, 32], "prix_du_lot", "prix_du_lot"),
    "price_field": ([79, 195], "prix_du_lot", "prix_du_lot"),
    "qty_region": ([30, 243, 81, 17], "quantite", "quantite"),
    "avg_region": ([25, 346, 80, 18], "prix_moyen", "prix_moyen"),
    "sell_button": ([65, 383], "prix_moyen", "prix_moyen"),
    "modify_button": ([178, 387], "prix_moyen", "prix_moyen"),
    "table_region": ([62, 480, 155, 125], "actuellement", "actuellement"),
    "relist_row": ([499, 190], "nom", "nom"),
    "count_region": ([247, 687, 144, 18], "nom", "lots_en_vente"),
}
ROW_STEP = 49.6   # hauteur d'une ligne de « mes ventes » (mesurée sur la capture)


def rel(x, y):
    return [x - TITLE[0], y - TITLE[1]]


def main() -> int:
    img = cv2.imread(str(SRC), cv2.IMREAD_GRAYSCALE)
    if img is None:
        sys.exit(f"capture introuvable : {SRC}")
    OUT.mkdir(exist_ok=True)
    x, y, w, h = HEADER
    cv2.imwrite(str(OUT / "entete.png"), img[y:y + h, x:x + w])
    model = {
        "info": "Dofus 3, interface en français. Capture 2560x1440, interface 90 %.",
        "header": {"file": "entete.png", "at": rel(x, y)},
        "row_step": ROW_STEP,
        "landmarks": {},
        "zones": {},
    }
    for name, ((x, y, w, h), search) in LANDMARKS.items():
        cv2.imwrite(str(OUT / f"{name}.png"), img[y:y + h, x:x + w])
        model["landmarks"][name] = {"file": f"{name}.png", "at": rel(x, y), "search": list(search)}
    for name, (value, lx, ly) in ZONES.items():
        model["zones"][name] = {"value": rel(*value[:2]) + list(value[2:]), "x": lx, "y": ly}
    (OUT / "modele.json").write_text(json.dumps(model, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"OK : {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
