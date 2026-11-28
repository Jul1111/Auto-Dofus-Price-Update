"""Réglages (Config) : chargement, enregistrement sûr, profils."""
from __future__ import annotations

import json
import os
import shutil
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

from .base import CONFIG_PATH, CONFIG_VERSION
from .anchor import anchor_path, DEFAULT_PROFILE, PROFILE_FIELDS, profile_name_problem


# --------------------------------------------------------------------------
# Config
# --------------------------------------------------------------------------
DEFAULT_HOTKEYS = {
    "sell": "f1",                    # vendre à la quantité affichée dans le jeu
    "sell_all": "f2",                # vendre tout le stock de ce lot au même prix (Entrée répétée)
    "optimize": "f4",                # meilleur lot (demande de changer la quantité si besoin)
    "calibrate_table": "ctrl+alt+f1",  # 2 appuis : coin haut-gauche puis bas-droit
    "calibrate_qty": "ctrl+alt+f2",    # 2 appuis
    "calibrate_field": "ctrl+alt+f3",  # 1 appui sur « Prix du lot »
    "calibrate_button": "ctrl+alt+f4", # 1 appui sur « Mettre en vente »
    "calibrate_avg": "ctrl+alt+f5",    # 2 appuis : valeur du « Prix moyen » (optionnel)
    "calibrate_count": "ctrl+alt+f6",  # 2 appuis : compteur « 21/100 lots en vente » (optionnel)
    "relist": "f3",                  # mes ventes : remettre la ligne sélectionnée sous le moins cher
    "relist_all": "ctrl+f3",         # mes ventes : toutes les lignes (RELIST_AUTO doit être activé)
    "calibrate_mine": "ctrl+alt+f7",   # 2 appuis : texte du champ « Prix du lot » (ton prix actuel)
    "calibrate_modify": "ctrl+alt+f8", # 1 appui sur « Modifier »
    "calibrate_rows": "ctrl+alt+f9",   # 2 appuis : 1re ligne puis 2e ligne de la liste de tes ventes
    "calibrate_anchor": "ctrl+alt+f10",  # 2 appuis : titre « Hôtel de vente » (les zones suivent l'HDV)
    "calibrate_name": "ctrl+alt+f11",    # 2 appuis : nom de l'objet (optionnel, sinon déduit)
    "calibrate_auto": "ctrl+alt+f12",    # calibration automatique (HDV ouvert, onglet Vente)
    "show_zones": "ctrl+alt+v",
    "pause": "ctrl+alt+p",
    "cheatsheet": "ctrl+alt+h",      # aide-mémoire des touches par-dessus le jeu
    "hud": "ctrl+alt+u",             # afficher / cacher le HUD discret par-dessus le jeu
    "toggle_window": "ctrl+alt+o",   # afficher / cacher la fenêtre de l'outil (depuis le jeu)
    "quit": "ctrl+alt+q",
}


def _copy(obj):
    return json.loads(json.dumps(obj))


_CONFIG_LOCK = threading.RLock()


def keep_unreadable(path: Path) -> Optional[Path]:
    """Copie d'un fichier de réglages illisible (« …illisible-20261127-1530.json »), pour
    pouvoir le réparer ou l'envoyer. None si impossible."""
    try:
        keep = path.with_name(f"{path.stem}.illisible-{time.strftime('%Y%m%d-%H%M%S')}{path.suffix}")
        shutil.copy2(path, keep)
        return keep
    except OSError:
        return None


# ambiances valides (même liste que gui/style.py : AMBIENCES, vérifiée par les tests)
AMBIENCE_KEYS = ("night", "amber", "forest", "ocean", "dofus_standard", "dofus_azur", "dofus_pourpre",
                 "dofus_cendre", "dofus_terre", "dofus_lavande", "dofus_orchidee", "dofus_jade", "dofus_lagon",
                 "dofus_sylve", "dofus_braise")


