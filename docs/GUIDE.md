# Guide d'utilisation

Le [README](../README.md) donne l'essentiel. Ce guide détaille chaque fonction.

- [Calibration](#calibration)
- [Vendre et mettre à jour les prix](#vendre-et-mettre-à-jour-les-prix)
- [Sécurité des prix](#sécurité-des-prix)
- [Raccourcis](#raccourcis)
- [Interface](#interface)
- [Profils et multi-compte](#profils-et-multi-compte)
- [Sauvegarde](#sauvegarde)
- [Mises à jour](#mises-à-jour)
- [Signaler un problème](#signaler-un-problème)
- [Configuration](#configuration)
- [Version ligne de commande](#version-ligne-de-commande)
- [Données enregistrées](#données-enregistrées)

## Calibration

Au tout premier lancement, une **visite guidée** en 5 bulles montre la calibration, les touches, l'arrêt d'un parcours, le HUD et le journal. Elle se relance avec **Visite guidée** dans l'onglet **Accueil** (ou depuis l'onglet **Options**), et `Échap` l'arrête. La calibration automatique est proposée juste après.

L'outil doit savoir où se trouvent les zones de l'HDV à l'écran.

### Calibration automatique

1. Ouvrez l'HDV sur l'onglet **Vente** et sélectionnez une de vos ventes (ou un objet de l'inventaire).
2. Cliquez sur **Calibration automatique** dans l'onglet **Calibration** (ou `Ctrl+Alt+F12` en jeu).
3. Vérifiez le résultat avec **Voir zones**.

L'outil trouve l'HDV quelles que soient la résolution et l'échelle de l'interface, place toutes les zones et lance un test de lecture. Elle est proposée dès le premier lancement.

Limite : **Dofus 3 en français**, sur la même version du jeu que le modèle de l'outil. Si l'HDV n'est pas reconnu (autre langue, interface modifiée par une mise à jour du jeu), utilisez la calibration manuelle.

Si vous changez ensuite l'échelle de l'interface ou la résolution, l'outil s'en rend compte et refait la calibration automatique (option dans l'onglet **Calibration**). L'outil vérifie aussi toutes les 5 secondes que la calibration colle encore à la fenêtre du jeu. Si elle semble décalée (fenêtre redimensionnée, écran changé) ou si l'HDV est introuvable, un bandeau apparaît avec un bouton **Recalibrer**, et la pastille du HUD passe à l'orange (« ⚠ Calibration décalée »). En jeu, maintenez `Alt` : **✨ Recalibrer** dans le HUD refait la calibration automatique sans quitter le jeu (l'HDV doit être ouvert, onglet Vente). L'alerte disparaît d'elle-même une fois réglé.

### Calibration manuelle

L'assistant pas à pas se trouve dans l'onglet **Calibration**, section **Avancé**. Il affiche la liste des étapes avec leur état, une capture de ce que l'outil voit dans chaque zone et ce qu'il y lit (✓ ou ✗). Il propose **Refaire cette zone** et **Tout placer automatiquement**, puis lance la vérification finale.

| Zone | Statut |
|---|---|
| Tableau « Actuellement en vente » | Obligatoire |
| Menu « Quantité » | Obligatoire |
| Champ « Prix du lot » | Obligatoire |
| Titre « Hôtel de vente » | Recommandé (suivi de la fenêtre) |
| Prix moyen | Recommandé (prix plancher) |
| Bouton « Modifier » | Recommandé (F1 automatique, F3) |
| Compteur de lots, lignes de la liste | Optionnel (F2 vérifié, Ctrl+F3) |

Quand le titre « Hôtel de vente » est calibré, les zones suivent la fenêtre de l'HDV si vous la déplacez.

## Vendre et mettre à jour les prix

- **F1** vend l'objet sélectionné dans l'inventaire, ou met à jour le prix d'une de vos ventes. Le mode est détecté automatiquement.
- **F2** remet en vente au même prix tant que la situation le permet, et passe au lot inférieur quand le stock baisse.
- **F3** met à jour la vente sélectionnée.
- **Ctrl+F3** met à jour toute la liste de vos ventes, avec défilement automatique. Fonction désactivée par défaut : activez-la dans l'onglet **Mes ventes**.
- **F4** choisit le meilleur lot (prix par objet le plus élevé).

Pendant un parcours **F2** ou **Ctrl+F3**, la progression s'affiche en haut de la fenêtre et dans le HUD (« Ligne 34 / 87 · 12 modifiées » ; le total est connu si le compteur « x/100 lots » est calibré). Le bouton **Arrêter**, ou **Arrêter le parcours** dans le menu de l'icône de la zone de notification, interrompt le parcours sans mettre l'outil en pause. En jeu, `Ctrl+Alt+P` l'arrête aussi (tout comme un clic sur la pastille **■ Arrêter le parcours**). L'outil n'a pas de pause : les touches restent actives.

À la fin d'un Ctrl+F3, un résumé s'ouvre. En tête, un récap : prix modifiés, lignes à revoir, lignes déjà au bon prix, durée, et la raison de l'arrêt si la liste n'a pas été parcourue jusqu'au bout. Dessous, le détail des prix modifiés (ancien → nouveau, avec l'image du nom de l'objet) et des lignes à revoir. Un clic sur une ligne la retrouve et la surligne dans le journal. Les 10 derniers résumés restent consultables dans l'onglet **Mes ventes**.

L'onglet **Prix** affiche un aperçu en direct du calcul (« Moins cher 1 000 → ton prix 999 (plancher 700) »), recalculé à chaque réglage.

## Sécurité des prix

| Situation | Comportement |
|---|---|
| Lecture incertaine ou prix incohérent entre lots | Prix copié uniquement ; nouvel appui pour forcer |
| Champ « Prix du lot » différent du prix calculé | Aucune validation |
| Concurrent sous le prix plancher | Vente au plancher, conservation du prix actuel ou arrêt (onglet **Prix**) |
| Votre prix est déjà le plus bas | Aucune baisse |
| Le moins cher est une autre de vos ventes du même objet | Alignement sur ce prix, pas de baisse |
| F2 : compteur de lots inchangé après une vente | Arrêt |

Le prix plancher est calculé à partir du prix moyen (70 % par défaut), pour ne pas suivre un vendeur qui brade.

L'outil reconnaît vos propres ventes grâce à l'image du nom de l'objet : il ne passe jamais sous votre propre prix, même d'une session à l'autre.

La lecture des chiffres repose sur un modèle de la police du jeu, appris automatiquement sur votre écran (environ 5 ms par lecture). Tesseract sert de secours et de contrôle croisé.

## Raccourcis

| Touche | Action |
|---|---|
| `F1` | Vendre (objet de l'inventaire) ou mettre à jour (une de vos ventes) |
| `F2` | Tout vendre au même prix |
| `F3` | Mettre à jour la vente sélectionnée |
| `Ctrl+F3` | Mettre à jour toute la liste |
| `F4` | Meilleur lot |
| Même touche deux fois | Forcer une lecture jugée suspecte |
| `Ctrl+Alt+P` | Arrêter le parcours en cours (Tout vendre, Toute la liste) |
| `Ctrl+Alt+V` | Afficher les zones calibrées |
| `Ctrl+Alt+H` | Aide-mémoire des touches par-dessus le jeu |
| `Ctrl+Alt+U` | Afficher ou cacher le HUD |
| `Ctrl+Alt+O` | Afficher ou cacher la fenêtre de l'outil, même depuis le jeu |
| `Ctrl+Alt+F1` à `F12` | Calibration (liste dans l'onglet **Raccourcis**, section **Avancé**) |

Tous les raccourcis se changent dans l'onglet **Raccourcis** : bouton **Changer**, puis la touche voulue.

Dans la fenêtre de l'outil : `Ctrl+1` à `Ctrl+6` pour les onglets (fonctionne aussi en AZERTY), `Ctrl+L` pour vider le journal, `Échap` pour fermer les popups.

## Interface

**Accueil.** Les premiers pas se cochent tout seuls (calibrer, tester une lecture, première vente). L'onglet affiche aussi les touches principales et le bilan de la session.

**Barre d'état.** Des pastilles indiquent l'état (actif, ou parcours en cours à arrêter), le profil, la calibration (OK ou à faire) et l'HDV (vu ou introuvable). Un clic sur une pastille mène à l'endroit utile.

**Journal.** Filtres **Tout**, **Ventes** et **Problèmes**, bouton **Copier**, une icône par type de ligne. Chaque parcours F2 ou Ctrl+F3 est regroupé dans un bloc repliable. Un clic sur une ligne qui contient un prix copie ce prix.

**Activité.** Les dernières actions (ancien → nouveau prix, statut en couleur) et la dernière lecture. Devant chaque prix lu, une pastille indique la fiabilité de la lecture : verte si elle est sûre, orange si elle est moyenne, rouge si elle est douteuse (l'outil ne colle alors pas ce prix tout seul). Le détail s'affiche au survol.

**Par-dessus le jeu.**
- **HUD** (`Ctrl+Alt+U`) : une ligne avec l'état, la dernière action ou la progression. Après chaque action, son bord s'allume de la couleur du résultat. Les clics le traversent et il n'apparaît que quand Dofus est au premier plan.
  - Pendant Tout vendre ou Toute la liste, il rappelle la touche pour arrêter (`Ctrl+Alt+P`).
  - Si la mise en vente automatique est coupée, il rappelle « Entrée pour valider » une fois le prix saisi, ou « Ctrl+V puis Entrée » si le prix est seulement copié.
  - Dans l'onglet **Options** : **Déplacer**, taille (petit, normal, grand), opacité, et contenu (état, dernière action, ou les deux).
  - Option **3 derniers prix sous la ligne** : les trois derniers lots traités (prix lu → prix mis), le plus récent en couleur, aussi pendant un parcours.
  - Pendant un parcours : une barre de progression et le temps restant estimé (« ≈ 2 min restantes »), dès que le total est connu.
  - Contenu **Pastille** : le HUD n'est plus qu'un petit rond de couleur, qui s'agrandit 2 secondes à chaque action.
  - **Masquer** (jamais, 10 s, 30 s, 1 min) : sans action pendant ce temps, le HUD s'estompe. Il revient à la prochaine action, pendant un parcours, ou en maintenant Alt.
  - **Alt maintenu** (seul) dans le jeu : le HUD devient cliquable et propose **Arrêter le parcours**, **Copier** le dernier prix et **Ouvrir l'outil**. Alt + glisser le déplace. Relâchez Alt et les clics le traversent à nouveau.
- **Aide-mémoire** (`Ctrl+Alt+H`) : déplaçable ; il reste alors affiché à cet endroit jusqu'au ✕.

**Zone de notification.** Un clic ouvre l'outil. Un clic droit donne accès au HUD, à l'aide-mémoire ou à la fermeture, et pendant un parcours à **Arrêter le parcours**. La pastille de l'icône montre l'état : vert actif, bleu parcours en cours, rouge calibration à faire. En option, réduire la fenêtre la cache à cet endroit.

**Notifications et sons.** Une notification Windows signale la fin d'un long parcours quand vous êtes dans une autre fenêtre. Des sons discrets accompagnent succès, avertissements, erreurs et fin de parcours, avec volume réglable et bouton **Tester**. Tout se désactive dans **Options**.

**Apparence** (onglet **Options**).
- Thème **Sombre**, **Clair** ou **Comme Windows**, et six couleurs d'accent, avec aperçu avant d'appliquer.
- Style **Verre** : le jeu derrière l'outil apparaît flouté, comme une vitre teintée, avec une teinte réglable. Nécessite Windows 10 (1803+) ou 11 et le thème sombre. Le style **Classique** reste opaque.
- Taille du texte réglable, aide au survol sur les options, fondus désactivables.
- Taille et position de la fenêtre mémorisées.

## Profils et multi-compte

Les profils de calibration (onglet **Calibration**) permettent d'en garder un par HDV ou par personnage. On passe de l'un à l'autre en un clic. **Nouveau** copie le profil actuel : il ne reste qu'à recalibrer ce qui change. **Renommer** change le nom du profil actif ; ses personnages associés, sa couleur et son repère suivent.

Le profil suit aussi le personnage joué, lu dans le titre de la fenêtre du jeu :
- choisir un profil pendant que vous jouez un personnage associe ce profil au personnage ;
- un profil qui porte le nom du personnage est pris automatiquement.

Chaque profil a une couleur, choisie sous **Couleur du profil**. Avec plusieurs profils, elle apparaît dans le HUD, sur la pastille **Profil** et en anneau autour de l'icône de la zone de notification : vous voyez d'un coup d'œil quel profil est actif.

## Sauvegarde

Dans l'onglet **Options**, **Sauvegarder…** crée un seul fichier `.zip`. Il contient les réglages, les profils (avec leurs personnages et leurs couleurs), la calibration, les chiffres appris et les derniers parcours Ctrl+F3. L'historique des ventes n'y est pas.

**Restaurer…** remplace les réglages actuels par ceux de la sauvegarde, puis redémarre l'outil. Les réglages actuels sont d'abord gardés dans le dossier `sauvegardes`.

## Mises à jour

Au démarrage, l'outil vérifie sur GitHub si une version plus récente est publiée. Si c'est le cas, il affiche un bouton **⬆ Installer vX.Y.Z** : un clic télécharge la version, vérifie le fichier, puis l'outil redémarre dans la nouvelle version.

Réglages, calibration et profils sont conservés. Si la copie échoue, l'ancienne version est remise en place. Au premier lancement d'une nouvelle version, une fenêtre **Quoi de neuf** résume les nouveautés. Elle se rouvre depuis l'onglet **Options**.

La vérification se désactive dans l'onglet **Options**.

## Signaler un problème

1. Onglet **Options** › **📦 Rapport de problème** : l'outil crée un zip contenant le journal, les réglages, les captures de diagnostic et l'image de l'HDV. Rien n'est envoyé automatiquement et l'historique des ventes n'est pas inclus.
2. Ouvrez une discussion dans [Bugs](https://github.com/Jul1111/Auto-Dofus-Price-Update/discussions/categories/bugs) en joignant le zip.

Le journal seul se trouve dans `%APPDATA%\Dofus Price Helper\journaux\journal.log`.

## Configuration

Les réglages se modifient dans l'interface. Ils sont enregistrés dans `dofus_price_helper_config.json`, dans `%APPDATA%\Dofus Price Helper` pour la version Windows. Toutes les options sont listées dans [`dofus_price_helper_config.example.json`](../dofus_price_helper_config.example.json).

| Option | Description | Défaut |
|---|---|---|
| `UNDERCUT_MODE` / `UNDERCUT_VALUE` | Baisse appliquée (kamas ou pourcentage) | `fixed` / `1` |
| `FLOOR_RATIO` | Prix plancher, en fraction du prix moyen | `0.7` |
| `FLOOR_MODE` | Comportement sous le plancher (`floor`, `keep`, `stop`) | `floor` |
| `VERIFY_BEFORE_ENTER` | Relecture du champ avant validation | `true` |
| `AUTO_VALIDATE` | Mise en vente automatique après saisie | `false` |
| `RELIST_AUTO` | Autoriser Ctrl+F3 | `false` |
| `HOTKEYS` | Raccourcis clavier | voir l'exemple |
| `TESSERACT_CMD` | Chemin de Tesseract, si non installé à l'emplacement standard | — |

## Version ligne de commande

`python dofus_price_helperV2.py` a les mêmes raccourcis que l'interface. Ses options sont enregistrées dans la configuration :

```bash
python dofus_price_helperV2.py --plancher 70 --sous-plancher plancher   # plancher à 70 % du prix moyen
python dofus_price_helperV2.py --plancher 0                             # plancher désactivé
python dofus_price_helperV2.py --f1-simple                              # F1 vend toujours
python dofus_price_helperV2.py --help
```

## Données enregistrées

Tout reste sur votre PC, dans `%APPDATA%\Dofus Price Helper` (ou dans le dossier du projet si vous le lancez depuis le code source) :

| Fichier | Contenu |
|---|---|
| `dofus_price_helper_config.json` | Réglages et calibration |
| `dofus_price_history.csv` | Historique des ventes |
| `dofus_my_prices.json` | Prix de vos ventes, conservés 2 jours |
| `digit_templates.npz` | Modèle des chiffres du jeu, appris sur votre écran |
| `hdv_anchor.png` | Image du titre « Hôtel de vente », servant de repère |
| `journaux/` | Journal de fonctionnement |
| `sauvegardes/` | Réglages mis de côté avant une restauration |

La seule connexion réseau est la vérification des mises à jour sur GitHub, désactivable.
