# 🗺️ Roadmap — Dofus Price Helper

Pistes d'amélioration, de la plus utile à la moins utile.
Priorité conseillée : **2** ou **4** (1 et 3 faits).

---

## ⚡ Vitesse et fiabilité

### 1. Reconnaissance des chiffres Dofus (remplace Tesseract) — ✅ FAIT (apprentissage automatique)
- **Idée** : la police du jeu ne change pas. On enregistre une fois l'image de chaque chiffre (0 à 9), puis on les reconnaît par comparaison directe (template matching).
- **Gain** :
  - lecture ~150-300 ms → ~10-20 ms, boucle Ctrl+F3 2 à 3× plus rapide ;
  - beaucoup moins d'erreurs (icône kamas lue « 4 », chiffres collés, confiance faible).
- **Sécurité** : Tesseract reste en secours si un chiffre n'est pas reconnu.
- **Réalisé autrement** : pas de captures à fournir. Les modèles sont appris sur l'écran de l'utilisateur, à partir des lectures Tesseract très sûres (`dofus_digits.py`, `digit_templates.npz`). Chiffres collés : découpe automatique. Formes parasites (flèche, coin de cadre) : apprises et ignorées. Contrôle croisé 1 lecture sur 25.

### 2. Zones liées à la fenêtre du jeu
- **Problème** : si la fenêtre de l'HDV bouge ou change de taille, il faut tout recalibrer.
- **Idée** : repérer la fenêtre (ex. titre « Hôtel de vente ») et placer toutes les zones par rapport à elle.
- **Gain** : une seule calibration, valable partout.

---

## 💰 Stratégie de prix

### 3. Prix plancher au lieu d'un simple arrêt — ✅ FAIT (`FLOOR_MODE`, `FLOOR_RATIO`)
- **Problème** : si quelqu'un vend très sous le prix moyen, l'outil s'arrête (lecture « suspecte »).
- **Idée** : appliquer une règle à la place, au choix :
  - ne pas suivre et garder ton prix ;
  - ou se mettre au prix plancher (ex. 70 % du prix moyen).
- **Gain** : pas de vente bradée à cause d'un dumper, et Ctrl+F3 ne s'arrête plus en cours de route.

### 4. Baisse adaptée au prix
- −1 kama sur les petits prix, −1 % sur les gros.
- Arrondi propre : 1 499 plutôt que 1 498.

### 5. Anti guerre des prix
- Si un concurrent repasse sous toi plusieurs fois de suite sur le même objet, l'outil arrête de baisser et te prévient.

---

## 📊 Suivi

### 6. Tableau de bord
- À partir de `dofus_price_history.csv` : kamas mis en vente, nombre de modifications par objet, évolution des prix.

### 7. Version .exe
- Un seul fichier à lancer (PyInstaller), sans Python ni terminal.

---

## ✅ Déjà fait

- F1 / F4 : lecture du tableau + quantité, undercut, garde-fous (confiance, cohérence entre lots).
- F2 « Tout vendre » : Entrée répétée, passage au lot inférieur, vérification par le compteur « x/100 lots ».
- Garde-fou « Prix moyen » (`MIN_AVG_RATIO`).
- F3 / Ctrl+F3 « Mettre à jour mes ventes » : Modifier, alignement sur ton propre prix, défilement mesuré, lignes identiques sautées.
- Lecture robuste : icônes pâles, cadre gris du menu Quantité, prix surligné en bleu, champ retrouvé dans une grande zone.
- Alertes de calibration (zone trop serrée).
- Lecture rapide des chiffres apprise (~5 ms au lieu de ~100-300 ms), Tesseract en secours.
- Prix plancher (70 % du prix moyen par défaut) : au plancher / garder mon prix / arrêt.

## ⚠️ Rappel

Ctrl+F3 en boucle et la mise en vente automatique automatisent des actions en jeu : c'est contraire aux CGU d'Ankama et peut mener à un ban. À utiliser en connaissance de cause.
