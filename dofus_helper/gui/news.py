"""« Quoi de neuf » après une mise à jour."""
from __future__ import annotations

from dofus_helper import core


# ---------------------------------------------------------------- « Quoi de neuf » après une mise à jour
# {version: [lignes]} ; {pause} / {hud} = touches actuelles. Les plus récentes en dernier.
WHATS_NEW = {
    "1.8.0": [
        "Le HUD, une ligne discrète par-dessus le jeu, remplace le popup de résultat, le bandeau et le "
        "mode compact. Après chaque action, il s'allume de la couleur du résultat.",
        "{hud} l'affiche ou le cache. « Déplacer » (onglet Options) le pose où tu veux.",
    ],
    "1.9.0": [
        "HUD réglable dans l'onglet Options : taille, opacité, et contenu (état, dernière action, ou les deux).",
        "Pendant Tout vendre ou Toute la liste, le HUD rappelle « {pause} = arrêter », et le menu de "
        "l'icône près de l'horloge propose « Arrêter le parcours ».",
        "Une couleur par profil, visible dans le HUD, sur la pastille Profil et sur l'icône près de "
        "l'horloge. Elle se choisit dans l'onglet Calibration.",
        "Dernière lecture : une pastille de couleur indique si chaque prix a été lu de façon sûre "
        "(détail au survol).",
        "Sauvegarder et restaurer réglages, profils et calibration en un seul fichier (onglet Options).",
    ],
    "1.10.0": [
        "Renommer un profil (onglet Calibration) : ses personnages associés, sa couleur et son repère suivent.",
        "{window} affiche ou cache la fenêtre de l'outil, même depuis le jeu.",
        "Quand la mise en vente automatique est coupée, le HUD rappelle « Entrée pour valider » une fois "
        "le prix saisi (ou « Ctrl+V puis Entrée » s'il est seulement copié).",
    ],
    "1.11.0": [
        "Plus de pause : {pause} arrête le parcours en cours (Tout vendre, Toute la liste), comme le bouton "
        "« Arrêter », et les touches restent actives. Le bouton Pause a disparu.",
        "HUD : option « 3 derniers prix sous la ligne » (onglet Options) pour vérifier les derniers lots "
        "d'un coup d'œil, aussi pendant un parcours.",
        "Fin de Toute la liste : le résumé commence par un récap (modifiés, à revoir, déjà au bon prix, "
        "durée, raison de l'arrêt). Un clic sur une ligne la retrouve dans le journal.",
        "Visite guidée en 5 bulles au premier lancement. Elle se relance avec « Visite guidée » "
        "(onglet Accueil).",
        "HUD pendant un parcours : barre de progression et temps restant estimé.",
        "HUD : contenu « Pastille » (un simple rond qui s'agrandit à chaque action), et option « Masquer » "
        "pour qu'il s'estompe sans action.",
        "Dans le jeu, maintiens Alt : le HUD devient cliquable (Arrêter le parcours, Copier le dernier prix, "
        "Ouvrir l'outil) ; Alt + glisser le déplace.",
        "Toute la liste va jusqu'au bout : la barre de défilement de l'HDV sert de repère, et le défilement "
        "est relancé quand le jeu ignore la molette.",
        "Nouvelle option (Mes ventes) : « Modifier même si le prix est suspect », pour suivre un marché qui "
        "chute. Le prix est relu une 2e fois avant ; une lecture peu fiable reste bloquée.",
    ],
    "1.12.0": [
        "HUD : la pastille passe à l'orange quand la calibration semble décalée (fenêtre du jeu "
        "redimensionnée, écran changé, HDV introuvable). Maintiens Alt : « Recalibrer » la refait sans "
        "quitter le jeu.",
        "Nouveau look : en-tête redessiné, icônes maison à la place des emojis, barre de titre aux couleurs "
        "du thème (Windows 11). Le panneau Activité montre l'écart de prix (▼ 4 %).",
        "Journal en cartes : une barre de couleur et une icône par ligne. Ambiances du thème sombre "
        "(Nuit, Ambre, Forêt, Océan) et petites animations (survol, onglets, compteurs).",
        "HUD : le nouveau prix défile jusqu'à sa valeur, le HUD change de taille en douceur, le rond respire "
        "pendant un parcours. Formes au choix (Carte, Pilule, Minimal) ; en multi-compte, son bord prend la "
        "couleur du personnage.",
        "HUD : l'option sous la ligne montre maintenant les prix (lots 1, 10, 100) de l'objet sélectionné dans "
        "l'HDV, mis à jour quand tu changes d'objet.",
        "Réduire la fenêtre la range toujours près de l'horloge, et la fenêtre s'adapte à sa taille : plus "
        "étroite, le panneau Activité se retire.",
        "Toute la liste : la dernière vente n'est plus oubliée en bas de liste, la reprise sur une liste "
        "déjà défilée ne s'arrête plus à tort, et les ventes vendues sont oubliées après un parcours complet.",
        "Corrections : la calibration ne peut plus être perdue (réglages illisibles gardés de côté), un "
        "prix suspect est relu sur une autre image, et la mise à jour en un clic attend aussi un "
        "exemplaire lancé en administrateur.",
    ],
    "1.13.0": [
        "Thèmes Dofus (Options › Apparence) : les 11 thèmes du jeu, avec leurs fonds, leur barre de titre "
        "colorée et leur couleur d'accent. Choisis le même que dans Dofus pour que l'outil s'y fonde.",
    ],
}


def whats_new(last_seen: str, current: str) -> list:
    """[(version, lignes)] à montrer : les versions après `last_seen`, jusqu'à `current` (3 au plus).
    last_seen vide = mise à jour depuis une version qui ne le notait pas : les dernières."""
    cur = core.parse_version(current)
    if cur is None:
        return []
    seen = core.parse_version(last_seen) or (0, 0, 0)
    out = [(v, lines) for v, lines in WHATS_NEW.items()
           if seen < (core.parse_version(v) or (0, 0, 0)) <= cur]
    out.sort(key=lambda x: core.parse_version(x[0]))
    return out[-3:]

