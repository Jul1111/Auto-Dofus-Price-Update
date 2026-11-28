"""Fenêtre du jeu, souris, presse-papier, saisie, défilement de la liste."""
from __future__ import annotations

import threading
import time
from pathlib import Path
from typing import TYPE_CHECKING, Dict, List, Optional, Tuple

import numpy as np

from .base import APP_DIR, BASE_DIR, IS_WINDOWS, log_line
from .ocr import digit_reader, grab_screen, mine_field_image, mine_regions, read_mine, wait_still
from .anchor import _gray, POINT_FIELDS, REGION_FIELDS
from .config import Config

if TYPE_CHECKING:
    from .base import Point, Region


# --------------------------------------------------------------------------
# Fenêtre active / saisie / son
# --------------------------------------------------------------------------
def foreground_info() -> Optional[Tuple[str, str]]:
    """(titre, nom de l'exe) de la fenêtre active. None hors Windows."""
    if not IS_WINDOWS:
        return None
    import ctypes
    from ctypes import wintypes
    user32, kernel32 = ctypes.windll.user32, ctypes.windll.kernel32
    hwnd = user32.GetForegroundWindow()
    n = user32.GetWindowTextLengthW(hwnd)
    buf = ctypes.create_unicode_buffer(n + 1)
    user32.GetWindowTextW(hwnd, buf, n + 1)
    title = buf.value

    exe = ""
    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    h = kernel32.OpenProcess(0x1000, False, pid.value)  # PROCESS_QUERY_LIMITED_INFORMATION
    if h:
        try:
            size = wintypes.DWORD(1024)
            pbuf = ctypes.create_unicode_buffer(size.value)
            if kernel32.QueryFullProcessImageNameW(h, 0, pbuf, ctypes.byref(size)):
                exe = Path(pbuf.value).name
        finally:
            kernel32.CloseHandle(h)
    return title, exe


def _window_exe(hwnd) -> str:
    import ctypes
    from ctypes import wintypes
    user32, kernel32 = ctypes.windll.user32, ctypes.windll.kernel32
    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    h = kernel32.OpenProcess(0x1000, False, pid.value)  # PROCESS_QUERY_LIMITED_INFORMATION
    if not h:
        return ""
    try:
        size = wintypes.DWORD(1024)
        pbuf = ctypes.create_unicode_buffer(size.value)
        if kernel32.QueryFullProcessImageNameW(h, 0, pbuf, ctypes.byref(size)):
            return Path(pbuf.value).name
    finally:
        kernel32.CloseHandle(h)
    return ""


def game_window_rect(cfg: Config) -> Optional[Region]:
    """Rectangle (x, y, l, h) de la fenêtre du jeu, visible et pas réduite ; None si introuvable
    (jeu fermé, réduit, ou hors Windows). Plusieurs fenêtres : la plus grande."""
    if not IS_WINDOWS or not (cfg.window_process or cfg.window_title):
        return None
    import ctypes
    from ctypes import wintypes
    user32 = ctypes.windll.user32
    found = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def cb(hwnd, _lp):
        try:
            if not user32.IsWindowVisible(hwnd) or user32.IsIconic(hwnd):
                return True
            n = user32.GetWindowTextLengthW(hwnd)
            if n <= 0:
                return True
            buf = ctypes.create_unicode_buffer(n + 1)
            user32.GetWindowTextW(hwnd, buf, n + 1)
            if is_game_window(buf.value, _window_exe(hwnd), cfg):
                r = wintypes.RECT()
                if user32.GetWindowRect(hwnd, ctypes.byref(r)) and r.right > r.left and r.bottom > r.top:
                    found.append((r.left, r.top, r.right - r.left, r.bottom - r.top))
        except Exception:
            pass
        return True
    try:
        user32.EnumWindows(cb, 0)
    except Exception:
        return None
    return max(found, key=lambda r: r[2] * r[3]) if found else None


