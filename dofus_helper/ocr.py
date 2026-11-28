"""Lecture de l'écran : captures, Tesseract, lecteur de chiffres, lignes de la liste, champ « ton prix »."""
from __future__ import annotations

import re
import shutil
import string
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Dict, List, Optional, Tuple

import numpy as np

from .base import APP_DIR, DIGITS_PATH, IS_WINDOWS

if TYPE_CHECKING:
    from .base import Region
    from .config import Config


# --------------------------------------------------------------------------
# OCR
# --------------------------------------------------------------------------
@dataclass
class Reading:
    value: Optional[int]
    confidence: float  # 0-100, -1 si rien lu
    raw: str = ""


@dataclass
class ScreenRead:
    prices: Dict[int, Reading] = field(default_factory=dict)
    selected: Optional[int] = None       # quantité sélectionnée (None = non lue)
    selected_raw: str = ""
    avg: Optional[int] = None            # « Prix moyen » (par objet), None = non lu / non calibré
    listed: Optional[Tuple[int, int]] = None  # compteur (n, max), rempli par le test de lecture
    mine: Optional[int] = None                # ton prix (mes ventes), rempli par le test de lecture
    mine_r: Optional["Reading"] = None        # ton prix lu dans le même appel OCR (mes ventes)
    engine: str = ""                          # "chiffres" (rapide) | "tesseract"

    @property
    def values(self) -> Dict[int, Optional[int]]:
        return {l: r.value for l, r in self.prices.items()}


_tls = threading.local()
BORDER = 10
# Chiffres seulement, via une LISTE NOIRE (lettres + ponctuation) :
# - une whitelist "0123456789" sans espace colle "1 789" en un mot et la confiance tombe à ~0 ;
# - une whitelist avec espace demande des guillemets, que pytesseract sous Windows
#   (shlex non-POSIX) refuse : « No closing quotation ».
# Aucun guillemet, espace ni antislash ne doit donc apparaître dans cette config.
_BLACKLIST = "".join(c for c in string.ascii_letters + string.punctuation if c not in "\"'\\")
OCR_CONFIG = f"--psm 6 -c tessedit_char_blacklist={_BLACKLIST}"
# Compteur « 21/100 lots en vente » : même liste noire SANS « / » (séparateur), une ligne.
# Appel séparé : autoriser « / » dans le tableau ferait lire des « 1 » comme « / ».
_COUNT_BLACKLIST = _BLACKLIST.replace("/", "")
COUNT_CONFIG = f"--psm 7 -c tessedit_char_blacklist={_COUNT_BLACKLIST}"
_COUNT_RE = re.compile(r"(\d+)\s*/\s*(\d+)")


MIN_TESSERACT = (5, 0)          # versions plus anciennes : lectures différentes, non testées
BUNDLED_TESSERACT = APP_DIR / "tesseract" / "tesseract.exe"   # inclus dans l'exe (zip)
TESSERACT_USED = ""             # « Tesseract 5.5 (installé) » : affiché au démarrage
_VERSION_RE = re.compile(r"tesseract\s+v?(\d+)\.(\d+)", re.IGNORECASE)


def tesseract_version(cmd: str) -> Optional[Tuple[int, int]]:
    """(majeure, mineure) de `cmd --version`, None si illisible ou pas un Tesseract."""
    import subprocess
    try:
        si = None
        if IS_WINDOWS:
            si = subprocess.STARTUPINFO()
            si.dwFlags |= subprocess.STARTF_USESHOWWINDOW   # pas de fenêtre console
        out = subprocess.run([cmd, "--version"], capture_output=True, text=True, timeout=15,
                             startupinfo=si)
    except (OSError, subprocess.SubprocessError, ValueError):
        return None
    m = _VERSION_RE.search((out.stdout or "") + (out.stderr or ""))
    return (int(m.group(1)), int(m.group(2))) if m else None


