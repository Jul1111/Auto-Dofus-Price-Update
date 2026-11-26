# Dofus Price Helper

Assistant de vente pour l'Hôtel de Vente de Dofus. L'outil lit l'écran par OCR, calcule un prix juste sous le moins cher, le saisit dans « Prix du lot », le vérifie, puis valide.

![Python](https://img.shields.io/badge/python-3.10%2B-3776AB?logo=python&logoColor=white)
![Platform](https://img.shields.io/badge/platform-Windows-0078D6)
![OCR](https://img.shields.io/badge/OCR-Tesseract-5C5C5C)
![License](https://img.shields.io/badge/license-MIT-green)

> [!WARNING]
> Les conditions d'utilisation d'Ankama interdisent en général les logiciels tiers qui interagissent avec le client de jeu. La mise en vente automatique et la mise à jour de toute la liste (Ctrl+F3) sont désactivées par défaut. Leur utilisation se fait à vos risques.

## Sommaire

- [Démonstration](#démonstration)
- [Fonctionnalités](#fonctionnalités)
- [Installation](#installation)
- [Utilisation](#utilisation)
- [Sécurité des prix](#sécurité-des-prix)
- [Configuration](#configuration)
- [Structure du projet](#structure-du-projet)
- [Tests](#tests)
- [Publier une version](#publier-une-version)
- [Licence](#licence)

## Démonstration

<img width="800" alt="Démonstration de Dofus Price Helper" src="https://github.com/user-attachments/assets/c0b4e31f-562e-45e9-8127-4ed8c1cc7a45" />

| Interface | Zones calibrées dans l'HDV |
|---|---|
| ![Interface](docs/interface.png) | ![Zones calibrées dans l'HDV](docs/calibrage.png) |
| **Onglet Calibration** | |
| ![Onglet Calibration](docs/assistant.png) | |

## Fonctionnalités

**Vente**
- **F1** : vend l'objet sélectionné dans l'inventaire, ou met à jour le prix d'une de vos ventes. Le mode est détecté automatiquement.
- **F2** : remet en vente au même prix tant que la situation le permet et passe au lot inférieur quand le stock baisse.
- **Ctrl+F3** : met à jour toute la liste de vos ventes, avec défilement automatique.

**Fiabilité**
- Relecture du champ « Prix du lot » avant chaque validation.
- Prix plancher calculé à partir du prix moyen, pour ne pas suivre un vendeur qui brade.
- Blocage des lectures douteuses (confiance faible, incohérence entre lots).
- Reconnaissance de vos propres ventes (par l'image du nom de l'objet) : l'outil ne passe jamais sous votre propre prix, même d'une session à l'autre.

**Performance**
- Reconnaissance des chiffres du jeu apprise automatiquement, environ 5 ms par lecture, avec Tesseract en secours.
- Attente des changements à l'écran plutôt que des pauses fixes.

**Ergonomie**
- Assistant de calibration pas à pas, avec vérification finale.
- Zones qui suivent la fenêtre de l'HDV lorsqu'elle est déplacée.
- Bandeau de résultat au-dessus de l'HDV et fenêtre toujours au premier plan.
- Raccourcis modifiables dans l'onglet **Raccourcis** (bouton « Changer », puis la touche voulue).
- Ctrl+F3 affiche chaque ligne traitée dans le journal, pendant le parcours, puis un résumé : prix modifiés (ancien → nouveau, avec l'image du nom de l'objet) et lignes à revoir.
- Profils de calibration (onglet **Calibration**) : un par HDV ou par personnage, on passe de l'un à l'autre en un clic. « Nouveau » copie le profil actuel ; il ne reste qu'à recalibrer ce qui change.

## Installation

### Version Windows prête à l'emploi (recommandé)

1. Téléchargez `DofusPriceHelper-vX.Y.Z.zip` dans les [Releases](https://github.com/Jul1111/Auto-Dofus-Price-Update/releases/latest).
2. Décompressez-le où vous voulez, puis lancez `DofusPriceHelper.exe` (gardez le dossier `_internal` à côté).

Rien d'autre à installer : Tesseract est inclus. Si un Tesseract 5 ou plus récent est déjà installé, c'est lui qui est utilisé. Les réglages et la calibration sont enregistrés dans `%APPDATA%\Dofus Price Helper` et sont conservés d'une version à l'autre.

Au démarrage, l'outil vérifie sur GitHub si une version plus récente est publiée et affiche alors un bouton « ⬆ vX.Y.Z disponible » (désactivable dans l'onglet **Options**). Un fichier journal (`%APPDATA%\Dofus Price Helper\journaux\journal.log`) garde les messages et les erreurs : joignez-le quand vous signalez un problème (onglet **Options**, « Ouvrir le dossier du journal »).

L'exe n'est pas signé et il lit le clavier : Windows SmartScreen peut afficher « Windows a protégé votre PC » (« Informations complémentaires », puis « Exécuter quand même »), et certains antivirus peuvent le signaler.

### Depuis le code source

Prérequis :

- Windows 10 ou 11
- Python 3.10 ou plus récent
- [Tesseract OCR](https://github.com/UB-Mannheim/tesseract/wiki) 5 ou plus récent
- Dofus en mode fenêtré ou plein écran fenêtré

Étapes :

```bash
git clone https://github.com/Jul1111/Auto-Dofus-Price-Update
cd Auto-Dofus-Price-Update
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```

Si Tesseract n'est pas installé dans `C:\Program Files\Tesseract-OCR\`, indiquez son chemin dans `TESSERACT_CMD` (fichier de configuration).

### Lancement

```bash
python dofus_price_helper_psg.py   # interface graphique (recommandé)
python dofus_price_helperV2.py     # ligne de commande
```

Le module `keyboard` peut nécessiter des droits administrateur.

La version ligne de commande a les mêmes raccourcis (F1 vend ou met à jour selon le panneau ouvert) et accepte quelques options, enregistrées dans la configuration :

```bash
python dofus_price_helperV2.py --plancher 70 --sous-plancher plancher   # plancher à 70 % du prix moyen
python dofus_price_helperV2.py --plancher 0                             # plancher désactivé
python dofus_price_helperV2.py --f1-simple                              # F1 vend toujours
python dofus_price_helperV2.py --help
```

## Utilisation

### Première calibration

Au premier lancement, l'assistant de calibration s'ouvre automatiquement (sinon : onglet **Calibration**, puis **Ouvrir l'assistant de calibration**). Il décrit chaque zone à sélectionner dans le jeu et termine par un test de lecture complet.

| Zone | Statut |
|---|---|
| Tableau « Actuellement en vente » | Obligatoire |
| Menu « Quantité » | Obligatoire |
| Champ « Prix du lot » | Obligatoire |
| Titre « Hôtel de vente » | Recommandé (suivi de la fenêtre) |
| Prix moyen | Recommandé (prix plancher) |
| Bouton « Modifier » | Recommandé (F1 automatique, F3) |
| Compteur de lots, lignes de la liste | Optionnel (F2 vérifié, Ctrl+F3) |

### Raccourcis

| Touche | Action |
|---|---|
| `F1` | Vendre (objet de l'inventaire) ou mettre à jour (une de vos ventes) |
| `F2` | Tout vendre au même prix |
| `F3` | Mettre à jour la vente sélectionnée |
| `Ctrl+F3` | Mettre à jour toute la liste (à activer dans l'onglet **Mes ventes**) |
| `F4` | Meilleur lot (prix par objet le plus élevé) |
| Même touche deux fois | Forcer une lecture jugée suspecte |
| `Ctrl+Alt+P` | Pause et reprise, arrêt des boucles |
| `Ctrl+Alt+V` | Afficher les zones calibrées |

Les raccourcis de calibration (`Ctrl+Alt+F1` à `Ctrl+Alt+F11`) sont listés dans l'onglet **Calibration**. Tous les raccourcis se changent dans l'onglet **Raccourcis**.

## Sécurité des prix

| Situation | Comportement |
|---|---|
| Lecture incertaine ou prix incohérent entre lots | Prix copié uniquement ; nouvel appui pour forcer |
| Champ « Prix du lot » différent du prix calculé | Aucune validation |
| Concurrent sous le prix plancher | Vente au plancher, conservation du prix actuel ou arrêt (onglet **Prix**) |
| Votre prix est déjà le plus bas | Aucune baisse |
| Le moins cher est une autre de vos ventes du même objet | Alignement sur ce prix, pas de baisse |
| F2 : compteur de lots inchangé après une vente | Arrêt |

## Configuration

Les réglages sont modifiables dans l'interface et enregistrés dans `dofus_price_helper_config.json`, créé au premier lancement. Le fichier `dofus_price_helper_config.example.json` liste toutes les options disponibles.

| Option | Description | Défaut |
|---|---|---|
| `UNDERCUT_MODE` / `UNDERCUT_VALUE` | Baisse appliquée (kamas ou pourcentage) | `fixed` / `1` |
| `FLOOR_RATIO` | Prix plancher, en fraction du prix moyen | `0.7` |
| `FLOOR_MODE` | Comportement sous le plancher (`floor`, `keep`, `stop`) | `floor` |
| `VERIFY_BEFORE_ENTER` | Relecture du champ avant validation | `true` |
| `AUTO_VALIDATE` | Mise en vente automatique après saisie | `false` |
| `RELIST_AUTO` | Autoriser Ctrl+F3 | `false` |
| `HOTKEYS` | Raccourcis clavier (modifiables dans l'onglet **Raccourcis**) | voir l'exemple |

## Structure du projet

```
Auto-Dofus-Price-Update/
├── dofus_price_helper_psg.py   Interface graphique
├── dofus_price_helperV2.py     Version ligne de commande
├── dofus_core.py               Moteur : lecture, calcul des prix, saisie, contrôles
├── dofus_digits.py             Reconnaissance rapide des chiffres
├── packaging/build.py          Construction de la version Windows (zip)
├── .github/workflows/          Construction automatique et publication des versions
├── docs/                       Captures d'écran
└── tests/                      Tests unitaires et tests OCR sur captures réelles
```

Fichiers générés localement et non versionnés : `dofus_price_helper_config.json`, `dofus_price_history.csv`, `digit_templates.npz`, `hdv_anchor.png`, `dofus_my_prices.json` (prix de vos ventes, gardés 2 jours).

## Tests

```bash
pip install -r requirements-dev.txt
pytest
```

## Publier une version

Chaque pull request vers `main` construit le zip et lance les tests sur GitHub : le zip est téléchargeable dans l'onglet **Actions** de l'exécution, pour l'essayer. Pour publier une version dans les Releases :

```bash
git tag v1.0.0
git push origin v1.0.0
```

Construction locale (Windows, Tesseract installé) : `pip install pyinstaller`, puis `python packaging/build.py --version v1.0.0`. Le zip est créé dans `dist/`.

## Licence

Distribué sous licence MIT. Voir [LICENSE](LICENSE).

Projet indépendant, non affilié à Ankama.
