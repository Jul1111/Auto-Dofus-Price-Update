# Participer à Dofus Price Helper

Merci de votre intérêt pour le projet ! Il y a plusieurs façons d'aider, et toutes ne demandent pas de savoir coder.

## Où poster quoi

| Vous voulez… | Rendez-vous dans |
|---|---|
| Signaler un problème | [Discussions › Bugs](https://github.com/Jul1111/Auto-Dofus-Price-Update/discussions/categories/bugs) |
| Poser une question (installation, calibration, réglages) | [Discussions › Q&A](https://github.com/Jul1111/Auto-Dofus-Price-Update/discussions/categories/q-a) |
| Proposer une idée | [Discussions › Ideas](https://github.com/Jul1111/Auto-Dofus-Price-Update/discussions/categories/ideas) |
| Partager votre retour d'utilisation | [Discussions › Show and tell](https://github.com/Jul1111/Auto-Dofus-Price-Update/discussions/categories/show-and-tell) |
| Proposer du code | Une [pull request](#proposer-du-code) |

Chaque catégorie a un petit formulaire : remplissez-le, il contient tout ce qu'il faut pour comprendre le problème du premier coup.

## Signaler un problème

1. Dans l'outil : onglet **Options** › **📦 Rapport de problème**. Un zip est créé avec le journal, les réglages, les captures de diagnostic et l'image de l'HDV. Rien n'est envoyé automatiquement, et l'historique des ventes n'est pas inclus.
2. Ouvrez une discussion dans **Bugs**, décrivez ce qui s'est passé et joignez le zip.

Les discussions sont publiques : vérifiez le contenu du zip avant de le publier.

## Aider sans coder

- **Tester** les versions de test : chaque pull request construit un zip téléchargeable dans l'onglet **Actions** (artefact « DofusPriceHelper »). Un retour « ça marche chez moi » est déjà utile.
- **Dire sur quelle configuration la calibration automatique fonctionne** (résolution, échelle de l'interface), dans **Show and tell**.
- **Envoyer des captures de l'HDV** quand la lecture d'un prix échoue : elles servent à enrichir les tests OCR (`tests/fixtures`).
- **Voter** 👍 pour les idées qui vous intéressent, pour aider à choisir quoi faire en premier.

## Proposer du code

### Mise en place

Windows 10 ou 11, Python 3.10+ et [Tesseract OCR](https://github.com/UB-Mannheim/tesseract/wiki) 5+.

```bash
git clone https://github.com/Jul1111/Auto-Dofus-Price-Update
cd Auto-Dofus-Price-Update
python -m venv venv
venv\Scripts\activate
pip install -r requirements-dev.txt
pytest
```

Lancement :

```bash
python dofus_price_helper.py       # interface graphique
python dofus_price_helper_cli.py   # ligne de commande
```

Si Tesseract n'est pas dans `C:\Program Files\Tesseract-OCR\`, indiquez son chemin dans `TESSERACT_CMD` (fichier de configuration). Le module `keyboard` peut demander les droits administrateur.

### Où se trouve quoi

| Fichier | Rôle |
|---|---|
| `dofus_helper/` | Moteur, rangé par thème ; tout le reste l'utilise par `from dofus_helper import core` |
| `dofus_helper/core.py` | Rassemble le moteur en un seul module (`core.X`) ; remplacer `core.X` dans un test le remplace partout |
| `dofus_helper/base.py` | Dossiers, version, fichier journal |
| `dofus_helper/config.py` | Réglages, profils, enregistrement sûr |
| `dofus_helper/anchor.py` | Repère HDV : les zones suivent la fenêtre de l'Hôtel de vente |
| `dofus_helper/ocr.py` | Lecture de l'écran (Tesseract, chiffres rapides, lignes de la liste) |
| `dofus_helper/pricing.py` | Calcul du prix |
| `dofus_helper/game.py` | Fenêtre du jeu, souris, presse-papier, saisie, défilement |
| `dofus_helper/hotkeys.py`, `sounds.py` | Raccourcis globaux, sons |
| `dofus_helper/history.py`, `my_prices.py` | Historique des prix, mémoire de tes ventes |
| `dofus_helper/engine.py` | Moteur : F1, F3, Tout vendre, Toute la liste |
| `dofus_price_helper.py` | Interface graphique |
| `dofus_price_helper_cli.py` | Version ligne de commande |
| `dofus_digits.py` | Reconnaissance rapide des chiffres du jeu |
| `dofus_autocal.py` | Calibration automatique |
| `dofus_update.py` | Mise à jour de l'outil |
| `dofus_style.py` | Thèmes, couleurs d'accent, effet verre, fondus |
| `dofus_logo.py` | Logo (dessiné par le code) et icônes |
| `modele_hdv/` | Modèle de l'HDV pour la calibration automatique (`packaging/build_hdv_model.py`) |
| `packaging/` | Construction du zip (`build.py`) et de l'installeur (`installer.iss`) |
| `.github/workflows/` | Tests, construction et publication automatiques |
| `tests/` | Tests unitaires et tests OCR sur captures réelles |
| `docs/` | Guide d'utilisation, visite de l'interface (`INTERFACE.md`) et captures d'écran (`img/`) |
| `tools/readme_shots.py` | Génère les captures de `docs/img` (données d'exemple, sans toucher au jeu) |

Fichiers générés localement et non versionnés : `dofus_price_helper_config.json`, `dofus_price_history.csv`, `digit_templates.npz`, `hdv_anchor.png`, `dofus_my_prices.json`.

### Étapes

1. Pour un changement important, ouvrez d'abord une discussion dans **Ideas**, pour valider l'approche avant d'y consacrer du temps.
2. Créez une branche à partir de `main`.
3. Gardez chaque pull request centrée sur un seul sujet.
4. Ajoutez ou adaptez les tests, et vérifiez que `pytest` passe.
5. Ouvrez la pull request vers `main` en expliquant le problème réglé et la façon dont vous avez testé. La construction du zip et les tests se lancent automatiquement.

### Règles du projet

- **Sécurité des prix d'abord** : tout changement doit garder les protections existantes (relecture du champ « Prix du lot », prix plancher, blocage des lectures douteuses). En cas de doute, l'outil doit s'abstenir plutôt que valider un mauvais prix.
- **Fonctions automatiques désactivées par défaut** : la mise en vente automatique et Ctrl+F3 restent des options à activer soi-même.
- **Interface et messages en français**, en phrases courtes et claires.
- Pas de nouvelle dépendance sans en avoir parlé avant.

## Construire et publier une version

Chaque pull request vers `main` lance les tests et construit le zip et l'installeur, téléchargeables dans l'onglet **Actions** de l'exécution.

Publication dans les Releases (mainteneur) :

```bash
git tag v1.0.0
git push origin v1.0.0
```

Construction locale (Windows, Tesseract installé) :

```bash
pip install pyinstaller
python packaging/build.py --version v1.0.0          # zip dans dist/
iscc /DAppVersion=v1.0.0 /DNumVersion=1.0.0 packaging\installer.iss   # installeur (Inno Setup 6)
```

## Comportement

Ce projet suit un [code de conduite](CODE_OF_CONDUCT.md). Merci de rester respectueux et bienveillant, en particulier avec les débutants.

Projet indépendant, non affilié à Ankama.