def calib_drift(saved, current, has_anchor: bool, tol: int = 4) -> Optional[str]:
    """Pourquoi la calibration semble décalée (None = rien à signaler).
    saved / current : rectangle de la fenêtre du jeu à la calibration / maintenant."""
    if not saved or not current or len(saved) != 4:
        return None
    sx, sy, sw, sh = saved
    cx, cy, cw, ch = current
    if abs(sw - cw) > tol or abs(sh - ch) > tol:
        return f"la fenêtre du jeu a changé de taille ({sw}×{sh} → {cw}×{ch})"
    if (abs(sx - cx) > tol or abs(sy - cy) > tol) and not has_anchor:
        return (f"la fenêtre du jeu a bougé de ({cx - sx:+d}, {cy - sy:+d}) px et il n'y a pas de "
                "repère « Hôtel de vente » pour que les zones suivent")
    return None


def zones_off_screen(cfg: Config, bounds: Region) -> List[str]:
    """Zones / points calibrés qui sortent de l'écran (écran débranché, résolution changée)."""
    bx, by, bw, bh = bounds
    out = []
    for f in REGION_FIELDS:
        r = getattr(cfg, f)
        if r and not (bx <= r[0] and by <= r[1] and r[0] + r[2] <= bx + bw and r[1] + r[3] <= by + bh):
            out.append(f[:-len("_region")])
    for f in POINT_FIELDS:
        pt = getattr(cfg, f)
        if pt and not (bx <= pt[0] < bx + bw and by <= pt[1] < by + bh):
            out.append(f)
    return out


def character_from_title(title: str) -> Optional[str]:
    """Nom du personnage d'après le titre de la fenêtre du jeu : « Perso - Classe - 3.x - Release »
    -> « Perso ». None si le titre n'a pas cette forme (lanceur, écran de connexion…)."""
    parts = [p.strip() for p in (title or "").split(" - ")]
    if len(parts) < 3 or not parts[0] or len(parts[0]) > 40:
        return None
    return parts[0]


def profile_for_character(character: Optional[str], mapping: dict, names: List[str]) -> Optional[str]:
    """Profil à utiliser pour ce personnage : celui qui lui est associé, sinon un profil qui porte
    son nom (sans tenir compte des majuscules). None = rien de prévu pour lui."""
    if not character:
        return None
    key = character.casefold()
    for c, prof in mapping.items():
        if c.casefold() == key and prof in names:
            return prof
    return next((n for n in names if n.casefold() == key), None)


def is_game_window(title: str, exe: str, cfg: Config) -> bool:
    """Fenêtre du jeu si le nom de l'exe OU le titre correspond.
    Titre Dofus : « Perso - Classe - version - Release » -> pas de « Dofus » dedans."""
    if cfg.window_process and cfg.window_process.lower() in exe.lower():
        return True
    if cfg.window_title and cfg.window_title.lower() in title.lower():
        return True
    return False


def game_has_focus(cfg: Config) -> bool:
    if not cfg.require_focus or not (cfg.window_process or cfg.window_title):
        return True
    info = foreground_info()
    if info is None:  # hors Windows : pas de vérification possible
        return True
    return is_game_window(*info, cfg)


def mouse_position() -> Point:
    import pyautogui
    p = pyautogui.position()
    return int(p[0]), int(p[1])


# Presse-papier : une seule restauration en attente à la fois. Sans ça, avec « Tout vendre »,
# la restauration de la vente précédente écrasait le prix juste avant le Ctrl+V suivant
# (le texte de l'utilisateur était collé dans « Prix du lot »).
_clip_lock = threading.Lock()
_clip_timer: Optional[threading.Timer] = None
_clip_saved: Optional[str] = None  # presse-papier de l'utilisateur, à remettre


def _take_clipboard(pyperclip, cfg: Config) -> None:
    """Annule la restauration en attente ; mémorise le presse-papier de l'utilisateur."""
    global _clip_timer, _clip_saved
    with _clip_lock:
        if _clip_timer is not None:      # restauration en attente : le presse-papier
            _clip_timer.cancel()         # contient encore NOTRE prix, garder l'ancien texte
            _clip_timer = None
        elif cfg.restore_clipboard:
            try:
                _clip_saved = pyperclip.paste()
            except Exception:
                _clip_saved = None


def _schedule_restore(pyperclip, delay: float = 1.0) -> None:
    global _clip_timer

    def _restore():
        global _clip_timer, _clip_saved
        with _clip_lock:
            if _clip_saved is not None:
                try:
                    pyperclip.copy(_clip_saved)
                except Exception:
                    pass
            _clip_timer, _clip_saved = None, None

    with _clip_lock:
        if _clip_saved is None:
            return
        _clip_timer = threading.Timer(delay, _restore)
        _clip_timer.daemon = True
        _clip_timer.start()


