"""
Dofus Price Helper — moteur partagé (GUI + CLI), vu comme un seul module
-------------------------------------------------------------------------
Lecture de l'Hôtel de Vente (onglet Vente) :
- Tableau « ACTUELLEMENT EN VENTE » : colonnes Lot + Prix, lues en entier.
  Chaque ligne est associée à son lot (1 / 10 / 100 / 1000) grâce à la colonne Lot,
  donc une ligne absente (personne ne vend ce lot) ne décale rien.
- Menu « Quantité » : on lit la quantité sélectionnée pour ne JAMAIS coller
  le prix d'un lot dans une autre quantité.
- Un seul appel Tesseract pour le tableau + la quantité.

Saisie : clic sur « Prix du lot » (option), vidage du champ (le jeu le pré-remplit),
collage Ctrl+V, puis option « Mettre en vente » (clic sur le bouton, sinon Entrée).

Le code est rangé par thème dans ce dossier (base, pricing, ocr, anchor, config, game,
hotkeys, sounds, history, my_prices, engine). Ce module les rassemble : l'interface, la CLI
et les tests écrivent `core.X` sans savoir où X est rangé.

Remplacer `core.X` (tests : monkeypatch.setattr(core, "grab_screen", ...)) le remplace
PARTOUT où X est utilisé, comme quand tout tenait dans un seul fichier.

Les dépendances lourdes (mss, pytesseract, keyboard, pyautogui, pyperclip)
sont importées à la demande : les fonctions pures restent testables partout.
"""
from __future__ import annotations

import sys
import types

from . import (anchor, base, config, engine, game, history, hotkeys, my_prices, ocr, pricing,
               sounds)

# Ordre des dépendances : un module n'importe que ceux d'avant. Le 1er qui connaît un nom
# est donc celui qui le définit (les suivants n'en ont qu'une copie importée).
MODULES = (base, pricing, ocr, anchor, config, game, hotkeys, sounds, history, my_prices, engine)


def _holders(name):
    return [m for m in MODULES if name in m.__dict__]


def _forward(name):
    """Accès à `core.<name>` : lu dans le module qui le définit, remplacé partout. Une vraie
    propriété (pas __getattr__) : monkeypatch la voit et remet l'ancienne valeur ensuite."""
    def get(self):
        return _holders(name)[0].__dict__[name]

    def set(self, value):
        for m in _holders(name):       # le module qui le définit ET ceux qui l'importent
            setattr(m, name, value)
    return property(get, set)


class _Core(types.ModuleType):
    def __getattr__(self, name):       # nom apparu après le chargement (rare)
        holders = _holders(name)
        if holders:
            return holders[0].__dict__[name]
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

    def __dir__(self):
        names = set(super().__dir__())
        for m in MODULES:
            names.update(n for n in m.__dict__ if not n.startswith("__"))
        return sorted(names)


for _m in MODULES:
    for _name in list(_m.__dict__):
        if not _name.startswith("__") and _name not in globals() and not hasattr(_Core, _name):
            setattr(_Core, _name, _forward(_name))
del _m, _name

sys.modules[__name__].__class__ = _Core
