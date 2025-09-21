# 🪙 Dofus Price Helper   

Un outil Python pour **optimiser vos ventes en Hôtel de Vente sur Dofus**. Il utilise l’OCR (Tesseract) pour lire automatiquement les prix affichés et coller un prix ajusté (undercut configurable).  

🛑 **Disclaimer:** Ce projet n’est pas un bot mais un outil d’assistance. Respectez les conditions d’utilisation du jeu : utilisez-le comme une aide au confort de vente, pas pour automatiser des actions massives.

⚠️ Ce script est un **assistant** (OCR + collage clavier), pas un bot full-auto. À utiliser de manière responsable.

---

## ✨ Fonctionnalités
- Hotkeys pour lire les prix (lots 1 / 10 / 100)
- Collage direct du prix ajusté
- Calibration des zones par raccourci (Ctrl+Alt+F1/F2/F3)
- Historique & options d'undercut
---
## ⌨️ Raccourcis clavier

- **F1 / F2 / F3 → Lire et coller le prix (lots 1, 10, 100)**

- **Ctrl+Alt+F1/F2/F3 → Calibrer une zone prix (placer la souris puis appuyer)**

- **Ctrl+Shift+P → Afficher dans le terminal les prix détectés + leurs undercuts**

- **Ctrl+Shift+M → Afficher la position actuelle de la souris (debug)**

- **Esc → Quitter le script**
---
## 🚀 Installation

### 1. Cloner le projet
```bash
git clone https://github.com/Jul1111/Auto-Dofus-Price-Update
```
#### 1.1 Déplacez vous dans le dossier
```bash
cd dofus-price-helper
```
---
### 2. Créer un environnement virtuel

#### Windows :

```bash
python -m venv venv
```

```bash
.\venv\Scripts\activate
```
#### Linux / macOS :
```bash
python3 -m venv venv
```
```bash
source venv/bin/activatee
```
---
### 3. Installer les dépendances
Un fichier requirements.txt est fourni. Installez les librairies nécessaires avec :

```bash
pip install -r requirements.txt
```
---
### 4. Installer Tesseract OCR

#### Windows : 

**Télécharger [ici](https://github.com/UB-Mannheim/tesseract/wiki)** (par défaut, installez dans **"C:\Program Files\Tesseract-OCR\"**)

#### Linux/macOS :
```bash
sudo apt install tesseract-ocr    # Debian/Ubuntu
brew install tesseract # macOS
```
Dans le script adaptez la ligne si besoin :
```python
TESSERACT_CMD = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
```
---
### ▶️ 5. Lancer le script

Toujours depuis le venv activé :
```bash
python dofus_price_helper_V2.py
```
Une fois lancé, le script tourne en arrière-plan et attend vos raccourcis clavier.

---
### 6. ⚙️ Paramétrage pour votre jeu

- Chaque joueur doit calibrer les zones de prix ***(lots 1/10/100)***, car elles dépendent de votre résolution et interface. 
  - Le calibrage est rapide et sauvegardé automatiquement.
- Ouvrez l’*Hôtel de Vente* → onglet Vente.

- Placez la souris au *centre* du prix du **lot 1**, puis *appuyez* sur ***Ctrl+Alt+F1***.

- Faites de même pour le **lot 10** ***(Ctrl+Alt+F2)*** et le **lot 100** ***(Ctrl+Alt+F3)***.

- Les zones sont enregistrées dans ***dofus_price_helper_config.json***.
  
---
### 💡 Conseils d’utilisation

- **Toujours cliquer dans le champ Prix du lot avant d’appuyer sur F1/F2/F3.**

- **Vérifiez visuellement les prix collés la première fois.**

- **Ajustez la valeur d’undercut dans le script :**
  ```python
  UNDERCUT_MODE  = "fixed"   # ou "percent"
  UNDERCUT_VALUE = 1         # valeur en kamas ou en %
  ```
- **Vous pouvez aussi changer PRICE_W et ROW_H si vos chiffres sont mal capturés.**

---
### 📂 Fichiers importants

- dofus_price_helper_fixed.py → le script principal

- requirements.txt → dépendances Python

- dofus_price_helper_config.json → zones calibrées (générées automatiquement, à ne pas partager)

- captures/ → images debug si DEBUG = True (optionnel)
  
---
### 🛑 Disclaimer

**Ce projet n’est pas un bot mais un outil d’assistance.
Respectez les conditions d’utilisation du jeu : utilisez-le comme une aide au confort de vente, pas pour automatiser des actions massives.**