def _set_clipboard(pyperclip, text: str, tries: int = 3) -> bool:
    """Vide le presse-papier, y met `text`, puis vérifie qu'il contient bien `text`."""
    for _ in range(tries):
        try:
            pyperclip.copy("")
            pyperclip.copy(text)
            if pyperclip.paste() == text:
                return True
        except Exception:
            pass
        time.sleep(0.05)
    return False


def input_price(value: int, cfg: Config, paste: bool = True, validate: bool = False) -> str:
    """paste=False : copie seulement le prix dans le presse-papier.
    paste=True  : clic sur « Prix du lot » (option) -> vidage -> saisie -> (mise en vente)."""
    import pyperclip
    if not paste:
        _take_clipboard(pyperclip, Config(restore_clipboard=False))
        _set_clipboard(pyperclip, str(value))
        return "copié"

    import keyboard
    import pyautogui
    use_clip = cfg.input_method == "paste"
    if use_clip:
        _take_clipboard(pyperclip, cfg)
        if not _set_clipboard(pyperclip, str(value)):
            _schedule_restore(pyperclip, 0.0)
            raise RuntimeError("presse-papier inaccessible : rien n'a été collé")

    restore_mouse = None
    if cfg.click_field and cfg.price_field:
        restore_mouse = mouse_position()
        pyautogui.click(*cfg.price_field)
        time.sleep(0.08)

    # Le jeu pré-remplit « Prix du lot » : sans vidage, on obtiendrait "353" + "34".
    if cfg.clear_method == "ctrl_a":
        keyboard.press_and_release("ctrl+a")
    else:  # "backspace" : fin du champ puis effacement, sans combinaison Ctrl
        keyboard.press_and_release("end")
        for _ in range(12):
            keyboard.press_and_release("backspace")
            time.sleep(0.005)
    time.sleep(0.04)

    if use_clip:
        keyboard.press_and_release("ctrl+v")
    else:  # "type" : chiffre par chiffre. Attention : faux en AZERTY (chiffres = Maj + touche)
        for ch in str(value):
            keyboard.press_and_release(ch)
            time.sleep(0.01)
    done = "saisi"

    if validate and can_verify(cfg):
        time.sleep(0.06)
        ok, got = field_check(cfg, value)
        if not ok:
            validate = False   # mauvais collage (presse-papier, champ) : on ne vend PAS
            done = f"saisi, PAS validé (champ lu : {got if got is not None else '?'} au lieu de {value})"
    if validate:
        time.sleep(0.15 if not can_verify(cfg) else 0.03)
        if cfg.validate_method == "click" and cfg.sell_button:
            restore_mouse = restore_mouse or mouse_position()
            pyautogui.click(*cfg.sell_button)
        else:
            keyboard.press_and_release("enter")
        done = "saisi + mis en vente"
    if restore_mouse:
        pyautogui.moveTo(*restore_mouse)

    if use_clip:
        _schedule_restore(pyperclip, 1.0)  # laisser le jeu lire le presse-papier
    return done


FIELD_TRIES = 5          # relectures du champ, étalées sur ~0,5 s (le curseur clignote)
FIELD_RETRY_DELAY = 0.12
DEBUG_DIR = BASE_DIR / "captures"


def field_check(cfg: Config, expected: int, tries: int = FIELD_TRIES) -> Tuple[bool, Optional[int]]:
    """Le champ « Prix du lot » affiche-t-il bien `expected` ?
    Le curseur de saisie, collé au dernier chiffre, peut fausser une lecture : on relit sur
    ~0,5 s (il clignote), puis on demande un 2e avis à Tesseract seul. Toujours différent :
    refus, et l'image du champ est gardée dans captures/ pour comprendre."""
    got = None
    for i in range(tries):
        got = read_mine(cfg).value
        if got == expected:
            return True, got
        if i < tries - 1:
            time.sleep(FIELD_RETRY_DELAY)
    if cfg.fast_digits:
        second = read_mine(cfg, tesseract_only=True)
        if second.value == expected and second.confidence >= 80:
            print(f"[Champ] Lecture rapide {got} corrigée par Tesseract : {expected}.")
            img = mine_field_image(cfg)
            if img is not None:
                n = digit_reader().correct(img, str(expected))
                if n:
                    print(f"[Chiffres] {n} modèle(s) faux retiré(s) (ils faisaient lire {got}).")
            return True, expected
    save_field_debug(cfg, f"attendu{expected}_lu{got}")
    return False, got


