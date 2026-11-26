# Participer à Dofus Price Helper

Merci de t'intéresser au projet ! Il y a plusieurs façons d'aider, et toutes ne demandent pas de savoir coder.

## Où poster quoi

| Tu veux… | Va dans |
|---|---|
| Signaler un problème | [Discussions › Bugs](https://github.com/Jul1111/Auto-Dofus-Price-Update/discussions/categories/bugs) |
| Poser une question (installation, calibration, réglages) | [Discussions › Q&A](https://github.com/Jul1111/Auto-Dofus-Price-Update/discussions/categories/q-a) |
| Proposer une idée | [Discussions › Ideas](https://github.com/Jul1111/Auto-Dofus-Price-Update/discussions/categories/ideas) |
| Dire comment ça se passe chez toi | [Discussions › Show and tell](https://github.com/Jul1111/Auto-Dofus-Price-Update/discussions/categories/show-and-tell) |
| Proposer du code | Une [pull request](#proposer-du-code) |

Chaque catégorie a un petit formulaire : remplis-le, il contient tout ce qu'il faut pour comprendre le problème du premier coup.

## Signaler un problème

1. Dans l'outil : onglet **Options** › **📦 Rapport de problème**. Un zip est créé avec le journal, les réglages, les captures de diagnostic et l'image de l'HDV. Rien n'est envoyé automatiquement, et l'historique des ventes n'est pas inclus.
2. Ouvre une discussion dans **Bugs**, décris ce qui s'est passé et joins le zip.

Les discussions sont publiques : jette un œil au contenu du zip avant de le publier.

## Aider sans coder

- **Tester** les versions de test : chaque pull request construit un zip téléchargeable dans l'onglet **Actions** (artefact « DofusPriceHelper »). Un retour « ça marche chez moi » est déjà utile.
- **Dire sur quelle configuration la calibration automatique fonctionne** (résolution, échelle de l'interface), dans **Show and tell**.
- **Envoyer des captures de l'HDV** quand la lecture d'un prix échoue : elles servent à enrichir les tests OCR (`tests/fixtures`).
- **Voter** 👍 pour les idées qui t'intéressent, pour aider à choisir quoi faire en premier.

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

### Où se trouve quoi

| Fichier | Rôle |
|---|---|
| `dofus_core.py` | Moteur : lecture, calcul des prix, saisie, contrôles de sécurité |
| `dofus_price_helper_psg.py` | Interface graphique |
| `dofus_price_helperV2.py` | Version ligne de commande |
| `dofus_digits.py` | Reconnaissance rapide des chiffres du jeu |
| `dofus_autocal.py` | Calibration automatique |
| `dofus_update.py` | Mise à jour de l'outil |
| `tests/` | Tests unitaires et tests OCR sur captures réelles |

### Étapes

1. Pour un changement important, ouvre d'abord une discussion dans **Ideas** : on se met d'accord avant que tu y passes du temps.
2. Crée une branche à partir de `main`.
3. Garde chaque pull request centrée sur un seul sujet.
4. Ajoute ou adapte les tests, et vérifie que `pytest` passe.
5. Ouvre la pull request vers `main` en expliquant le problème réglé et comment tu as testé. La construction du zip et les tests se lancent automatiquement.

### Règles du projet

- **Sécurité des prix d'abord** : tout changement doit garder les protections existantes (relecture du champ « Prix du lot », prix plancher, blocage des lectures douteuses). En cas de doute, l'outil doit s'abstenir plutôt que valider un mauvais prix.
- **Fonctions automatiques désactivées par défaut** : la mise en vente automatique et Ctrl+F3 restent des options à activer soi-même.
- **Interface et messages en français**, en phrases courtes et claires.
- Pas de nouvelle dépendance sans en avoir parlé avant.

## Comportement

Ce projet suit un [code de conduite](CODE_OF_CONDUCT.md). Sois respectueux et bienveillant, en particulier avec les débutants.

Projet indépendant, non affilié à Ankama.