@dataclass
class Config:
    # Les noms en MAJUSCULES dans le JSON = nom du champ en majuscules.
    config_version: int = CONFIG_VERSION
    tesseract_cmd: str = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
    lots: List[int] = field(default_factory=lambda: [1, 10, 100, 1000])

    # Zones (coordonnées écran)
    table_region: Optional[List[int]] = None  # colonnes Lot + Prix, SANS icônes objet/kamas
    qty_region: Optional[List[int]] = None    # texte du menu Quantité, SANS la flèche
    price_field: Optional[List[int]] = None   # (x, y) champ « Prix du lot »
    sell_button: Optional[List[int]] = None   # (x, y) bouton « Mettre en vente »
    avg_region: Optional[List[int]] = None    # chiffres sous « PRIX MOYEN » (optionnel)
    count_region: Optional[List[int]] = None  # texte « 21/100 lots en vente » (optionnel)
    anchor_region: Optional[List[int]] = None # repère : titre « Hôtel de vente » (zones suivent l'HDV)
    name_region: Optional[List[int]] = None   # nom de l'objet (reconnaître tes ventes ; sinon déduit)
    mine_region: Optional[List[int]] = None   # mes ventes : texte du champ « Prix du lot »
    modify_button: Optional[List[int]] = None # mes ventes : (x, y) bouton « Modifier »
    relist_row: Optional[List[int]] = None    # mes ventes : (x, y) centre de la 1re ligne visible
    relist_step: int = 0                      # mes ventes : hauteur d'une ligne (px)
    table_split: float = 0.45  # séparation colonne Lot / colonne Prix (fraction de largeur)
    scale: int = 2
    fast_digits: bool = True          # lecture rapide des chiffres (apprise), Tesseract en secours

    # Prix
    undercut_mode: str = "fixed"      # "fixed" | "percent"
    undercut_value: float = 1.0       # kamas (fixed) ou % (percent)
    min_price: int = 1
    rounding: str = "none"            # "none" | "down_10" | "down_100" | "end_9"
    tie_tolerance: float = 0.01       # ex aequo (prix unitaire) -> plus petit lot

    # Garde-fous
    min_confidence: float = 60.0      # confiance OCR mini (0-100) pour coller auto
    max_ratio: float = 5.0            # écart max de prix unitaire entre lots
    confirm_window: float = 3.0       # ré-appuyer dans ce délai = forcer
    own_price_ttl: float = 1800.0     # s : objet non reconnu -> prix en tête = ton dernier prix (même lot)
    min_avg_ratio: float = 0.5        # FLOOR_MODE "stop" : prix unitaire < 50 % du prix moyen = suspect
    floor_mode: str = "floor"         # concurrent sous le plancher : "floor" (se mettre au plancher)
                                      # | "keep" (garder ton prix en F3) | "stop" (suspect, arrêt)
    floor_ratio: float = 0.7          # plancher = 70 % du « Prix moyen » (par objet) ; 0 = off

    # « Tout vendre » (F2)
    sell_all_max: int = 20            # nombre max de mises en vente par appui
    sell_all_delay: float = 0.6       # s entre deux mises en vente (laisser le jeu se mettre à jour)
    verify_count: bool = True         # F2 : vérifier chaque vente avec le compteur « x/100 lots »

    # « Mettre à jour mes ventes » (F3 / Ctrl+F3)
    relist_auto: bool = False         # Ctrl+F3 : parcourir toute la liste seul (risque CGU : à toi de voir)
    relist_rows: int = 10             # lignes entièrement visibles dans la liste
    relist_scroll_max: int = 40       # crans de molette max pour passer une page
    relist_scroll_page: float = 0.5   # défilement visé : 0.5 = une demi-page entre deux lectures
    relist_max: int = 400             # garde-fou : lignes lues max par appui (boucle infinie impossible)
    relist_delay: float = 0.5         # s après un clic sur une ligne / une modification
    relist_confirm_enter: bool = True # « Modifier » : Entrée si une fenêtre de confirmation reste ouverte
    relist_force_suspect: bool = False  # mes ventes : modifier même si le PRIX est suspect (marché qui chute)
    relist_summary: bool = True       # Ctrl+F3 : fenêtre de résumé (prix modifiés, lignes douteuses)
    auto_recalibrate: bool = True     # repère perdu (taille de l'HDV changée) : calibration automatique

    # Saisie
    auto_paste: bool = False          # coller automatiquement (sinon copie seule)
    click_field: bool = False         # cliquer sur « Prix du lot » avant de coller
    input_method: str = "paste"       # "paste" (Ctrl+V, marche en jeu) | "type" (touches : faux en AZERTY)
    clear_method: str = "backspace"   # "backspace" (Fin + effacer) | "ctrl_a" ; le champ est pré-rempli
    auto_validate: bool = False       # mettre en vente automatiquement après collage
    verify_before_enter: bool = True  # relire « Prix du lot » avant de valider : jamais un mauvais prix
    smart_f1: bool = True             # F1 : vend (objet de l'inventaire) OU met à jour (une de tes ventes)
    always_on_top: bool = True        # fenêtre de l'outil toujours au-dessus du jeu
    check_updates: bool = True        # au démarrage : nouvelle version publiée sur GitHub ?
    validate_method: str = "enter"    # "enter" (rapide, souris immobile) | "click" (bouton calibré)
    restore_clipboard: bool = True

    # Confort
    # Hotkeys actifs seulement si la fenêtre active est le jeu :
    # nom de l'exe contient WINDOW_PROCESS, ou titre contient WINDOW_TITLE.
    window_process: str = "dofus"     # Dofus.exe
    window_title: str = " - Release"  # titre : « Perso - Classe - version - Release »
    require_focus: bool = True
    sound: bool = True
    calib_countdown: int = 3          # secondes avant calibration via bouton UI
    ui_scale: float = 1.0             # taille du texte / des éléments de l'interface (1.0 = 100 %)
    ui_style: str = "classic"         # "classic" (opaque) | "glass" (flou du jeu derrière, Windows)
    glass_opacity: float = 0.6        # teinte du verre : 0.3 (très transparent) .. 0.95 (presque opaque)
    window_geometry: str = ""         # taille et position de la fenêtre (mémorisées à la fermeture)
    notify: bool = True               # notification Windows à la fin d'un long F2 / Ctrl+F3 (outil en arrière-plan)
    first_steps: List[str] = field(default_factory=list)   # premiers pas faits : "read", "sell"
    sound_volume: float = 0.5         # volume des sons (0..1)
    theme: str = "dark"               # "dark" | "light" | "system" (comme Windows)
    accent: str = "blue"              # couleur d'accent (gui/style.py : ACCENTS)
    ambience: str = "night"           # ambiance du thème sombre (AMBIENCE_KEYS ; dofus_* = thèmes du jeu)
    animations: bool = True           # fondus des popups, barre de progression douce
    tray: bool = True                 # icône dans la zone de notification (près de l'horloge)
    tray_minimize: bool = True        # (toujours actif) réduire la fenêtre = la cacher près de l'horloge
    calib_window: Optional[List[int]] = None   # fenêtre du jeu (x, y, l, h) quand la calibration marchait
    cheatsheet_pos: Optional[List[int]] = None # aide-mémoire : position choisie en le déplaçant
    auto_profile: bool = True         # changer de profil tout seul selon le personnage (titre du jeu)
    character_profiles: Dict = field(default_factory=dict)   # personnage -> profil de calibration
    hud: bool = True                  # HUD par-dessus le jeu (les clics le traversent) : résultat des actions
    hud_pos: Optional[List[int]] = None        # position du HUD (choisie avec « Déplacer »)
    hud_size: str = "normal"          # HUD : "small" | "normal" | "large"
    hud_shape: str = "card"           # HUD : "card" (carte) | "pill" (pilule) | "minimal" (texte + liseré)
    hud_opacity: float = 0.9          # HUD : opacité (0.5 .. 1)
    hud_content: str = "both"         # HUD : "state" (état seul) | "action" (dernière action) | "both"
    hud_history: bool = False         # HUD : les 3 derniers prix traités, sous la ligne principale
    hud_autohide: int = 0             # HUD : s sans action avant qu'il s'estompe (0 = jamais)
    hud_alt: bool = True              # HUD : Alt maintenu = HUD cliquable (arrêter, copier le prix, ouvrir)
    profile_colors: Dict = field(default_factory=dict)       # profil -> couleur (HUD, pastille, icône)
    last_seen_version: str = ""       # « Quoi de neuf » déjà montré pour cette version
    tour_done: bool = False           # visite guidée vue (1er lancement) ; se relance depuis l'Accueil

    hotkeys: Dict = field(default_factory=lambda: _copy(DEFAULT_HOTKEYS))

    # Profils de calibration (un par HDV / personnage) : zones, points, repère.
    # Les champs ci-dessus sont ceux du profil ACTIF ; `profiles` garde tous les profils.
    profile: str = "Principal"
    profiles: Dict = field(default_factory=dict)

    # ---------- I/O ----------
    @classmethod
    def load(cls, path: Path = CONFIG_PATH) -> "Config":
        cfg = cls()
        if not path.exists():
            return cfg
        try:
            data = json.loads(path.read_text(encoding="utf-8")) or {}
            if not isinstance(data, dict):
                raise ValueError("contenu inattendu")
        except (OSError, ValueError) as e:      # JSONDecodeError en fait partie
            # Valeurs par défaut… qui seraient enregistrées par-dessus à la fermeture : calibration
            # et profils perdus pour de bon. Le fichier illisible est donc gardé de côté.
            keep = keep_unreadable(path)
            print(f"[Config] Lecture impossible ({e}), valeurs par défaut."
                  + (f" Ancien fichier gardé : {keep.name}." if keep else ""))
            return cfg
        old = int(data.get("CONFIG_VERSION", 1)) < 2  # v1 seulement : raccourcis incompatibles
        for name in cfg.__dataclass_fields__:
            key = name.upper()
            if key not in data or name == "config_version":
                continue
            if old and name == "hotkeys":
                continue  # v1 : raccourcis par lot, incompatibles -> défauts v2
            default = getattr(cfg, name)
            value = data[key]
            try:
                if isinstance(default, bool):
                    value = bool(value)
                elif isinstance(default, int) and not isinstance(default, bool):
                    value = int(value)
                elif isinstance(default, float):
                    value = float(value)
            except (TypeError, ValueError):
                print(f"[Config] Valeur invalide pour {key}: {value!r}, ignorée.")
                continue
            setattr(cfg, name, value)
        hk = _copy(DEFAULT_HOTKEYS)
        if isinstance(cfg.hotkeys, dict):       # fichier modifié à la main : jamais de plantage
            hk.update({k: v for k, v in cfg.hotkeys.items() if isinstance(v, str)})
        cfg.hotkeys = hk
        lots = set()
        for l in cfg.lots if isinstance(cfg.lots, list) else []:
            try:
                if int(l) > 0:
                    lots.add(int(l))
            except (TypeError, ValueError):
                pass
        cfg.lots = sorted(lots) or cls().lots
        if "WINDOW_PROCESS" not in data and cfg.window_title == "Dofus":
            cfg.window_title = cls.window_title  # ancien défaut v1, faux
        if int(data.get("CONFIG_VERSION", 1)) < 4:
            # v4 : la frappe chiffre par chiffre ne marche pas en AZERTY (touche "6" = "-")
            # -> collage Ctrl+V (validé en jeu) ; le champ est vidé par Fin + Retour arrière.
            cfg.input_method, cfg.clear_method = "paste", "backspace"
        if int(data.get("CONFIG_VERSION", 1)) < 5 and cfg.relist_max == 120:
            cfg.relist_max = cls.relist_max  # v5 : 120 était trop bas pour une liste de 100+ lots
        if int(data.get("CONFIG_VERSION", 1)) < 6:
            cfg.hud = True   # v6 : le HUD remplace le popup / bandeau de résultat et le mode compact
        if int(data.get("CONFIG_VERSION", 1)) < 7:
            cfg.tour_done = True   # v7 : visite guidée réservée aux nouvelles installations
        if cfg.hud_autohide not in (0, 10, 30, 60):
            cfg.hud_autohide = 0
        if cfg.hud_content not in ("state", "action", "both", "dot"):
            cfg.hud_content = "both"
        if cfg.ambience not in AMBIENCE_KEYS:
            cfg.ambience = "night"
        if cfg.hud_shape not in ("card", "pill", "minimal"):
            cfg.hud_shape = "card"
        if not isinstance(cfg.profile_colors, dict):
            cfg.profile_colors = {}
        cfg.profile_colors = {str(k): v for k, v in cfg.profile_colors.items() if isinstance(v, str)}
        if not isinstance(cfg.character_profiles, dict):
            cfg.character_profiles = {}
        cfg.character_profiles = {str(k): str(v) for k, v in cfg.character_profiles.items()
                                  if isinstance(v, str) and str(k).strip()}
        if not isinstance(cfg.profiles, dict):
            cfg.profiles = {}
        cfg.profiles = {str(k): v for k, v in cfg.profiles.items() if isinstance(v, dict)}
        if not isinstance(cfg.profile, str) or not cfg.profile.strip():
            cfg.profile = DEFAULT_PROFILE
        cfg.config_version = CONFIG_VERSION
        return cfg

    # ---------- profils de calibration ----------
    def profile_data(self) -> dict:
        return {f: _copy(getattr(self, f)) for f in PROFILE_FIELDS}

    def profile_names(self) -> List[str]:
        names = set(self.profiles) | {self.profile}
        return sorted(names, key=lambda n: (n != DEFAULT_PROFILE, n.casefold()))

    def switch_profile(self, name: str) -> None:
        """Active le profil `name` (le profil actuel est gardé tel quel)."""
        if name == self.profile:
            return
        if name not in self.profiles:
            raise KeyError(f"profil inconnu : {name}")
        self.profiles[self.profile] = self.profile_data()
        data, defaults = self.profiles[name], Config()
        for f in PROFILE_FIELDS:
            setattr(self, f, _copy(data.get(f, getattr(defaults, f))))
        self.profile = name

    def new_profile(self, name: str) -> None:
        """Nouveau profil = copie du profil actuel (on ne recalibre que ce qui diffère), activé."""
        name = (name or "").strip()
        problem = profile_name_problem(name, self.profile_names())
        if problem:
            raise ValueError(problem)
        src_anchor = anchor_path(self)
        self.profiles[self.profile] = self.profile_data()
        self.profiles[name] = self.profile_data()
        self.profile = name
        if src_anchor.exists():
            shutil.copy2(src_anchor, anchor_path(self))

    def rename_profile(self, old: str, new: str) -> None:
        """Renomme un profil : ses zones, son repère, ses personnages associés et sa couleur suivent."""
        new = (new or "").strip()
        if old not in self.profile_names():
            raise KeyError(f"profil inconnu : {old}")
        if new == old:
            return
        problem = profile_name_problem(new, [n for n in self.profile_names() if n != old])
        if problem:
            raise ValueError(problem)
        src, dst = anchor_path(self, old), anchor_path(self, new)
        self.profiles[self.profile] = self.profile_data()        # profil actif à jour
        self.profiles[new] = self.profiles.pop(old)
        if self.profile == old:
            self.profile = new
        self.character_profiles = {c: (new if p == old else p) for c, p in self.character_profiles.items()}
        if old in self.profile_colors:
            self.profile_colors[new] = self.profile_colors.pop(old)
        if src.exists() and src != dst:
            dst.unlink(missing_ok=True)
            src.replace(dst)

    def delete_profile(self, name: str) -> None:
        if name == self.profile:
            raise ValueError("impossible de supprimer le profil actif : choisis-en un autre d'abord")
        if name not in self.profiles:
            raise KeyError(f"profil inconnu : {name}")
        self.character_profiles = {c: p for c, p in self.character_profiles.items() if p != name}
        self.profile_colors.pop(name, None)
        path = anchor_path(self, name)
        del self.profiles[name]
        if name != DEFAULT_PROFILE:
            path.unlink(missing_ok=True)

    def save(self, path: Path = CONFIG_PATH) -> None:
        # La fenêtre ET le fil de travail enregistrent (HDV déplacé, recalibration, fermeture) :
        # un à la fois. Avant, deux enregistrements simultanés partageaient le même fichier
        # temporaire et pouvaient laisser un fichier tronqué (illisible au lancement suivant).
        with _CONFIG_LOCK:
            self.profiles[self.profile] = self.profile_data()   # profil actif toujours à jour
            data = {name.upper(): getattr(self, name) for name in self.__dataclass_fields__}
            text = json.dumps(data, indent=2, ensure_ascii=False)
            tmp = path.with_name(f"{path.stem}.{os.getpid()}.tmp")
            tmp.write_text(text, encoding="utf-8")
            for attempt in range(5):           # antivirus / indexation : fichier ouvert un instant
                try:
                    os.replace(tmp, path)      # écriture atomique
                    return
                except PermissionError:
                    if attempt == 4:
                        tmp.unlink(missing_ok=True)
                        raise
                    time.sleep(0.1)