def save_field_debug(cfg: Config, tag: str) -> None:
    """Image du champ « Prix du lot » quand la relecture refuse un prix (diagnostic)."""
    try:
        import cv2
        regions = mine_regions(cfg)
        if not regions:
            return
        DEBUG_DIR.mkdir(exist_ok=True)
        path = DEBUG_DIR / f"champ_refuse_{int(time.time() * 1000)}_{tag}.png"
        cv2.imwrite(str(path), grab_screen(regions[0]))
        print(f"[Champ] Prix refusé : image du champ enregistrée dans {path.name} (dossier captures).")
    except Exception:
        pass


def can_verify(cfg: Config) -> bool:
    return cfg.verify_before_enter and bool(mine_regions(cfg))


def press_validate(cfg: Config, expected: Optional[int] = None) -> bool:
    """Remet en vente au prix déjà affiché dans « Prix du lot » (le jeu le garde après une vente).
    Avec `expected` : vérifie d'abord le champ ; prix différent -> pas de validation (False)."""
    if expected is not None and can_verify(cfg) and not field_check(cfg, expected)[0]:
        return False
    import keyboard
    if cfg.validate_method == "click" and cfg.sell_button:
        import pyautogui
        back = mouse_position()
        pyautogui.click(*cfg.sell_button)
        pyautogui.moveTo(*back)
    else:
        keyboard.press_and_release("enter")
    return True


def press_modify(cfg: Config) -> None:
    """Valide la modification : clic sur « Modifier » si calibré, sinon Entrée."""
    import keyboard
    if cfg.modify_button:
        import pyautogui
        back = mouse_position()
        pyautogui.click(*cfg.modify_button)
        pyautogui.moveTo(*back)
    else:
        keyboard.press_and_release("enter")


def detect_panel(cfg: Config) -> Optional[str]:
    """Que montre le panneau de gauche ? Repère : la ligne des boutons, à hauteur de
    « Modifier ». Une de tes ventes -> deux boutons « Retirer | Modifier » séparés par un
    petit espace sombre ; objet de l'inventaire -> un seul grand bouton « Mettre en vente ».
    -> "relist" | "sell" | None (rien de sélectionné / pas calibré)."""
    if not cfg.modify_button:
        return None
    import cv2
    mx, my = cfg.modify_button
    x0 = mx - 130
    img = grab_screen((x0, my - 3, 125, 7))
    if img is None or img.size == 0:
        return None
    line = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY).mean(axis=0)
    if float(line.mean()) < 48:
        return None                      # tout sombre : panneau vide
    dark = line < 48
    runs, start = [], None
    for i, d in enumerate(list(dark) + [False]):
        if d and start is None:
            start = i
        elif not d and start is not None:
            runs.append((start, i))
            start = None
    for a, b in runs:
        # bords du creux : 2 px de tolérance (image adoucie quand le jeu est mis à l'échelle)
        if (2 <= b - a <= 15 and a > 0 and b < len(line)
                and line[max(0, a - 2):a].max() >= 55 and line[b:b + 2].max() >= 55):
            return "relist"
    return "sell"


def press_enter() -> None:
    import keyboard
    keyboard.press_and_release("enter")


# Fenêtre « Confirmer la mise en vente » : le jeu l'ouvre après « Modifier » quand le nouveau
# prix est loin de SON prix moyen, souvent pas à jour. Elle bloque l'HDV tant qu'on ne la
# valide pas (Entrée). Repérée par son titre (modèle à l'échelle de modele_hdv).
CONFIRM_TPL = APP_DIR / "modele_hdv" / "confirmation_titre.png"
CONFIRM_MIN = 0.88         # ressemblance minimale du bandeau de titre (HDV sans fenêtre : < 0.8)
MODEL_ROW_STEP = 49.6      # hauteur de ligne du modèle : échelle de l'HDV = relist_step / ceci
_confirm_cache: Dict[str, object] = {}


