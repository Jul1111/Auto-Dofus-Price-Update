# 🪙 Dofus Price Helper

Assistant Python pour **vendre plus vite et sans erreur à l'Hôtel de Vente de Dofus**.
Il lit l'écran (OCR), calcule un prix juste sous le moins cher, le colle dans « Prix du lot », le vérifie, puis valide.

> ⚠️ Les CGU d'Ankama interdisent en général les logiciels tiers qui interagissent avec le jeu. La mise en vente automatique et le parcours de toute la liste (Ctrl+F3) sont les fonctions les plus risquées : **désactivées par défaut**, à vos risques.

---

## 🎬 Présentation
> <img width="800" height="268" alt="Presentation_Dofus_Helper-ezgif com-video-to-gif-converter" src="https://github.com/user-attachments/assets/c0b4e31f-562e-45e9-8127-4ed8c1cc7a45" />







| | |
|---|---|
| <!-- CAPTURE 1 — docs/interface.png : l'interface complète, onglet « Raccourcis », panneau « Dernière lecture » rempli après un F1. --> Interface <img width="1754" height="843" alt="Capture d&#39;écran 2026-11-14 155130" src="https://github.com/user-attachments/assets/2ed70d1f-35db-4ea8-a0f0-6fa96d48cc62" />

| <!-- CAPTURE 2 — docs/hdv-vente.png : l'HDV du jeu, onglet Vente, avec le bandeau du résultat affiché au-dessus. --> Vente
| <!-- CAPTURE 3 — docs/tableau-de-bord.png : onglet « Tableau de bord » avec un objet choisi dans « Prix par objet ». --> 📷 *Tableau de bord* | <!-- CAPTURE 4 — docs/assistant.png : l'assistant de calibration, page « Vérification » avec les ✓ après « Tester ». --> 

<!-- Pour afficher une capture : remplacer « 📷 *…* » par ![Interface](docs/interface.png) -->

---

## ✨ Ce qu'il fait

- **F1 intelligent** : objet de l'inventaire sélectionné → **vend** ; une de tes ventes sélectionnée → **met à jour son prix**.
- **F2 « Tout vendre »** : remet en vente au même prix tant que c'est sûr, passe au lot inférieur quand le stock baisse, s'arrête dès que quelque chose change.
- **Ctrl+F3** : met à jour **toute la liste** de tes ventes, avec défilement (désactivé par défaut).
- **Jamais un mauvais prix** : le champ « Prix du lot » est relu avant chaque validation ; prix plancher (70 % du prix moyen) contre les vendeurs qui bradent ; lectures douteuses bloquées.
- **Rapide** : chiffres du jeu appris tout seuls (~5 ms par lecture), attente des changements d'écran plutôt que des pauses fixes.
- **Pratique** : assistant de calibration, zones qui suivent l'HDV si tu le déplaces, bandeau de résultat au-dessus de l'HDV, tableau de bord avec prix par objet.

---

## 🚀 Installation

```bash
git clone https://github.com/Jul1111/Auto-Dofus-Price-Update
cd Auto-Dofus-Price-Update
python -m venv venv
.\venv\Scripts\activate          # Linux/macOS : source venv/bin/activate
pip install -r requirements.txt
```

**Tesseract OCR** : [Windows](https://github.com/UB-Mannheim/tesseract/wiki) (cocher la langue **French** à l'installation, pour les noms d'objets) · Linux `sudo apt install tesseract-ocr tesseract-ocr-fra` · macOS `brew install tesseract tesseract-lang`.

```bash
python dofus_price_helper_psg.py   # interface (recommandé)
python dofus_price_helperV2.py     # ligne de commande
```

ℹ️ Le module `keyboard` demande parfois les droits administrateur (Windows) ou root (Linux).

---

## 🧭 Premier lancement

L'**assistant de calibration** s'ouvre tout seul (sinon : onglet *Calibration* → *Ouvrir l'assistant*). Il te guide zone par zone, puis teste tout et affiche ✓ / ✗.

Obligatoire : tableau « Actuellement en vente », menu « Quantité », champ « Prix du lot ».
Conseillé : titre « Hôtel de vente » (suivi de la fenêtre), prix moyen (plancher), bouton « Modifier » (F1 intelligent, F3).

---

## ⌨️ Raccourcis

| Touche | Action |
|---|---|
| **F1** | Vendre (objet de l'inventaire) **ou** mettre à jour (une de tes ventes) |
| **F2** | Tout vendre au même prix |
| **F3** | Mettre à jour la vente sélectionnée |
| **Ctrl+F3** | Mettre à jour toute la liste ⚠️ (à activer dans *Mes ventes*) |
| **F4** | Meilleur lot (prix par objet le plus haut) |
| même touche ×2 | Forcer une lecture jugée suspecte |
| **Ctrl+Alt+P** | Pause / reprise (arrête aussi les boucles) |
| **Ctrl+Alt+V** | Afficher les zones calibrées |

Les raccourcis de calibration (Ctrl+Alt+F1 à F11) sont listés dans l'onglet *Calibration*. Tout est modifiable dans `dofus_price_helper_config.json` (`HOTKEYS`).

---

## 🛡️ Sécurité des prix

| Situation | Ce que fait l'outil |
|---|---|
| Lecture incertaine, prix incohérent entre lots | Copie seulement, ré-appuyer pour forcer |
| Champ « Prix du lot » ≠ prix calculé | **Ne valide pas** |
| Concurrent sous le plancher | Vend au plancher (ou garde ton prix, ou s'arrête : onglet *Prix*) |
| Le moins cher, c'est déjà toi | Ne baisse pas |
| F2 : compteur de lots qui n'augmente pas | S'arrête |

---

## 📂 Fichiers

| Fichier | Rôle |
|---|---|
| `dofus_price_helper_psg.py` | Interface |
| `dofus_price_helperV2.py` | Version ligne de commande |
| `dofus_core.py` | Moteur (lecture, prix, saisie, garde-fous) |
| `dofus_digits.py` / `dofus_items.py` | Lecture rapide des chiffres / nom des objets |
| `dofus_dashboard.py` | Calculs du tableau de bord |
| `dofus_price_helper_config.json` | Réglages (créé au 1er lancement) |
| `dofus_price_history.csv` | Historique de tes actions |

Tests : `pip install -r requirements-dev.txt` puis `pytest`.

---

## 🛑 Disclaimer

Projet non affilié à Ankama. Utilisation à vos risques.
