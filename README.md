# 🪙 Dofus Price Helper

Un outil Python pour **vendre plus vite à l'Hôtel de Vente de Dofus**. Il lit le tableau « Actuellement en vente » par OCR (Tesseract), calcule un prix juste en dessous (undercut configurable) et le saisit dans « Prix du lot ».

> ⚠️ **Avertissement.** Les conditions d'utilisation d'Ankama interdisent en général les logiciels tiers qui interagissent avec le client de jeu. Ce projet est un assistant (lecture d'écran + collage), pas un bot. Le **collage automatique** et surtout la **mise en vente automatique** sont les fonctions les plus risquées : elles sont **désactivées par défaut**. Vous les utilisez à vos risques.

---
https://github.com/user-attachments/assets/9d1fd908-4398-410b-accb-64e54f98fd78

<img width="974" height="668" alt="image" src="https://github.com/user-attachments/assets/71677131-5761-45e9-bbf2-3984da1a2845" />

---

## ✨ Fonctionnalités

- **Lecture du tableau entier** (lots 1 / 10 / 100 / 1000) en un seul appel OCR. Chaque prix est associé à son lot grâce à la colonne « Lot » : si personne ne vend un lot, rien n'est décalé.
- **Lecture de la quantité sélectionnée** : le prix collé correspond **toujours** à la quantité affichée dans le jeu.
- **F1** : vendre à la quantité affichée (le jeu choisit déjà 1 / 10 / 100 selon votre stock).
- **F2 « Tout vendre »** : met en vente puis recommence **au même prix** en appuyant seulement sur Entrée (le jeu garde le prix affiché). Quand la quantité affichée baisse (ex. 42 objets : 4×10, puis il en reste 2 → lot 1), il calcule le prix du nouveau lot et continue, après avoir vérifié que c'est le même objet (votre dernière vente est en tête de l'ancien lot). Arrêt : stock épuisé, prix en tête qui n'est plus le vôtre (autre objet, concurrent), lecture suspecte, 20 ventes (`SELL_ALL_MAX`) ou pause (Ctrl+Alt+P). Jamais vers un lot plus grand.
- **Prix plancher** (zone « Prix moyen » requise, Ctrl+Alt+F5) : plancher = `FLOOR_RATIO` × prix moyen (70 % par défaut, réglable dans l'interface). Si un concurrent brade en dessous, au choix (`FLOOR_MODE`) :
  - `floor` (défaut) : F1/F2/F3 mettent ton prix **au plancher**, sans suivre le brader ; F2 continue et Ctrl+F3 ne s'arrête plus ; une vente déjà au plancher n'est pas retouchée ;
  - `keep` : F3 garde ton prix actuel (F1/F2 vendent au plancher) ;
  - `stop` : ancien comportement, lecture suspecte si le prix tombe sous `MIN_AVG_RATIO` (50 %) du prix moyen.
- **F2 vérifié par le compteur** (optionnel, Ctrl+Alt+F6) : après chaque mise en vente, le compteur « 21/100 lots en vente » doit avoir augmenté de 1. Sinon F2 s'arrête (« vente non confirmée »). Arrêt aussi quand l'HDV est plein.
- **F3 « Mettre à jour mes ventes »** : dans la liste de vos ventes, sélectionnez une ligne puis F3. Si quelqu'un est moins cher, le nouveau prix est collé puis **Modifier** est validé, et le prix affiché ensuite est vérifié. Si le moins cher c'est vous : rien. Plusieurs lignes du même objet s'alignent sur votre nouveau prix (pas 759, 758, 757…).
- **Ctrl+F3 « toute la liste »** ⚠️ (désactivé : interrupteur dans l'interface, ou `RELIST_AUTO`) : clique chaque ligne visible, met à jour, descend à la molette d'une demi-page (`RELIST_SCROLL_PAGE`) en mesurant de combien la liste a réellement bougé, reprend à la 1re ligne pas encore vue, jusqu'en bas. Départ à la ligne sous la souris si elle est posée sur la liste (sinon en haut) ; arrêt en cours de route = souris laissée sur la dernière ligne traitée, Ctrl+F3 reprend là. Les lignes sont repérées à l'écran (bandes sombres entre elles), même après un défilement à la main. Fenêtre de confirmation du changement de prix : validée par Entrée (`RELIST_CONFIRM_ENTER`). Une modification réordonne la liste : la page est alors reprise depuis la 1re ligne (aucune ligne sautée). Une ligne douteuse est relue une fois, puis laissée telle quelle (listée à la fin, à refaire avec F3) ; arrêt après 3 lignes douteuses de suite, sur une modification non confirmée, ou Ctrl+Alt+P.
- **Lecture rapide des chiffres** (`FAST_DIGITS`) : l'outil apprend tout seul la police du jeu à partir des lectures sûres de Tesseract (`digit_templates.npz`). Dès que les 10 chiffres sont connus, une lecture prend ~5 ms au lieu de ~100-300 ms. Au moindre chiffre douteux, Tesseract reprend la main ; 1 lecture rapide sur 25 est recontrôlée par Tesseract (désaccord = modèles effacés et réappris). « Lire (test) » affiche le moteur utilisé et le nombre de chiffres appris.
- **Les zones suivent l'HDV** (Ctrl+Alt+F10 ×2 sur le titre « Hôtel de vente ») : si vous déplacez la fenêtre de l'HDV, l'outil retrouve le titre à l'écran et décale toutes les zones avant d'agir. Un changement de taille d'interface demande toujours une recalibration.
- **Tableau de bord** (bouton en haut de l'interface, ou `python dofus_dashboard.py`) : page HTML hors ligne tirée de l'historique (lots et kamas mis en vente, prix modifiés, activité par heure, lectures suspectes, dernières actions).
- **Pas d'undercut contre vous-même** : si le prix en tête est celui que vous venez de mettre (même lot, < 30 min, `OWN_PRICE_TTL`), il est réutilisé tel quel.
- **F4** : meilleur prix unitaire **parmi les lots possibles** (≤ quantité affichée, que le jeu met au maximum permis par votre stock). Si c'est un lot plus petit, la popup indique lequel choisir.
- **Lot absent** : prix estimé depuis les autres lots (proposé, jamais validé automatiquement).
- **Icônes ignorées** : les icônes kamas et objets (colorées) sont effacées avant l'OCR, donc la calibration n'a pas besoin d'être précise.
- **Champ « Prix du lot » vidé** (Fin + Retour arrière, le jeu le pré-remplit) puis prix **collé** (Ctrl+V) ; le presse-papier est restauré ensuite.
- **Popup près de la souris** + **son**, **pause**, raccourcis actifs **seulement dans Dofus**.
- **Garde-fous** : confiance OCR, cohérence entre lots, prix toujours inférieur au concurrent.
- **Historique** dans `dofus_price_history.csv`.

---

## ⌨️ Raccourcis clavier

| Touche | Action |
|---|---|
| **F1** | Vendre à la quantité affichée |
| **F2** | Tout vendre au même prix (arrêt automatique) |
| **F4** | Meilleur lot (prix unitaire le plus haut) |
| **Même touche 2×** (< 3 s) | Forcer une lecture suspecte |
| **Ctrl+Alt+F1** (×2) | Calibrer le tableau : coin haut-gauche, puis coin bas-droit |
| **Ctrl+Alt+F2** (×2) | Calibrer le menu Quantité : coin haut-gauche, puis coin bas-droit |
| **Ctrl+Alt+F3** | Calibrer le champ « Prix du lot » |
| **Ctrl+Alt+F4** | Calibrer le bouton « Mettre en vente » (seulement si `VALIDATE_METHOD` = `click`) |
| **Ctrl+Alt+F5** (×2) | (optionnel) Calibrer la valeur sous « PRIX MOYEN » (chiffres + icône kamas) |
| **Ctrl+Alt+F6** (×2) | (optionnel) Calibrer le compteur « 21/100 lots en vente » (toute la ligne) |
| **F3** | Mes ventes : mettre à jour la ligne sélectionnée |
| **Ctrl+F3** | Mes ventes : toute la liste, avec scroll (`RELIST_AUTO` = `true` requis) |
| **Ctrl+Alt+F7** (×2) | Mes ventes : calibrer le texte du champ « Prix du lot » (votre prix actuel) |
| **Ctrl+Alt+F8** | Mes ventes : calibrer le bouton « Modifier » (sinon Entrée) |
| **Ctrl+Alt+F9** (×2) | Mes ventes : centre de la 1re ligne, puis de la 2e ligne de la liste |
| **Ctrl+Alt+V** | Afficher les zones calibrées |
| **Ctrl+Alt+P** | Pause / reprise |
| **Ctrl+Alt+Q** | Quitter (version CLI) |

Tous les raccourcis se changent dans `dofus_price_helper_config.json`, clé `HOTKEYS`.

---

## 🚀 Installation

### 1. Cloner le projet
```bash
git clone https://github.com/Jul1111/Auto-Dofus-Price-Update
cd Auto-Dofus-Price-Update
```

### 2. Créer un environnement virtuel

Windows :
```bash
python -m venv venv
.\venv\Scripts\activate
```

Linux / macOS :
```bash
python3 -m venv venv
source venv/bin/activate
```

### 3. Installer les dépendances
```bash
pip install -r requirements.txt
```

### 4. Installer Tesseract OCR

- **Windows** : [télécharger ici](https://github.com/UB-Mannheim/tesseract/wiki) (dossier par défaut : `C:\Program Files\Tesseract-OCR\`)
- **Linux** : `sudo apt install tesseract-ocr`
- **macOS** : `brew install tesseract`

Si Tesseract est installé ailleurs, modifiez `TESSERACT_CMD` dans la config. S'il est dans le PATH, il est trouvé automatiquement.

### 5. Lancer

Interface graphique (recommandé) :
```bash
python dofus_price_helper_psg.py
```

Ligne de commande :
```bash
python dofus_price_helperV2.py          # --debug pour enregistrer les images OCR dans captures/
```

ℹ️ Le module `keyboard` a besoin des droits administrateur sur certains PC Windows, et de root sous Linux.

---

## ⚙️ Premier réglage (1 minute)

Ouvrez **l'Hôtel de Vente** → onglet **Vente**, avec un objet sélectionné.

1. **Tableau** : souris sur le coin **haut-gauche** de la colonne « Lot » (ligne du lot 1) → **Ctrl+Alt+F1**. Puis souris sur le coin **bas-droit** de la colonne « Prix » (ligne du lot 1000) → **Ctrl+Alt+F1**. Pas besoin d'être précis : les icônes sont ignorées.
2. **Quantité** : même chose sur le menu « Quantité » (coin haut-gauche puis bas-droit) → **Ctrl+Alt+F2** deux fois.
3. **Prix du lot** (recommandé) : souris sur le champ → **Ctrl+Alt+F3**. L'option « Cliquer Prix du lot » s'active toute seule.
4. **Mettre en vente** : inutile par défaut, la validation se fait avec **Entrée** (`"VALIDATE_METHOD": "enter"`). Pour cliquer le bouton à la place : `"click"` + calibrer avec **Ctrl+Alt+F4**.
5. **Prix moyen** (optionnel) : coin haut-gauche puis bas-droit du nombre sous « PRIX MOYEN » → **Ctrl+Alt+F5** deux fois.
6. **Compteur de lots** (optionnel, conseillé pour F2) : toute la ligne « 21/100 lots en vente », avec un peu de marge en haut et en bas → **Ctrl+Alt+F6** deux fois. Une zone qui coupe les chiffres peut lire « 91 » au lieu de « 21 » : F2 s'arrêtera alors après la 1re vente (sans risque), recalibrez plus large.
7. **Ctrl+Alt+V** pour voir les zones, puis **Lire (test)** dans l'interface : la quantité et les 4 prix doivent être corrects.

Les boutons de calibration de l'interface font la même chose, avec un compte à rebours de 3 s pour placer la souris.

### Mes ventes (F3)

Le tableau « Actuellement en vente », la quantité et le prix moyen sont aux mêmes endroits que dans l'onglet vente : rien à refaire. En plus :

1. **Ton prix** : rien à faire si le champ « Prix du lot » est calibré (**Ctrl+Alt+F3**, le carré rouge) : votre prix est cherché autour de ce point. La zone **Ctrl+Alt+F7** n'est qu'un secours ; elle doit contenir le champ « Prix du lot » (à gauche), pas la liste.
2. **Modifier** : souris sur le bouton → **Ctrl+Alt+F8**. Sans calibration, F3 appuie sur Entrée.
3. Pour Ctrl+F3 seulement : souris au centre de la 1re ligne de la liste → **Ctrl+Alt+F9**, puis au centre de la 2e ligne → **Ctrl+Alt+F9**. Réglez `RELIST_ROWS` (lignes entièrement visibles, 10 par défaut), puis activez l'interrupteur « CTRL+F3 : toute la liste » (ou `"RELIST_AUTO": true`).

Chaque modification de prix peut être taxée par le jeu : ne relancez pas en boucle pour 1 kama.

---

### Interface

Onglets **Raccourcis** (aide + vente rapide), **Prix** (undercut, arrondi, plancher), **Mes ventes** (Ctrl+F3, défilement, garde-fou de lignes), **Calibration** (état ✓/✗ de chaque zone + bouton), **Options** (focus, sons, lecture rapide, réapprendre les chiffres). À droite : dernière lecture (quantité, prix par lot et par objet, prix moyen, ton prix, moteur). En-tête : état actif/pause, chiffres appris, compteurs de la session.

---

## ⚡ Vendre plus vite

| Niveau | Options (section **Vente rapide**) | Ce que vous faites par objet |
|---|---|---|
| Prudent (défaut) | aucune | F1 → clic sur « Prix du lot » → Ctrl+A → Ctrl+V → Mettre en vente |
| Rapide | **Coller auto** + **Cliquer Prix du lot** | F1 → vérifier la popup → Mettre en vente |
| Une touche ⚠️ | + **Mettre en vente auto** | F1 |

Une lecture **suspecte** (confiance faible, écart anormal entre lots, lot absent, quantité non vérifiée) n'est **jamais** mise en vente automatiquement : le prix est seulement copié, une popup jaune s'affiche, et il faut ré-appuyer pour le coller.

Le champ est vidé avec Fin + Retour arrière (`"CLEAR_METHOD": "backspace"`) puis le prix est collé (`"INPUT_METHOD": "paste"`). La frappe chiffre par chiffre (`"type"`) existe mais ne marche pas en AZERTY (la touche « 6 » donne « - »).

---

## 🛡️ Garde-fous

| Contrôle | Réglage | Défaut |
|---|---|---|
| Prix collé = prix du lot de la **quantité affichée** | `QTY_REGION` | obligatoire pour F1 |
| Confiance OCR minimale | `MIN_CONFIDENCE` | 60 |
| Écart max de prix unitaire entre lots | `MAX_RATIO` | 5 |
| Prix par objet ≥ 50 % du « Prix moyen » | `MIN_AVG_RATIO` (0 = off) | 0.5 |
| F2 : compteur de lots = avant + nombre de ventes | `VERIFY_COUNT` | true |
| Délai pour forcer en ré-appuyant | `CONFIRM_WINDOW` | 3 s |
| Prix toujours < prix lu (même avec l'arrondi) | — | toujours |
| Raccourcis seulement dans le jeu (exe **ou** titre) | `WINDOW_PROCESS` / `WINDOW_TITLE` | `dofus` / ` - Release` |
| Vidage du champ puis collage | `CLEAR_METHOD` / `INPUT_METHOD` | `backspace` / `paste` |

---

## 📂 Fichiers

| Fichier | Rôle |
|---|---|
| `dofus_core.py` | Logique partagée (OCR, calcul, garde-fous, saisie, config, historique) |
| `dofus_price_helper_psg.py` | Interface graphique |
| `dofus_price_helperV2.py` | Version ligne de commande |
| `dofus_price_helper_config.example.json` | Exemple de config avec toutes les options |
| `dofus_price_helper_config.json` | Votre config (créée automatiquement, **non versionnée**) |
| `dofus_price_history.csv` | Historique des ventes (non versionné) |
| `tests/` | Tests, dont un OCR réel sur une capture de l'HDV (`pip install -r requirements-dev.txt` puis `pytest`) |

---

## 🛑 Disclaimer

**Ce projet n'est pas un bot mais un outil d'assistance. Respectez les conditions d'utilisation du jeu : utilisez-le comme une aide au confort de vente, pas pour automatiser des actions massives.**
