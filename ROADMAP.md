# 🗺️ Roadmap — Dofus Price Helper

Pistes d'amélioration, de la plus utile à la moins utile.
Tout est fait.

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

### 3. Calibration automatique — ✅ FAIT
- Un clic (ou Ctrl+Alt+F12), HDV ouvert sur l'onglet Vente : l'outil trouve l'HDV à l'écran à n'importe quelle taille (résolution, échelle de l'interface) et place toutes les zones.
- Modèle de l'HDV (`modele_hdv/`, généré par `packaging/build_hdv_model.py`) : position de chaque zone par rapport au titre, mesurée sur une capture 2560 x 1440 à 90 %. Vérifié sur 1920 x 1080, 1920 x 1200 et 2560 x 1440 à 80 / 90 / 100 % : l'HDV grandit d'un bloc, à 5 px près ; les textes fixes (« Prix du lot », « PRIX MOYEN »…) rattrapent ces écarts.
- Limite : Dofus 3 en **français**, même version du jeu que le modèle. Si une mise à jour change l'HDV, refaire une capture de référence et relancer le script.

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

### 6. Tableau de bord — ❌ RETIRÉ (peu utile)
- Retiré avec la lecture du nom des objets par Tesseract. L'image du nom sert maintenant à reconnaître tes propres ventes (pas d'undercut contre toi-même).
- Ancienne version : onglet calculé depuis l'historique (`dofus_dashboard.py`), actualisé à chaque action : lots et kamas mis en vente, prix modifiés, activité par heure, taille des lots, baisse moyenne, lectures suspectes, dernières actions.
- Nom des objets lu en arrière-plan (`dofus_items.py`) → détail par objet : courbe « moins cher lu / ton prix » dans le temps et liste des objets.

### 7. Version .exe — ✅ FAIT (zip construit par GitHub)
- `DofusPriceHelper.exe` (PyInstaller, mode dossier : démarrage rapide, moins d'alertes antivirus), Tesseract inclus (utilisé seulement si aucun Tesseract 5+ n'est installé).
- Réglages dans `%APPDATA%` : gardés d'une version à l'autre.
- GitHub Actions : tests + zip à chaque PR, publication dans Releases à chaque tag `v*`.

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
- Tes propres ventes reconnues (image du nom + lot, gardées 2 jours) : Ctrl+F3 ne baisse plus tes ventes à chaque passage.
- Raccourcis modifiables dans l'interface ; Ctrl+F3 détaille chaque ligne dans le journal.
- Interface à onglets (Raccourcis, Prix, Mes ventes, Calibration, Options).
- Barre d'état (pause, profil, calibration, HDV), journal filtrable avec blocs Ctrl+F3 repliables, historique des résumés, aperçu des prix, mode compact, aide au survol, taille du texte.
- Nouveau thème (palette, police Segoe UI, cartes) et style « Verre » : flou du jeu derrière l'outil, teinte réglable.
- Prix relu dans « Prix du lot » avant chaque validation (F1, F2, F3) : jamais un mauvais collage validé.
- F2 sans pause fixe : attend le changement à l'écran (compteur, quantité, tableau).
- F1 intelligent : vend ou met à jour selon le panneau (« Mettre en vente » ou « Retirer | Modifier »).
- Assistant de calibration pas à pas avec vérification finale.
- Bandeau de résultat fixe au-dessus de l'HDV.

## ⚠️ Rappel

Ctrl+F3 en boucle et la mise en vente automatique automatisent des actions en jeu : c'est contraire aux CGU d'Ankama et peut mener à un ban. À utiliser en connaissance de cause.
