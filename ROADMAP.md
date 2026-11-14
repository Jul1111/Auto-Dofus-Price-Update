# 🗺️ Roadmap — Dofus Price Helper

Pistes d'amélioration, de la plus utile à la moins utile.
Reste : **7** (version .exe).

---

## ⚡ Vitesse et fiabilité

### 1. Reconnaissance des chiffres Dofus (remplace Tesseract) — ✅ FAIT (apprentissage automatique)
- **Idée** : la police du jeu ne change pas. On enregistre une fois l'image de chaque chiffre (0 à 9), puis on les reconnaît par comparaison directe (template matching).
- **Gain** :
  - lecture ~150-300 ms → ~10-20 ms, boucle Ctrl+F3 2 à 3× plus rapide ;
  - beaucoup moins d'erreurs (icône kamas lue « 4 », chiffres collés, confiance faible).
- **Sécurité** : Tesseract reste en secours si un chiffre n'est pas reconnu.
- **Réalisé autrement** : pas de captures à fournir. Les modèles sont appris sur l'écran de l'utilisateur, à partir des lectures Tesseract très sûres (`dofus_digits.py`, `digit_templates.npz`). Chiffres collés : découpe automatique. Formes parasites (flèche, coin de cadre) : apprises et ignorées. Contrôle croisé 1 lecture sur 25.

### 2. Zones liées à la fenêtre de l'HDV — ✅ FAIT (repère « Hôtel de vente »)
- Calibration du titre « Hôtel de vente » (Ctrl+Alt+F10 ×2) : son image sert de repère (`hdv_anchor.png`).
- Avant chaque action, l'outil vérifie que le titre est toujours à sa place (~1 ms). S'il a bougé, il le retrouve sur tout l'écran (~20 ms) et décale toutes les zones et tous les points d'autant.
- Limite : suit un déplacement, pas un changement de taille d'interface (dans ce cas, recalibrer).

---

## 💰 Stratégie de prix

### 3. Prix plancher au lieu d'un simple arrêt — ✅ FAIT (`FLOOR_MODE`, `FLOOR_RATIO`)
- **Problème** : si quelqu'un vend très sous le prix moyen, l'outil s'arrête (lecture « suspecte »).
- **Idée** : appliquer une règle à la place, au choix :
  - ne pas suivre et garder ton prix ;
  - ou se mettre au prix plancher (ex. 70 % du prix moyen).
- **Gain** : pas de vente bradée à cause d'un dumper, et Ctrl+F3 ne s'arrête plus en cours de route.

---

## 📊 Suivi

### 6. Tableau de bord — ✅ FAIT (`dofus_dashboard.py`, bouton « Tableau de bord »)
- Page `dashboard.html` générée depuis l'historique, sans internet : lots et kamas mis en vente, prix modifiés, activité par heure, taille des lots, baisse moyenne, lectures suspectes, dernières actions.
- Limite : l'historique ne contient pas le nom des objets (pas de détail par objet).

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
- Zones qui suivent l'HDV déplacé (repère « Hôtel de vente »).
- Tableau de bord HTML de l'historique.
- Interface à onglets (Raccourcis, Prix, Mes ventes, Calibration, Options).

## ⚠️ Rappel

Ctrl+F3 en boucle et la mise en vente automatique automatisent des actions en jeu : c'est contraire aux CGU d'Ankama et peut mener à un ban. À utiliser en connaissance de cause.
