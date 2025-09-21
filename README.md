# 🪙 Dofus Price Helper   

Un outil Python pour **optimiser vos ventes en Hôtel de Vente sur Dofus**. Il utilise l’OCR (Tesseract) pour lire automatiquement les prix affichés et coller un prix ajusté (undercut configurable).  

🛑 **Disclaimer:** Ce projet n’est pas un bot mais un outil d’assistance. Respectez les conditions d’utilisation du jeu : utilisez-le comme une aide au confort de vente, pas pour automatiser des actions massives.

⚠️ Ce script est un **assistant** (OCR + collage clavier), pas un bot full-auto. À utiliser de manière responsable.

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
python dofus_price_helper_fixed.py
```
Une fois lancé, le script tourne en arrière-plan et attend vos raccourcis clavier.

