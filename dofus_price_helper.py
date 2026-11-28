#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Dofus Price Helper — lance l'interface graphique (code dans dofus_helper/gui/)
------------------------------------------------------------------------------
Raccourcis par défaut (modifiables dans la config, clé HOTKEYS) :
  F1                  vendre à la quantité affichée dans le jeu (lit le tableau + la quantité)
  F2                  tout vendre : remet en vente au même prix tant que la quantité et ton prix
                      en tête du tableau ne changent pas (stock épuisé, autre objet, concurrent)
  F4                  optimiser : meilleur prix unitaire (demande de changer la quantité si besoin)
  F3                  mes ventes : remet la vente sélectionnée juste sous le moins cher (« Modifier »)
  Ctrl+F3             mes ventes : toute la liste, avec scroll (RELIST_AUTO = true requis)
  (même touche 2x)    forcer une lecture jugée suspecte
  Ctrl+Alt+F1 (x2)    calibrer le tableau « Actuellement en vente » (coin haut-gauche, puis bas-droit)
  Ctrl+Alt+F2 (x2)    calibrer le menu « Quantité » (coin haut-gauche, puis bas-droit)
  Ctrl+Alt+F3         calibrer le champ « Prix du lot »
  Ctrl+Alt+F4         calibrer le bouton « Mettre en vente »
  Ctrl+Alt+F5 (x2)    (optionnel) calibrer la valeur du « Prix moyen » -> garde-fou prix trop bas
  Ctrl+Alt+F6 (x2)    (optionnel) calibrer le compteur « 21/100 lots en vente » -> F2 vérifie chaque vente
  Ctrl+Alt+F7 (x2)    mes ventes : calibrer le texte du champ « Prix du lot » (ton prix actuel)
  Ctrl+Alt+F8         mes ventes : calibrer le bouton « Modifier » (sinon Entrée)
  Ctrl+Alt+F9 (x2)    mes ventes : 1re ligne puis 2e ligne de la liste (pour Ctrl+F3)
  Ctrl+Alt+F10 (x2)   repère : titre « Hôtel de vente » (les zones suivent l'HDV déplacé)
  Ctrl+Alt+V          afficher les zones calibrées
  Ctrl+Alt+P          arrêter le parcours en cours (Tout vendre, Toute la liste)
"""
from dofus_helper.gui.app import main

if __name__ == "__main__":
    main()