def hdv_monitor(cfg: "Config") -> Region:
    """Écran (moniteur) qui contient l'HDV ; tous les écrans si inconnu."""
    import mss
    r = cfg.table_region or cfg.anchor_region
    with mss.mss() as sct:
        if r:
            cx, cy = r[0] + r[2] // 2, r[1] + r[3] // 2
            for m in sct.monitors[1:]:
                if m["left"] <= cx < m["left"] + m["width"] and m["top"] <= cy < m["top"] + m["height"]:
                    return m["left"], m["top"], m["width"], m["height"]
        m = sct.monitors[0]
        return m["left"], m["top"], m["width"], m["height"]


def find_confirm_dialog(cfg: "Config", screen: Optional[np.ndarray] = None,
                        origin: Tuple[int, int] = (0, 0)) -> Optional[Point]:
    """Coin haut-gauche du bandeau « Confirmer la mise en vente » à l'écran, ou None.
    Recherche en demi-résolution légèrement floutée (tolère ±3 % d'échelle), à l'échelle
    de l'HDV puis ±5 et ±10 %, sur l'écran où se trouve l'HDV."""
    import cv2
    if "tpl" not in _confirm_cache:
        img = cv2.imread(str(CONFIRM_TPL)) if CONFIRM_TPL.exists() else None
        _confirm_cache["tpl"] = None if img is None else _gray(img)
    base = _confirm_cache["tpl"]
    if base is None:
        return None
    if screen is None:
        sx, sy, sw, sh = hdv_monitor(cfg)
        screen, origin = grab_screen((sx, sy, sw, sh)), (sx, sy)
    small = cv2.GaussianBlur(cv2.resize(_gray(screen), None, fx=0.5, fy=0.5, interpolation=cv2.INTER_AREA),
                             (0, 0), 1.0)
    hint = (cfg.relist_step / MODEL_ROW_STEP) if cfg.relist_step else 1.0
    scales = [_confirm_cache["scale"]] if _confirm_cache.get("scale") else []
    scales += [hint * f for f in (1.0, 0.95, 1.05, 0.9, 1.1)]
    for sc in scales:
        t = cv2.GaussianBlur(cv2.resize(base, None, fx=sc / 2, fy=sc / 2, interpolation=cv2.INTER_AREA),
                             (0, 0), 1.0)
        if min(t.shape) < 4 or t.shape[0] >= small.shape[0] or t.shape[1] >= small.shape[1]:
            continue
        _, score, _, (x, y) = cv2.minMaxLoc(cv2.matchTemplate(small, t, cv2.TM_CCOEFF_NORMED))
        if score >= CONFIRM_MIN:
            _confirm_cache["scale"] = sc
            return origin[0] + 2 * x, origin[1] + 2 * y
    return None


def click_at(p: Point) -> None:
    import pyautogui
    pyautogui.click(*p)


WHEEL_DELTA = 120  # un cran de molette sous Windows


SCROLL_HOVER = 0.04       # s entre l'arrivée de la souris sur la liste et la molette
SCROLL_RETRY_WAIT = 0.3   # s : liste immobile -> on laisse le jeu finir avant de réessayer
SCROLL_ZEROS = 3          # crans sans mouvement (avec attente) avant de conclure « en bas »


SCROLLBAR_SETTLE = 0.6    # s max pour que la poignée finisse de glisser avant d'être jugée
SCROLLBAR_BRIGHT = 90     # poignée de la barre de défilement : ~128 ; piste ~44 ; fond ~33