def setup_tesseract(cfg: Config) -> Optional[str]:
    """Choisit le Tesseract à utiliser. Retourne un message d'erreur ou None.
    Ordre : celui de la config ou du PATH s'il est en version >= 5 ; sinon celui inclus dans
    l'exe ; sinon un Tesseract installé plus ancien (mieux que rien)."""
    global TESSERACT_USED
    import pytesseract
    installed = []
    for cmd in (cfg.tesseract_cmd, shutil.which("tesseract")):
        if cmd and Path(cmd).exists() and cmd not in installed:
            installed.append(cmd)
    candidates = [(c, tesseract_version(c), "installé") for c in installed]
    good = [c for c in candidates if c[1] and c[1] >= MIN_TESSERACT]
    if not good and BUNDLED_TESSERACT.exists():
        good = [(str(BUNDLED_TESSERACT), tesseract_version(str(BUNDLED_TESSERACT)), "inclus")]
    pick = (good or [c for c in candidates if c[1]] or [None])[0]
    if pick is None:
        return ("Tesseract introuvable. Installe-le (version 5 ou plus) ou corrige TESSERACT_CMD "
                "dans dofus_price_helper_config.json.")
    cmd, ver, origin = pick
    pytesseract.pytesseract.tesseract_cmd = cmd
    TESSERACT_USED = f"Tesseract {ver[0]}.{ver[1]} ({origin})" if ver else f"Tesseract ({origin})"
    if ver and ver < MIN_TESSERACT:
        return (f"Tesseract {ver[0]}.{ver[1]} est ancien : installe la version 5 ou plus "
                "(lectures moins fiables).")
    return None


def grab_screen(region: Region) -> np.ndarray:
    import mss
    sct = getattr(_tls, "sct", None)
    if sct is None:  # une instance mss par thread (non thread-safe)
        sct = _tls.sct = mss.mss()
    x, y, w, h = region
    img = np.array(sct.grab({"left": x, "top": y, "width": w, "height": h}))
    return img[:, :, :3]  # BGR


