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
PARTOUT où X est utilisé, comme quand tout tenait dans un seul fichier (voir _gather.py).

Les dépendances lourdes (mss, pytesseract, keyboard, pyautogui, pyperclip)
sont importées à la demande : les fonctions pures restent testables partout.
"""
from __future__ import annotations

from . import (anchor, base, config, engine, game, history, hotkeys, my_prices, ocr, pricing,
               sounds)
from ._gather import gather

# Ordre des dépendances : un module n'importe que ceux d'avant.
gather(__name__, (base, pricing, ocr, anchor, config, game, hotkeys, sounds, history, my_prices, engine))