def find_scrollbar(gray: np.ndarray, min_len: int = 20, expect_x: Optional[int] = None,
                   min_track: int = 0) -> Optional[Tuple[int, int, int, int]]:
    """Barre de défilement verticale de la liste dans une image en niveaux de gris :
    (haut poignée, bas poignée, haut piste, bas piste) en px de l'image, ou None (pas de
    barre : la liste tient sur une page). Poignée = bande claire de 3 à 14 px de large ;
    la plus proche de `expect_x` (sinon la plus à droite), avec une piste d'au moins
    `min_track` px : le décor du jeu, à droite de l'HDV, peut contenir des bandes claires
    (vu : « fin de la liste » au milieu de la liste). Le cadre jaune de la ligne choisie ne
    fait que 1-2 px."""
    g = gray.astype(int)
    h, w = g.shape
    runs = []                     # (x, début, fin) du plus long segment clair de chaque colonne
    for x in range(w):
        col = np.concatenate(([False], g[:, x] > SCROLLBAR_BRIGHT, [False]))
        d = np.diff(col.astype(int))
        starts, ends = np.where(d == 1)[0], np.where(d == -1)[0] - 1
        if len(starts):
            i = int(np.argmax(ends - starts))
            if ends[i] - starts[i] + 1 >= min_len:
                runs.append((x, int(starts[i]), int(ends[i])))
    bands, cur = [], []
    for r in runs:                # colonnes voisines avec le même segment = une bande
        if cur and r[0] == cur[-1][0] + 1 and abs(r[1] - cur[0][1]) <= 2 and abs(r[2] - cur[0][2]) <= 2:
            cur.append(r)
        else:
            if cur:
                bands.append(cur)
            cur = [r]
    if cur:
        bands.append(cur)
    found = []
    for band in bands:
        if not 3 <= len(band) <= 14:
            continue
        xc = band[len(band) // 2][0]
        t0, t1 = band[0][1], band[0][2]
        out = g[:, min(w - 1, band[-1][0] + 2)]          # fond juste à droite de la barre
        track = (g[:, xc] - out >= 5) | (g[:, xc] > SCROLLBAR_BRIGHT)
        a, b = t0, t1
        while a > 0 and track[a - 1]:
            a -= 1
        while b < h - 1 and track[b + 1]:
            b += 1
        if b - a + 1 >= max(min_track, t1 - t0 + 1):
            found.append((xc, (t0, t1, a, b)))
    if not found:
        return None
    if expect_x is None:
        return found[-1][1]
    return min(found, key=lambda f: abs(f[0] - expect_x))[1]


def _scrollbar(cfg: "Config") -> Optional[Tuple[int, int, int, int]]:
    """Barre de défilement de la liste « mes ventes » (voir find_scrollbar), None si absente."""
    if not cfg.relist_row or cfg.relist_step <= 0:
        return None
    x0, y0 = cfg.relist_row
    step = cfg.relist_step
    region = (x0 + 2 * step, y0 - step, 4 * step, step * (cfg.relist_rows + 2))
    try:
        # La poignée glisse avec un léger retard sur la liste : on attend qu'elle soit
        # immobile (vu en vidéo : jugée « pas en bas » alors que la liste était au bout).
        wait_still(region, SCROLLBAR_SETTLE)
        img = grab_screen(region)
    except Exception:
        return None
    gray = img if img.ndim == 2 else __import__("cv2").cvtColor(img, __import__("cv2").COLOR_BGR2GRAY)
    # Barre à ~4 hauteurs de ligne à droite du point de clic (mesuré : 4,0 à 4,05 lignes).
    return find_scrollbar(gray, min_len=max(8, step // 3), expect_x=2 * step, min_track=3 * step)


def scrollbar_at_top(cfg: "Config") -> Optional[bool]:
    """Poignée en haut de sa piste (liste pas défilée) ? None = barre introuvable."""
    sb = _scrollbar(cfg)
    return None if sb is None else sb[0] <= sb[2] + 2


def scrollbar_at_bottom(cfg: "Config") -> Optional[bool]:
    """Poignée de la barre de défilement en bas de sa piste ? None = barre introuvable."""
    sb = _scrollbar(cfg)
    if sb is None:
        log_line("[MAJ TOUT] Barre de défilement introuvable.")
        return None
    t0, t1, a, b = sb
    log_line(f"[MAJ TOUT] Barre de défilement : poignée {t0}-{t1}, piste {a}-{b} "
             f"({'en bas' if t1 >= b - 2 else 'pas en bas'}).")
    return t1 >= b - 2


def scroll_at(p: Point, notches: int) -> None:
    """Molette vers le bas de `notches` crans. Sous Windows, pyautogui.scroll(n) envoie n
    BRUT (1 = 1/120 de cran) : il faut multiplier par 120, sinon la liste bouge à peine."""
    import pyautogui
    x, y = p
    # Petit mouvement puis pause : le jeu (Unity) doit « voir » la souris sur la liste avant la
    # molette. Souris téléportée puis molette aussitôt, ou liste redessinée après « Modifier » :
    # la molette était parfois ignorée, et Ctrl+F3 croyait la liste finie.
    pyautogui.moveTo(x, y + 3)
    pyautogui.moveTo(x, y)
    time.sleep(SCROLL_HOVER)
    pyautogui.scroll(-abs(notches) * (WHEEL_DELTA if IS_WINDOWS else 1))


def measure_shift(before: np.ndarray, after: np.ndarray, step: int,
                  expected: Optional[int] = None) -> Optional[int]:
    """Déplacement vers le haut (px) du contenu de la liste entre deux captures.
    Bande de 2 lignes de `after` recherchée dans `before`. Lignes identiques (même objet,
    même prix) = plusieurs positions possibles : on garde la plus proche du déplacement
    précédent (un cran de molette défile toujours pareil), sinon la plus petite.
    None = introuvable (défilé de plus de ~6 lignes d'un coup)."""
    import cv2
    a = cv2.cvtColor(before, cv2.COLOR_BGR2GRAY) if before.ndim == 3 else before
    b = cv2.cvtColor(after, cv2.COLOR_BGR2GRAY) if after.ndim == 3 else after
    if a.shape != b.shape:
        return None
    if np.abs(a.astype(int) - b.astype(int)).mean() < 0.5:
        return 0
    h = a.shape[0]
    band_y, band_h = step, min(2 * step, h - step - 1)
    if band_h < step // 2:
        return None
    band = b[band_y:band_y + band_h]
    res = cv2.matchTemplate(a[band_y:], band, cv2.TM_CCOEFF_NORMED)[:, 0]
    best = float(res.max())
    if best < 0.8:
        return None
    cands = [int(i) for i in np.where(res >= best - 0.03)[0]]
    # positions voisines = même pic : garder le centre de chaque pic
    peaks, cur = [], [cands[0]]
    for c in cands[1:]:
        if c - cur[-1] <= 2:
            cur.append(c)
        else:
            peaks.append(cur)
            cur = [c]
    peaks.append(cur)
    ds = [max(p, key=lambda i: res[i]) for p in peaks]
    if expected:
        return min(ds, key=lambda d: (abs(d - expected), d))
    return min(ds)


def _key_down_windows(scan_code: int) -> Optional[bool]:
    """La touche (code de balayage) est-elle physiquement enfoncée ? None = inconnu."""
    import ctypes
    user32 = ctypes.windll.user32
    vk = user32.MapVirtualKeyW(scan_code, 1)   # MAPVK_VSC_TO_VK : Ctrl/Maj/Alt sans gauche/droite
    if not vk:
        return None
    return bool(user32.GetAsyncKeyState(vk) & 0x8000)


def release_stuck_keys(kb=None, is_down=None) -> List[str]:
    """Le module `keyboard` reconnaît un raccourci en comparant l'ensemble EXACT des touches
    qu'il croit enfoncées. S'il rate un relâchement (Windows abandonne un événement quand
    l'écouteur répond trop tard, pendant un calcul lourd), la touche reste « enfoncée » pour
    lui : Ctrl+F3 devient Ctrl+F3+V et plus AUCUN raccourci ne marche, jusqu'au redémarrage.
    On demande à Windows l'état réel et on libère les touches qui ne sont plus enfoncées.
    Retourne les noms des touches libérées."""
    if kb is None:
        if not IS_WINDOWS:
            return []
        try:
            import keyboard as kb
        except Exception:
            return []
    is_down = is_down or _key_down_windows
    pressed = getattr(kb, "_pressed_events", None)
    lock = getattr(kb, "_pressed_events_lock", None)
    if pressed is None or lock is None:
        return []
    freed = []
    with lock:
        for sc, ev in list(pressed.items()):
            try:
                down = is_down(sc)
            except Exception:
                down = None
            if down is False:
                del pressed[sc]
                getattr(kb, "_logically_pressed_keys", {}).pop(sc, None)
                listener = getattr(kb, "_listener", None)
                if listener is not None and hasattr(listener, "active_modifiers"):
                    listener.active_modifiers.discard(sc)
                freed.append(str(getattr(ev, "name", None) or sc))
    return freed