def preprocess(img_bgr: np.ndarray, scale: int = 2) -> np.ndarray:
    """Niveaux de gris, agrandissement, binarisation Otsu, texte NOIR sur BLANC."""
    import cv2
    gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
    # Texte Dofus = blanc/gris (peu saturé). Icônes kamas (jaune) et objets (couleurs) :
    # saturées -> remplacées par le fond, sinon l'icône kamas est lue comme un "4".
    hsv = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2HSV)
    colored = ((hsv[:, :, 1] > 80) & (hsv[:, :, 2] > 60)).astype(np.uint8)
    # + contour gris des icônes (anticrénelage) : sans ça, les restes d'une icône d'objet
    # se collent au « 1 » de la colonne Lot et la ligne du lot 1 disparaît.
    colored = cv2.dilate(colored, np.ones((3, 3), np.uint8)).astype(bool)
    if colored.any() and (~colored).any():
        gray = gray.copy()
        gray[colored] = int(np.median(gray[~colored]))
    up = cv2.resize(gray, (gray.shape[1] * scale, gray.shape[0] * scale),
                    interpolation=cv2.INTER_CUBIC)
    t, th = cv2.threshold(up, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    if np.mean(th) > 255 * 0.3:
        # Trop de pixels « clairs » : Otsu a séparé le fond d'un CADRE gris (menu Quantité
        # grisé, champ) au lieu du texte. 2e seuil, parmi les pixels clairs seulement.
        bright = up[up > t]
        t2, _ = cv2.threshold(bright.reshape(-1, 1), 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        th2 = np.where(up > t2, 255, 0).astype(np.uint8)
        if 0.002 < np.mean(th2) / 255 < 0.3:
            th = th2
    if np.mean(th) < 127:  # fond sombre majoritaire -> inverser
        th = cv2.bitwise_not(th)
    th = _drop_big_blobs(th, scale)
    return cv2.copyMakeBorder(th, BORDER, BORDER, BORDER, BORDER, cv2.BORDER_CONSTANT, value=255)


def _drop_big_blobs(th: np.ndarray, scale: int) -> np.ndarray:
    """Efface les taches noires trop grandes pour être un chiffre : icônes d'objet
    PÂLES (laine céleste, plumes : pas assez colorées pour le masque de couleur),
    traits de séparation. Un chiffre Dofus fait ~10 px de haut à l'échelle 1."""
    import cv2
    ink = (th == 0).astype(np.uint8)
    n, lab, stats, _ = cv2.connectedComponentsWithStats(ink, connectivity=8)
    if n <= 1:
        return th
    h, w = stats[1:, cv2.CC_STAT_HEIGHT], stats[1:, cv2.CC_STAT_WIDTH]
    big = (h > 16 * scale) | (w > 24 * scale)
    if not big.any():
        return th
    out = th.copy()
    out[np.isin(lab, np.where(big)[0] + 1)] = 255
    return out


def stack_images(imgs: List[np.ndarray], gap: int = 30) -> Tuple[np.ndarray, List[Tuple[int, int]]]:
    """Empile verticalement des images binaires. Retourne l'image et les bornes y de chaque segment."""
    width = max(i.shape[1] for i in imgs)
    parts, bounds, y = [], [], 0
    for i, img in enumerate(imgs):
        if img.shape[1] < width:
            pad = np.full((img.shape[0], width - img.shape[1]), 255, dtype=img.dtype)
            img = np.hstack([img, pad])
        parts.append(img)
        bounds.append((y, y + img.shape[0]))
        y += img.shape[0]
        if i < len(imgs) - 1:
            parts.append(np.full((gap, width), 255, dtype=img.dtype))
            y += gap
    return np.vstack(parts), bounds


def _words(data: Dict[str, list], y0: int, y1: int):
    """Mots contenant des chiffres dont le centre vertical est dans [y0, y1)."""
    n = len(data["text"])
    for i in range(n):
        digits = "".join(c for c in str(data["text"][i]) if c.isdigit())
        if not digits:
            continue
        cy = int(data["top"][i]) + int(data["height"][i]) / 2
        if y0 <= cy < y1:
            yield i, digits


def parse_table(data: Dict[str, list], bounds: Tuple[int, int], inner_width: int,
                split: float, lots: List[int]) -> Dict[int, Reading]:
    """Lignes du tableau -> {lot: Reading}. Colonne Lot à gauche de `split`, Prix à droite.
    Un lot illisible est déduit de l'ordre des lignes (lots croissants de haut en bas)
    quand un seul lot est possible entre la ligne du dessus et celle du dessous."""
    rows: Dict[tuple, List[Tuple[int, str, float, bool, int]]] = {}
    for i, digits in _words(data, *bounds):
        key = (data["block_num"][i], data["par_num"][i], data["line_num"][i])
        cx = (int(data["left"][i]) + int(data["width"][i]) / 2 - BORDER) / max(1, inner_width)
        rows.setdefault(key, []).append((int(data["left"][i]), digits, float(data["conf"][i]),
                                         cx < split, int(data["top"][i])))
    parsed: List[Tuple[int, Optional[int], Reading]] = []  # (y, lot ou None, prix)
    for words in rows.values():
        words.sort()
        price_w = [w for w in words if not w[3]]
        if not price_w:
            continue
        lot_txt = "".join(w[1] for w in words if w[3])
        if lot_txt and int(lot_txt) not in lots:
            continue  # lot lu mais impossible (ex. « 7 ») : ligne ignorée, jamais déduite
        lot = int(lot_txt) if lot_txt else None  # None = illisible -> déduit de l'ordre
        reading = Reading(int("".join(w[1] for w in price_w)), min(w[2] for w in price_w),
                          " ".join(w[1] for w in price_w))
        parsed.append((min(w[4] for w in words), lot, reading))
    parsed.sort(key=lambda t: t[0])
    known = [lot for _, lot, _ in parsed if lot is not None]
    out: Dict[int, Reading] = {}
    i = 0
    while i < len(parsed):
        _, lot, reading = parsed[i]
        if lot is not None:
            out.setdefault(lot, reading)
            i += 1
            continue
        # bloc de lignes consécutives au lot illisible, entre deux lots connus
        j = i
        while j < len(parsed) and parsed[j][1] is None:
            j += 1
        lo = next((l for _, l, _ in reversed(parsed[:i]) if l is not None), 0)
        hi = parsed[j][1] if j < len(parsed) else float("inf")
        cands = [l for l in lots if lo < l < hi and l not in known]
        if len(cands) == j - i:          # autant de lots possibles que de lignes : sans ambiguïté
            for (_, _, rd), l in zip(parsed[i:j], cands):
                out.setdefault(l, rd)
        i = j
    return out


def parse_number(data: Dict[str, list], bounds: Tuple[int, int]) -> Reading:
    ws = sorted((int(data["left"][i]), d, float(data["conf"][i])) for i, d in _words(data, *bounds))
    if not ws:
        return Reading(None, -1.0, "")
    return Reading(int("".join(w[1] for w in ws)), min(w[2] for w in ws), " ".join(w[1] for w in ws))


def table_second_read(cfg: Config, first_engine: str = "") -> "ScreenRead":
    """2e lecture du tableau, Tesseract seul (sans la lecture rapide), pour contrôler la 1re.
    1re lecture déjà faite par Tesseract : même moteur, même image = même résultat, erreur
    comprise (« 1 499 » lu 199 était « confirmé »). L'image est alors agrandie autrement."""
    if first_engine != "chiffres":
        import dataclasses
        cfg = dataclasses.replace(cfg, scale=cfg.scale + 1)
    return read_screen(cfg, tesseract_only=True)


def read_screen(cfg: Config, debug_dir: Optional[Path] = None, with_mine: bool = False,
                tesseract_only: bool = False) -> ScreenRead:
    """Tableau + quantité (+ prix moyen, + ton prix) en UN appel Tesseract."""
    if not cfg.table_region:
        return ScreenRead()
    regions = [tuple(cfg.table_region)]
    if cfg.qty_region:
        regions.append(tuple(cfg.qty_region))
    if cfg.avg_region:
        regions.append(tuple(cfg.avg_region))
    imgs = [preprocess(grab_screen(r), cfg.scale) for r in regions]
    mine_img = None
    if with_mine:
        # même échelle que le reste : à ×4 le texte est trop grand pour cet appel groupé
        mine_img = mine_field_image(cfg, cfg.scale)
        if mine_img is not None:
            imgs.append(mine_img)
    comp, bounds = stack_images(imgs)
    if debug_dir:
        import cv2
        debug_dir.mkdir(exist_ok=True)
        cv2.imwrite(str(debug_dir / f"ocr_{int(time.time() * 1000)}.png"), comp)
    data, engine = _ocr(comp, bounds, cfg, force_tesseract=tesseract_only)
    inner_w = imgs[0].shape[1] - 2 * BORDER
    res = _parse_screen(data, bounds, inner_w, cfg, len(regions), mine_img is not None)
    if engine == "chiffres" and (not res.prices or (cfg.qty_region and res.selected is None)):
        # Lecture rapide incomplète (tableau vide, quantité manquante) : Tesseract tranche.
        data, engine = _ocr(comp, bounds, cfg, force_tesseract=True)
        res = _parse_screen(data, bounds, inner_w, cfg, len(regions), mine_img is not None)
    res.engine = engine
    ENGINE_STATS[engine] = ENGINE_STATS.get(engine, 0) + 1
    return res


ENGINE_STATS: Dict[str, int] = {}   # nombre de lectures par moteur (« chiffres » / « tesseract »)


def _parse_screen(data, bounds, inner_w: int, cfg: Config, n_regions: int, with_mine: bool) -> ScreenRead:
    res = ScreenRead(prices=parse_table(data, bounds[0], inner_w, cfg.table_split, cfg.lots))
    if cfg.qty_region:
        q = parse_number(data, bounds[1])
        res.selected_raw = q.raw
        res.selected = q.value if q.value in cfg.lots else None
    if cfg.avg_region:
        a = parse_number(data, bounds[n_regions - 1])
        res.avg = a.value if a.value and a.confidence >= cfg.min_confidence else None
    if with_mine:
        res.mine_r = parse_number(data, bounds[-1])
    return res


RELIST_READ_TRIES = 8   # F3 : relectures max si le tableau n'est pas encore chargé (~1 s)

_digits = None
_digits_lock = threading.Lock()
_fast_count = 0
CROSS_CHECK_EVERY = 25   # 1 lecture rapide sur 25 est recontrôlée par Tesseract


def digit_reader():
    global _digits
    with _digits_lock:
        if _digits is None:
            from .digits import DigitReader
            _digits = DigitReader(DIGITS_PATH)
        return _digits


def _ocr(comp: np.ndarray, bounds, cfg: Config, force_tesseract: bool = False):
    """Lecture rapide si les chiffres sont appris et tous reconnus avec certitude ;
    sinon Tesseract (qui sert aussi à apprendre). Contrôle croisé régulier."""
    import pytesseract
    global _fast_count
    dr = digit_reader() if cfg.fast_digits else None
    fast = dr.read_data(comp, bounds) if dr and not force_tesseract else None
    if fast is not None:
        _fast_count += 1
        if _fast_count % CROSS_CHECK_EVERY:
            return fast, "chiffres"
    data = pytesseract.image_to_data(comp, config=OCR_CONFIG, output_type=pytesseract.Output.DICT)
    if fast is not None and _digits_disagree(fast, data, bounds, cfg):
        print("[Chiffres] Contrôle : désaccord avec Tesseract, modèles réinitialisés.")
        dr.reset()
    if dr:
        dr.learn(comp, data, bounds)
    return data, "tesseract"


def _digits_disagree(a, b, bounds, cfg: Config) -> bool:
    for y0, y1 in bounds:
        ra, rb = parse_number(a, (y0, y1)), parse_number(b, (y0, y1))
        if rb.confidence >= 90 and ra.value != rb.value:
            return True
    return False


def detect_rows(strip_bgr: np.ndarray, top: int, step: int) -> List[int]:
    """Centres (y écran) des lignes ENTIÈREMENT visibles de la liste « mes ventes ».
    Les lignes (fond ~54, ~74 au survol) sont séparées par des bandes plus sombres (~32) :
    on les retrouve sur le profil vertical, quel que soit le défilement."""
    import cv2
    if strip_bgr.size == 0:
        return []
    gray = cv2.cvtColor(strip_bgr, cv2.COLOR_BGR2GRAY) if strip_bgr.ndim == 3 else strip_bgr
    prof = np.median(gray, axis=1)
    level = float(np.percentile(prof, 75))
    is_row = prof > level - 12
    out, start = [], None
    for i, r in enumerate(list(is_row) + [False]):
        if r and start is None:
            start = i
        elif not r and start is not None:
            n = i - start
            # ligne complète : ni coupée en haut/bas de la zone, ni fusionnée avec la voisine
            if 0.6 * step <= n <= 1.3 * step and start > 0 and i < len(prof):
                out.append(top + (start + i - 1) // 2)
            start = None
    return out


def _same_row(a: np.ndarray, b: np.ndarray) -> bool:
    """Deux lignes de la liste STRICTEMENT identiques (même objet, même prix, même durée).
    On compte les pixels vraiment différents : une moyenne globale ne voyait pas un seul
    chiffre de prix changé (76 vs 75 -> ligne sautée à tort)."""
    import cv2
    if a.shape != b.shape:
        return False
    ga = cv2.cvtColor(a, cv2.COLOR_BGR2GRAY) if a.ndim == 3 else a
    gb = cv2.cvtColor(b, cv2.COLOR_BGR2GRAY) if b.ndim == 3 else b
    return int((np.abs(ga.astype(np.int16) - gb.astype(np.int16)) > 40).sum()) <= 6


def wait_any_change(regions: List[Region], befores: List[np.ndarray], timeout: float,
                    settle: float = 0.08) -> bool:
    """Attend qu'UNE des zones change (au plus `timeout` s). True si changement vu."""
    end = time.time() + timeout
    time.sleep(0.04)
    while regions and time.time() < end:
        for r, b in zip(regions, befores):
            if not np.array_equal(grab_screen(r), b):
                time.sleep(settle)
                return True
        time.sleep(0.03)
    if not regions:
        time.sleep(max(0.0, timeout - 0.04))
    return False


def wait_change(region: Optional[Region], before: Optional[np.ndarray], timeout: float,
                min_wait: float = 0.05) -> None:
    """Attend que la zone change à l'écran (panneau mis à jour), au plus `timeout` s.
    Remplace une pause fixe : le jeu répond souvent en ~0,1 s."""
    time.sleep(min_wait)
    if region is None or before is None:
        time.sleep(max(0.0, timeout - min_wait))
        return
    end = time.time() + timeout - min_wait
    while time.time() < end:
        if not np.array_equal(grab_screen(region), before):
            time.sleep(0.03)  # laisser finir l'affichage
            return
        time.sleep(0.03)


def wait_still(region: Region, timeout: float, step: float = 0.05) -> None:
    """Attend que la zone ne bouge plus (deux captures identiques à `step` s d'écart),
    au plus `timeout` s. Remplace une pause fixe après un défilement : la liste s'arrête
    souvent en ~0,1 s."""
    end = time.time() + timeout
    prev = grab_screen(region)
    while time.time() < end:
        time.sleep(step)
        cur = grab_screen(region)
        if np.array_equal(cur, prev):
            return
        prev = cur


def _find_field(img_bgr: np.ndarray) -> Optional[np.ndarray]:
    """Dans une zone trop large, isole le champ « Prix du lot » : rectangle presque NOIR
    (bien plus sombre que le panneau), large et peu haut."""
    import cv2
    if img_bgr.size == 0:
        return None
    if img_bgr.shape[1] < 220 and img_bgr.shape[0] < 60:
        return img_bgr  # zone déjà ajustée au champ
    best = None
    # champ sélectionné : ~8 ; champ non sélectionné : ~27 (panneau ~40)
    for limit in (20, 33):
        dark = (img_bgr.max(axis=2) < limit).astype(np.uint8)
        n, _, stats, _ = cv2.connectedComponentsWithStats(dark)
        for k in range(1, n):
            x, y, w, h, area = (int(v) for v in stats[k])
            if 60 <= w <= 400 and 12 <= h <= 60 and w >= 3 * h and area >= 0.6 * w * h:
                if best is None or area > best[4]:
                    best = (x, y, w, h, area)
        if best is not None:
            break
    if best is None:
        return None  # pas de champ (vente désélectionnée) : ne pas lire toute la zone
    x, y, w, h, _ = best
    return img_bgr[y:y + h, x:x + w]


def preprocess_field(img_bgr: np.ndarray, scale: int = 4) -> Optional[np.ndarray]:
    """Champ « Prix du lot ». Zone trop large -> on y retrouve le champ (rectangle noir).
    Texte souvent SÉLECTIONNÉ (fond bleu) : le masque des couleurs effacerait tout ->
    recadrage sur le surlignage puis Otsu ; sinon traitement normal du champ seul."""
    import cv2
    img_bgr = _find_field(img_bgr)
    if img_bgr is None:
        return None
    c = img_bgr.astype(int)
    hl = (c[:, :, 0] > 110) & (c[:, :, 0] > c[:, :, 2] + 40)
    if hl.sum() < 20:
        return _drop_caret(preprocess(img_bgr, max(2, scale // 2)))
    # plus grande tache bleue = le surlignage (pas une icône bleue voisine)
    n, _, stats, _ = cv2.connectedComponentsWithStats(hl.astype(np.uint8))
    k = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
    x, y, w, h = (int(v) for v in stats[k, :4])
    sub = img_bgr[y:y + h, x:x + w]
    gray = cv2.cvtColor(sub, cv2.COLOR_BGR2GRAY)
    up = cv2.resize(gray, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
    _, th = cv2.threshold(up, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    if np.mean(th) < 127:
        th = cv2.bitwise_not(th)
    return cv2.copyMakeBorder(th, BORDER, BORDER, BORDER, BORDER, cv2.BORDER_CONSTANT, value=255)


def mine_regions(cfg: Config) -> List[Region]:
    """Où chercher le champ « Prix du lot » : autour du point calibré du champ
    (Ctrl+Alt+F3, le plus fiable), puis la zone « Ton prix » (Ctrl+Alt+F7)."""
    out = []
    if cfg.price_field:
        x, y = cfg.price_field
        out.append((max(0, x - 140), max(0, y - 30), 280, 60))
    if cfg.mine_region:
        out.append(tuple(cfg.mine_region))
    return out


def mine_field_image(cfg: Config, scale: int = 4) -> Optional[np.ndarray]:
    for region in mine_regions(cfg):
        img = preprocess_field(grab_screen(region), scale)
        if img is not None:
            return img
    return None


def _drop_caret(th: np.ndarray) -> np.ndarray:
    """Efface le curseur de saisie : barre verticale fine qui traverse la ligne de texte et
    DÉPASSE au-dessus et en dessous des chiffres. Collé au dernier chiffre, « 496| » était
    lu « 49 » ou « 494 »."""
    ink = th < 128
    per_row = ink.sum(axis=1)
    if per_row.max() == 0:
        return th
    band = np.where(per_row > 0.25 * per_row.max())[0]     # lignes des chiffres
    if len(band) < 3:
        return th
    top, bot = band[0], band[-1]
    above = ink[:max(0, top - 1)].any(axis=0)
    below = ink[bot + 2:].any(axis=0)
    inside = ink[top:bot + 1].any(axis=0)
    cand = above & below & inside                          # traverse toute la ligne
    out = th
    cols = np.where(cand)[0]
    if len(cols):
        runs, start = [], cols[0]
        for a, b in zip(cols, list(cols[1:]) + [None]):
            if b is None or b != a + 1:
                runs.append((start, a))
                start = b
        for a, b in runs:
            if b - a + 1 <= 8:                             # barre fine seulement
                if out is th:
                    out = th.copy()
                out[:, a:b + 1] = 255
                # bords anticrénelés de la barre : effacés seulement HORS de la ligne de texte.
                # Effacés partout, ils rognaient le chiffre collé au curseur (8 relu 6 : vente
                # refusée à tort).
                for c in (a - 1, b + 1):
                    if 0 <= c < out.shape[1]:
                        out[:max(0, top - 1), c] = 255
                        out[bot + 2:, c] = 255
    return out


MINE_SURE = 90   # confiance (%) sous laquelle ton prix est relu autrement (niveaux de gris)


def field_gray_image(img_bgr: np.ndarray, scale: int = 4) -> Optional[np.ndarray]:
    """Champ « Prix du lot » en NIVEAUX DE GRIS (texte foncé sur fond clair), sans
    noir et blanc. Quand le jeu est mis à l'échelle de l'écran (plein écran à une autre
    résolution), le texte est adouci : le seuillage soude ou coupe les chiffres
    (« 1 989 » lu « 1909 »), Tesseract lit mieux l'image grise. Curseur de saisie effacé."""
    import cv2
    img = _find_field(img_bgr)
    if img is None or img.size == 0:
        return None
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    up = cv2.resize(gray, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
    inv = 255 - cv2.normalize(up, None, 0, 255, cv2.NORM_MINMAX)
    _, th = cv2.threshold(inv, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    caret = (_drop_caret(th) != th).any(axis=0)             # colonnes du curseur
    if caret.any():
        inv = inv.copy()
        inv[:, caret] = 255
    return cv2.copyMakeBorder(inv, BORDER, BORDER, BORDER, BORDER, cv2.BORDER_CONSTANT, value=255)


SECOND_OPINION_SCALE = 6   # « ton prix » relu plus grand : pas la même image que la 1re lecture


def mine_second_opinions(cfg: Config) -> List[Reading]:
    """Deux autres lectures de « ton prix », chacune sur une image DIFFÉRENTE de la 1re :
    Tesseract seul sur le champ agrandi autrement, et niveaux de gris. Avant, la 2e relisait
    la même image avec le même moteur (ou reprenait la lecture en gris) : une majorité
    « 2 sur 3 » sans vrai 2e avis."""
    return [read_mine(cfg, tesseract_only=True, scale=SECOND_OPINION_SCALE, gray_fallback=False),
            read_mine_gray(cfg)]


def vote_mine(first: Reading, others: List[Reading], min_conf: float) -> Tuple[Optional[int], str]:
    """Valeur lue par au moins 2 lectures sur 3 (None si aucune majorité) + détail."""
    vals = [first.value] + [r.value for r in others if r.value is not None and r.confidence >= min_conf]
    detail = " / ".join(str(v) for v in vals)
    for v in vals:
        if v is not None and vals.count(v) >= 2:
            return v, detail
    return (first.value if not others else None), detail


def read_mine_gray(cfg: Config) -> Reading:
    """2e avis sur ton prix : le champ lu en niveaux de gris (voir field_gray_image)."""
    import pytesseract
    for region in mine_regions(cfg):
        img = field_gray_image(grab_screen(region))
        if img is not None:
            data = pytesseract.image_to_data(img, config=OCR_CONFIG, output_type=pytesseract.Output.DICT)
            return parse_number(data, (0, img.shape[0]))
    return Reading(None, -1.0, "")


def surer(a: Optional[Reading], b: Optional[Reading]) -> Reading:
    """La lecture la plus sûre des deux (une valeur vaut mieux que rien)."""
    cands = [r for r in (a, b) if r is not None]
    if not cands:
        return Reading(None, -1.0, "")
    return max(cands, key=lambda r: (r.value is not None, r.confidence))


def read_mine(cfg: Config, tesseract_only: bool = False, scale: int = 4,
              gray_fallback: bool = True) -> Reading:
    """Ton prix actuel (champ « Prix du lot » de la vente sélectionnée).
    tesseract_only : sans la lecture rapide (2e avis quand la relecture ne colle pas).
    Lecture peu sûre -> relue en niveaux de gris, la plus sûre des deux est gardée."""
    import pytesseract
    img = mine_field_image(cfg, scale)
    if img is None:
        return Reading(None, -1.0, "")
    if cfg.fast_digits and not tesseract_only:
        fast = digit_reader().read_data(img, [(0, img.shape[0])])
        if fast is not None:
            r = parse_number(fast, (0, img.shape[0]))
            if r.value is not None:
                return r
    data = pytesseract.image_to_data(img, config=OCR_CONFIG, output_type=pytesseract.Output.DICT)
    r = parse_number(data, (0, img.shape[0]))
    if gray_fallback and (r.value is None or r.confidence < MINE_SURE):
        r = surer(r, read_mine_gray(cfg))
    return r


def parse_counter(text: str) -> Optional[Tuple[int, int]]:
    """« 21/100 lots en vente » -> (21, 100). None si illisible ou incohérent."""
    m = _COUNT_RE.search(text or "")
    if not m:
        return None
    n, mx = int(m.group(1)), int(m.group(2))
    return (n, mx) if 0 <= n <= mx and mx > 0 else None


def read_counter(cfg: Config) -> Optional[Tuple[int, int]]:
    """Compteur de lots en vente (n, max). None si non calibré ou illisible."""
    import pytesseract
    if not cfg.count_region:
        return None
    img = preprocess(grab_screen(tuple(cfg.count_region)), cfg.scale)
    return parse_counter(pytesseract.image_to_string(img, config=COUNT_CONFIG))

