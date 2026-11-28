"""Moteur : lecture -> contrôles -> saisie (F1, F3, Tout vendre, Toute la liste)."""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Dict, List, Optional, Tuple

import numpy as np

from .base import log_line
from .pricing import check_coherence, compute_price, derive_price, floor_price, pick_best_lot
from .ocr import (
    detect_rows,
    digit_reader,
    ENGINE_STATS,
    grab_screen,
    mine_field_image,
    mine_regions,
    mine_second_opinions,
    MINE_SURE,
    read_counter,
    read_mine,
    read_screen,
    Reading,
    RELIST_READ_TRIES,
    _same_row,
    ScreenRead,
    surer,
    table_second_read,
    vote_mine,
    wait_any_change,
    wait_change,
    wait_still,
)
from .anchor import (
    ANCHOR_OK,
    anchor_path,
    anchor_score,
    find_anchor,
    load_anchor,
    rect_from_points,
    save_anchor,
    screen_bounds,
    shift_zones,
)
from .game import (
    can_verify,
    click_at,
    detect_panel,
    field_check,
    find_confirm_dialog,
    input_price,
    measure_shift,
    mouse_position,
    press_enter,
    press_modify,
    press_validate,
    scroll_at,
    SCROLL_RETRY_WAIT,
    SCROLL_ZEROS,
    scrollbar_at_bottom,
    scrollbar_at_top,
)
from .history import grab_name, log_history
from .my_prices import item_key, MY_PRICES_PATH, MyPrices

if TYPE_CHECKING:
    from .base import Point, Region
    from .config import Config


# --------------------------------------------------------------------------
# Moteur : lecture -> contrôles -> saisie
# --------------------------------------------------------------------------
@dataclass
class Result:
    lot: Optional[int]
    level: str              # "ok" | "warn" | "error"
    message: str
    screen: ScreenRead = field(default_factory=ScreenRead)
    new_price: Optional[int] = None
    hint: str = ""          # texte court pour la popup
    floored_top: Optional[int] = None  # prix concurrent ignoré car sous le plancher
    old_price: Optional[int] = None    # mes ventes : ton prix avant la mise à jour
    item_img: Optional[np.ndarray] = None   # image du nom de l'objet (résumé Ctrl+F3)
    changes: List["RowChange"] = field(default_factory=list)   # Ctrl+F3 : résumé ligne par ligne
    summary: Dict = field(default_factory=dict)   # Ctrl+F3 : lignes vues, modifiées, au bon prix, arrêt, durée


@dataclass
class RowChange:
    """Une ligne du résumé de Ctrl+F3 : prix modifié, ou ligne laissée telle quelle (douteuse)."""
    row: int                     # numéro de la ligne dans la liste (1 = la première)
    lot: Optional[int]
    old: Optional[int]           # ton prix avant
    new: Optional[int]           # nouveau prix (ou prix proposé si non modifié)
    modified: bool
    note: str = ""               # pourquoi la ligne n'a pas été modifiée
    img: Optional[np.ndarray] = None   # image du nom de l'objet

    def text(self) -> str:
        lot = f"lot {self.lot}" if self.lot else "lot ?"
        if self.modified and self.old and self.new:
            return (f"ligne {self.row} · {lot} : {self.old:,} → {self.new:,} "
                    f"({(self.new - self.old) / self.old:+.1%})").replace(",", " ")
        return f"ligne {self.row} · {lot} : NON modifiée ({self.note})"


AUTO_RECAL_RETRY = 30.0   # s entre deux recalibrations automatiques ratées
CONFIRM_CLOSE_WAIT = 1.0   # s : après Entrée, la fenêtre de confirmation doit se fermer
RELIST_CONFIRM_WAIT = 2.0  # s : après « Modifier », ancien prix encore lu -> on relit jusque-là
CLICK_PAUSE = 0.02        # s après chaque clic / mouvement de souris (pyautogui : 0,1 par défaut)
TIMING_STAGES = ("clic", "lecture", "saisie", "validation", "défilement")


def timing_text(total: float, rows: int, timing: Dict[str, float]) -> str:
    """« durée 1 min 05 s, 0,9 s/ligne (clic 0,15 · lecture 0,30 · …) » : où part le temps."""
    m, s = divmod(int(round(total)), 60)
    out = f"durée {m} min {s:02d} s" if m else f"durée {total:.1f} s".replace(".", ",")
    if rows <= 0:
        return out
    parts = [f"{k} {timing[k] / rows:.2f}".replace(".", ",") for k in TIMING_STAGES if timing.get(k)]
    other = total - sum(timing.get(k, 0.0) for k in TIMING_STAGES)
    if other > 0.05 * total:
        parts.append(f"autre {other / rows:.2f}".replace(".", ","))
    return out + f", {total / rows:.2f} s/ligne".replace(".", ",") + (f" ({' · '.join(parts)})" if parts else "")


class PriceEngine:
    """Utilisé par la GUI et la CLI. Thread-safe (un seul traitement à la fois)."""

    def __init__(self, cfg: Config, debug_dir: Optional[Path] = None):
        self.cfg = cfg
        self.debug_dir = debug_dir
        self.paused = False
        self._lock = threading.Lock()
        self._pending: Optional[Tuple[int, int, float]] = None  # (lot, prix, t) à confirmer
        self._dialog: Optional[str] = None   # fenêtre de confirmation : None / "ok" / "open"
        self._first_point: Dict[str, Tuple[Point, float]] = {}
        self.my_prices = MyPrices(MY_PRICES_PATH)   # tes ventes : pas d'undercut contre toi-même
        self.progress = None   # Ctrl+F3 : appelé avec le Result de chaque ligne (journal en direct)
        self.on_loop_progress = None   # Ctrl+F3 : appelé avec un dict (ligne, faites, modifiées, à revoir, total)
        self.stop_requested = False    # bouton « Arrêter » : finit la boucle en cours sans mettre en pause
        self.last_anchor_msg = ""  # dernier message du repère HDV (lu puis vidé par l'interface)
        self._autocal_failed = 0.0  # heure du dernier échec de recalibration automatique
        self.timing: Dict[str, float] = {}   # Ctrl+F3 : temps total par étape (s)
        try:
            # pyautogui attend 0,1 s après CHAQUE clic ou mouvement : ~0,5 s par prix modifié.
            # Les attentes utiles sont déjà faites par l'outil (changement guetté à l'écran).
            import pyautogui
            pyautogui.PAUSE = CLICK_PAUSE
        except Exception:
            pass

    # ---- calibration ----
    def calibrate_rect(self, name: str, pos: Optional[Point] = None) -> Tuple[str, object]:
        """Zone en 2 appuis. name = "table" | "qty" | "avg" | "count".
        Retourne ("first", point) puis ("done", region)."""
        p = pos or mouse_position()
        first = self._first_point.get(name)
        if first is None or time.time() - first[1] > 30:
            self._first_point[name] = (p, time.time())
            return "first", p
        del self._first_point[name]
        region = rect_from_points(first[0], p)
        setattr(self.cfg, f"{name}_region", list(region))
        if name == "anchor":
            save_anchor(grab_screen(region), anchor_path(self.cfg))
        self.cfg.save()
        return "done", region

    # ---- repère : l'HDV a bougé -> toutes les zones suivent
    def _reanchor(self) -> Optional[Tuple[int, int]]:
        """Si le titre « Hôtel de vente » n'est plus à sa place, le retrouve à l'écran et
        décale TOUTES les zones et tous les points d'autant. Retourne le décalage (dx, dy)
        appliqué, ou None (pas de repère, pas bougé, ou introuvable)."""
        cfg = self.cfg
        if not cfg.anchor_region:
            return None
        tpl = load_anchor(anchor_path(cfg))
        if tpl is None:
            return None
        x, y, w, h = cfg.anchor_region
        try:
            if anchor_score(grab_screen((x, y, w, h)), tpl) >= ANCHOR_OK:
                return None                       # pas bougé (cas normal, ~1 ms)
            found = find_anchor(tpl)
        except Exception as e:
            self.last_anchor_msg = f"Repère HDV : erreur ({e})"
            return None
        if found is None:
            if self._auto_recalibrate():
                return None
            self.last_anchor_msg = "Repère HDV introuvable : HDV fermé ou caché ? Zones inchangées."
            return None
        dx, dy = found[0] - x, found[1] - y
        if dx == 0 and dy == 0:
            return None
        shift_zones(cfg, dx, dy)
        cfg.save()
        self.last_anchor_msg = f"HDV déplacé de ({dx:+d}, {dy:+d}) px : zones recalées."
        return dx, dy

    def calibrate_auto(self):
        """Trouve l'HDV à l'écran et place TOUTES les zones du profil actif (dofus_autocal).
        Ne change rien si l'HDV n'est pas reconnu. Retourne le résultat (AutoCal)."""
        with self._lock:
            return self._autocal_now()

    def _autocal_now(self):
        import dofus_autocal
        sx, sy, sw, sh = screen_bounds()
        screen = grab_screen((sx, sy, sw, sh))
        res = dofus_autocal.locate(screen, (sx, sy))
        if res.ok:
            dofus_autocal.apply(self.cfg, res, screen, (sx, sy))
            self.cfg.save()
            self._autocal_failed = 0.0
        return res

    def _auto_recalibrate(self) -> bool:
        """Repère introuvable : l'HDV a souvent changé de TAILLE (échelle de l'interface,
        résolution), ce que le repère ne suit pas. On refait la calibration automatique
        (~1 s). Échec (HDV fermé, autre langue…) : rien ne change, nouvel essai dans 30 s
        au plus tôt pour ne pas ralentir chaque raccourci."""
        if not self.cfg.auto_recalibrate or time.time() - self._autocal_failed < AUTO_RECAL_RETRY:
            return False
        try:
            res = self._autocal_now()
        except Exception:
            res = None
        if res is None or not res.ok:
            self._autocal_failed = time.time()
            return False
        self.last_anchor_msg = (f"Taille de l'HDV changée : calibration automatique refaite "
                                f"(taille ×{res.scale:.2f}), zones recalées.")
        return True

    def calibrate_point(self, name: str, pos: Optional[Point] = None) -> Point:
        """name = "price_field" | "sell_button" | "modify_button"."""
        x, y = pos or mouse_position()
        setattr(self.cfg, name, [x, y])
        if name == "price_field":
            self.cfg.click_field = True
        self.cfg.save()
        return x, y

    def calibrate_rows(self, pos: Optional[Point] = None) -> Tuple[str, object]:
        """2 appuis : centre de la 1re ligne visible, puis de la 2e -> position + hauteur de ligne."""
        p = pos or mouse_position()
        first = self._first_point.get("rows")
        if first is None or time.time() - first[1] > 30:
            self._first_point["rows"] = (p, time.time())
            return "first", p
        del self._first_point["rows"]
        step = abs(p[1] - first[0][1])
        if step < 10:
            return "error", "les 2 lignes sont trop proches : clique sur la 1re puis la 2e ligne"
        self.cfg.relist_row, self.cfg.relist_step = list(first[0]), int(step)
        self.cfg.save()
        return "done", (tuple(first[0]), step)

    # ---- F1 « une seule touche » ----
    def smart(self) -> Result:
        """F1 : une de tes ventes sélectionnée -> mise à jour du prix (comme F3) ;
        sinon (objet de l'inventaire) -> vente (comme avant)."""
        if self.cfg.smart_f1:
            try:
                self._reanchor()
                mode = detect_panel(self.cfg)
            except Exception:
                mode = None
            if mode == "relist":
                return self.relist()
        return self.sell(False)

    # ---- mes ventes : mise à jour des prix ----
    def relist(self) -> Result:
        """Vente sélectionnée dans « mes ventes » : si quelqu'un est moins cher, nouveau prix
        + « Modifier ». Si le moins cher, c'est toi : rien."""
        if not self._lock.acquire(blocking=False):
            return Result(None, "warn", "Lecture déjà en cours, ignoré.")
        try:
            self._reanchor()
            return self._relist()
        except Exception as e:
            return Result(None, "error", f"Erreur: {e}", hint="Erreur")
        finally:
            self._lock.release()

    def relist_all(self) -> Result:
        if not self._lock.acquire(blocking=False):
            return Result(None, "warn", "Lecture déjà en cours, ignoré.")
        try:
            self._reanchor()
            return self._relist_all()
        except Exception as e:
            return Result(None, "error", f"Erreur: {e}", hint="Erreur")
        finally:
            self._lock.release()

    def _relist(self, auto: bool = False) -> Result:
        """auto=True (boucle) : jamais de forçage, une lecture suspecte arrête la boucle.
        Le résultat porte ton ancien prix et l'image du nom de l'objet (résumé Ctrl+F3)."""
        self._row_ctx = {}
        res = self._relist_row(auto)
        res.old_price = self._row_ctx.get("old")
        res.item_img = self._row_ctx.get("img")
        return res

    def _tick(self, stage: str, t0: float) -> float:
        """Ajoute le temps écoulé depuis t0 à l'étape `stage` ; retourne l'heure actuelle."""
        now = time.perf_counter()
        self.timing[stage] = self.timing.get(stage, 0.0) + now - t0
        return now

    def _relist_row(self, auto: bool) -> Result:
        cfg = self.cfg
        tag = "MAJ"
        t0 = time.perf_counter()
        if not cfg.table_region or not cfg.qty_region:
            return Result(None, "error", f"[{tag}] Calibre d'abord le tableau et la quantité.",
                          hint="Calibration manquante")
        if not mine_regions(cfg):
            return Result(None, "error",
                          f"[{tag}] Champ « Prix du lot » non calibré ({cfg.hotkeys['calibrate_field']}).",
                          hint="Calibre Prix du lot")
        # Juste après un clic, quantité ou tableau peuvent être encore illisibles :
        # on relit jusqu'à ~1 s tant que quantité ou prix du lot manquent.
        for attempt in range(RELIST_READ_TRIES):
            sr = read_screen(cfg, self.debug_dir, with_mine=True)
            if sr.selected is not None and sr.prices.get(sr.selected) is not None:
                break
            if attempt < RELIST_READ_TRIES - 1:
                time.sleep(0.12)
        name_img = grab_name(cfg)  # avant « Modifier » : le panneau se vide ensuite
        key = item_key(name_img)
        self._row_ctx["img"] = name_img
        self._row_ctx["key"] = key
        mine = sr.mine_r
        if mine is None or mine.value is None or mine.confidence < MINE_SURE:
            mine = surer(mine, read_mine(cfg))  # 2e lecture seule, plus grande : la plus sûre
        lot = sr.selected
        t0 = self._tick("lecture", t0)
        if lot is None:
            return Result(None, "error", f"[{tag}] Quantité illisible (lu : {sr.selected_raw!r}).", sr,
                          hint="Quantité illisible")
        if mine.value is None:
            return Result(lot, "error", f"[{tag}] Ton prix illisible (zone {cfg.hotkeys['calibrate_mine']}).",
                          sr, hint="Ton prix illisible")
        top = sr.prices.get(lot)
        if top is None or top.value is None:
            return Result(lot, "error", f"[{tag}] Lot {lot} : aucun prix lu dans le tableau.", sr,
                          hint="Aucun prix lu")
        if top.value < mine.value:
            # Une modification va suivre : « ton prix » relu deux autres fois, vote à la majorité.
            # (459 lu 489 : l'outil collait 459, « Modifier » grisé, et recommençait sans fin.)
            voted, detail = vote_mine(mine, mine_second_opinions(cfg), cfg.min_confidence)
            if voted is None:
                return Result(lot, "warn", f"[{tag}] Lot {lot} | ton prix douteux (lectures : {detail}), "
                              "ligne passée", sr, hint="Ton prix douteux")
            if voted != mine.value:
                print(f"[Champ] Ton prix relu : {voted} (lecture rapide {mine.value} ; lectures : {detail}).")
                img = mine_field_image(cfg)
                if img is not None and cfg.fast_digits:
                    digit_reader().correct(img, str(voted))
                mine = Reading(voted, max(mine.confidence, cfg.min_confidence))
        head = f"[{tag}] Lot {lot} | ton prix {mine.value} | moins cher {top.value}"
        self._row_ctx["old"] = mine.value
        if key is not None and mine.confidence >= cfg.min_confidence:
            self.my_prices.add(key, lot, mine.value)     # une de tes ventes est à ce prix
        if top.value >= mine.value:
            msg = "déjà le moins cher" if top.value == mine.value else "ton prix est déjà plus bas"
            log_history("observe", lot, lot, top, mine.value, "cheapest", cfg)
            return Result(lot, "ok", f"{head} | {msg}, rien à faire", sr, mine.value, hint="Déjà le moins cher")

        own = self.my_prices.has(key, lot, top.value, cfg.own_price_ttl)
        new_p = top.value if own else compute_price(top.value, cfg.undercut_mode, cfg.undercut_value,
                                                    cfg.rounding, cfg.min_price)
        # ---- plancher : un concurrent qui brade ne fait pas baisser sous FLOOR_RATIO × prix moyen
        fp = floor_price(lot, sr.avg, cfg.floor_ratio) if cfg.floor_mode != "stop" else None
        floored = fp is not None and new_p < fp
        if floored:
            if cfg.floor_mode == "keep":
                log_history("observe", lot, lot, top, mine.value, "floor_keep", cfg)
                return Result(lot, "ok", f"{head} | sous le plancher ({fp}) : ton prix gardé, rien à faire",
                              sr, mine.value, hint="Plancher : prix gardé", floored_top=top.value)
            new_p = fp
            if mine.value <= new_p:
                log_history("observe", lot, lot, top, mine.value, "at_floor", cfg)
                return Result(lot, "ok", f"{head} | déjà au plancher ({fp}), rien à faire", sr,
                              mine.value, hint="Déjà au plancher", floored_top=top.value)
        problems = []
        for name, r in (("tableau", top), ("ton prix", mine)):
            if r.confidence < cfg.min_confidence:
                problems.append(f"confiance OCR {name} {r.confidence:.0f} < {cfg.min_confidence:.0f}")
        incoh = check_coherence(lot, sr.values, cfg.max_ratio)
        if incoh:
            problems.append(incoh)
        unit = new_p / lot
        if (cfg.floor_mode == "stop" and cfg.min_avg_ratio > 0 and sr.avg
                and unit < sr.avg * cfg.min_avg_ratio):
            problems.append(f"{unit:.0f}/u < {cfg.min_avg_ratio:.0%} du prix moyen ({sr.avg}/u)")
        if new_p < mine.value / cfg.max_ratio:
            problems.append(f"baisse énorme : {mine.value} -> {new_p}")
        if floored:  # le concurrent brade : son prix ne sert pas, la cohérence entre lots non plus
            problems = [p for p in problems if not p.startswith("prix unitaire")]

        prefix = (f"{head} -> {new_p}{' (aligné sur ton autre vente)' if own else ''}"
                  f"{f' (plancher {cfg.floor_ratio:.0%} du prix moyen {sr.avg})' if floored else ''}")
        if problems and cfg.relist_force_suspect and not any(p.startswith("confiance OCR") for p in problems):
            # Option « modifier même si suspect » : le marché peut chuter d'un jour à l'autre.
            # Seuls les doutes sur le PRIX sont levés (jamais une lecture peu fiable), et
            # seulement si une 2e lecture indépendante redonne exactement le même prix.
            sr2 = table_second_read(cfg, sr.engine)
            top2 = sr2.prices.get(lot)
            if sr2.selected == lot and top2 is not None and top2.value == top.value:
                prefix += f" [suspect accepté : {'; '.join(problems)}]"
                problems = []
            else:
                problems.append(f"2e lecture différente ({top2.value if top2 else '?'})")
        now = time.time()
        forced = (not auto and self._pending is not None and self._pending[:2] == (-lot, new_p)
                  and now - self._pending[2] <= cfg.confirm_window)
        if problems and not forced:
            self._pending = (-lot, new_p, now)   # lot négatif : ne pas confondre avec F1
            input_price(new_p, cfg, paste=False)
            log_history("read", lot, lot, top, new_p, "relist_suspect", cfg)
            return Result(lot, "warn", f"{prefix} | SUSPECT ({'; '.join(problems)}). Copié seulement."
                          + ("" if auto else f" Ré-appuie dans {cfg.confirm_window:.0f}s pour forcer."),
                          sr, new_p, hint="Suspect")
        self._pending = None
        t0 = time.perf_counter()
        input_price(new_p, cfg, paste=True, validate=False)
        time.sleep(0.06)
        if can_verify(cfg):
            ok, got = field_check(cfg, new_p)
        t0 = self._tick("saisie", t0)
        if can_verify(cfg):
            if not ok:
                log_history("relist", lot, lot, top, new_p, "not_validated", cfg)
                return Result(lot, "warn", f"{prefix} | collé mais PAS modifié : le champ affiche "
                              f"{got if got is not None else '?'} au lieu de {new_p}", sr, new_p,
                              hint="Prix collé incorrect")
        mine_box = mine_regions(cfg)[0]
        before = grab_screen(mine_box)
        press_modify(cfg)
        self.my_prices.add(key, lot, new_p, sure=False)   # sûr seulement une fois confirmé
        wait_change(mine_box, before, cfg.relist_delay)
        # Après « Modifier », le jeu désélectionne la vente : panneau vide (« Veuillez
        # sélectionner un objet ») = modification acceptée. Ancien prix encore affiché = échec.
        self._dialog = None
        check = self._await_new_price(mine.value, new_p)
        if self._dialog is None and check.value is not None:
            self._confirm_dialog()            # panneau pas vidé : fenêtre apparue entre-temps ?
        if self._dialog == "open":
            log_history("relist", lot, lot, top, new_p, "unconfirmed", cfg)
            return Result(lot, "warn", f"{prefix} | fenêtre « Confirmer la mise en vente » toujours "
                          "ouverte après Entrée : valide-la à la main", sr, new_p, hint="Confirmation bloquée")
        confirmed = " (confirmation validée)" if self._dialog == "ok" else ""
        if (self._dialog is None and check.value is not None and check.confidence >= cfg.min_confidence
                and cfg.relist_confirm_enter):
            # Panneau pas vidé : souvent la fenêtre de confirmation du changement de prix.
            # Entrée la valide (sans elle, la vente reste sélectionnée).
            before = grab_screen(mine_box)
            press_enter()
            wait_change(mine_box, before, cfg.relist_delay)
            check = self._await_new_price(mine.value)
            confirmed = " (Entrée de secours)" if self._dialog is None else " (confirmation validée)"
        self._tick("validation", t0)
        if check.value is None or check.confidence < cfg.min_confidence:
            self.my_prices.add(key, lot, new_p, replaces=mine.value)
            log_history("relist", lot, lot, top, new_p, "forced" if forced else "modified", cfg)
            return Result(lot, "ok", f"{prefix} | modifié{' (forcé)' if forced else ''}{confirmed}",
                          sr, new_p, hint=f"Modifié : {new_p}")
        if check.value != new_p:
            log_history("relist", lot, lot, top, new_p, "unconfirmed", cfg)
            return Result(lot, "warn", f"{prefix} | modification NON confirmée (lu ensuite : "
                          f"{check.value if check.value is not None else '?'})", sr, new_p,
                          hint="Modif. non confirmée")
        self.my_prices.add(key, lot, new_p, replaces=mine.value)
        log_history("relist", lot, lot, top, new_p, "forced" if forced else "modified", cfg)
        return Result(lot, "ok", f"{prefix} | modifié{' (forcé)' if forced else ''}{confirmed}",
                      sr, new_p, hint=f"Modifié : {new_p}")

    def _await_new_price(self, old: Optional[int], new: Optional[int] = None) -> "Reading":
        """Champ « Prix du lot » après « Modifier ». Le jeu peut réafficher un instant
        l'ANCIEN prix avant de vider le panneau ou de montrer le nouveau (serveur lent) :
        tant que l'ancien prix est lu, on relit, jusqu'à RELIST_CONFIRM_WAIT s. Sans cela,
        une modification réussie était prise pour un échec et Ctrl+F3 s'arrêtait.
        Le champ montre le NOUVEAU prix quand le jeu demande confirmation (prix loin de son
        prix moyen) : on cherche alors la fenêtre et on la valide (Entrée)."""
        check = read_mine(self.cfg)
        end = time.time() + RELIST_CONFIRM_WAIT
        shown = {v for v in (old, new) if v is not None}
        while (check.value in shown and check.confidence >= self.cfg.min_confidence
               and time.time() < end and self._dialog != "open"):
            if self._confirm_dialog():
                end = time.time() + RELIST_CONFIRM_WAIT
            else:
                time.sleep(0.1)
            check = read_mine(self.cfg)
        return check

    def _confirm_dialog(self) -> Optional[str]:
        """Fenêtre « Confirmer la mise en vente » ouverte -> Entrée (deux essais).
        Note self._dialog : "ok" (validée), "open" (toujours ouverte). None si pas de fenêtre."""
        cfg = self.cfg
        if not cfg.relist_confirm_enter or find_confirm_dialog(cfg) is None:
            return None
        for _ in range(2):
            press_enter()
            end = time.time() + CONFIRM_CLOSE_WAIT
            while time.time() < end:
                time.sleep(0.1)
                if find_confirm_dialog(cfg) is None:
                    self._dialog = "ok"
                    return "ok"
        self._dialog = "open"
        return "open"

    def _page_rows(self, shift: int, base: int) -> List[Tuple[int, int]]:
        """Lignes à cliquer : détectées à l'écran (centres exacts) si possible, sinon
        calculées depuis le défilement mesuré. Numéro global = position depuis `base`
        (centre de la 1re ligne au départ) + défilement cumulé."""
        cfg = self.cfg
        x0, y0 = cfg.relist_row
        step = cfg.relist_step
        top = y0 - step // 2 - step // 3
        strip = grab_screen((x0 - 60, top, 240, step * cfg.relist_rows + 2 * (step // 3)))
        ys = detect_rows(strip, top, step)
        if len(ys) >= 2 and all(abs((b - a) - step) <= 0.25 * step for a, b in zip(ys, ys[1:])):
            return [(y, int(round((y - base + shift) / step))) for y in ys]
        return self._visible_rows(shift + (y0 - base))

    def _visible_rows(self, shift: int) -> List[Tuple[int, int]]:
        """Lignes cliquables après un défilement de `shift` px depuis le haut :
        [(y écran du centre, numéro global de la ligne)]. Le jeu défile au pixel près :
        une ligne trop coupée en haut est ignorée (elle a déjà été traitée)."""
        cfg = self.cfg
        x0, y0 = cfg.relist_row
        step = cfg.relist_step
        offset = shift % step
        y = y0 - offset
        if offset > 0.35 * step:
            y += step
        # En bas de la liste, le jeu laisse la dernière ligne ~0,32 ligne plus bas, entièrement
        # visible (vidéo du joueur) : avec 0,3, elle était oubliée.
        y_max = y0 + (cfg.relist_rows - 1) * step + 0.4 * step
        rows = []
        while y <= y_max:
            rows.append((int(y), int(round((y - y0 + shift) / step))))
            y += step
        return rows

    def _scroll_page(self, box: Region, target: int) -> Tuple[int, Optional[str]]:
        """Molette cran par cran en MESURANT le déplacement réel de la liste, jusqu'à
        `target` px (≈ une page moins une ligne). Retourne (px défilés, erreur).
        0 px après 2 crans = bas de la liste."""
        cfg = self.cfg
        x0, y0 = cfg.relist_row
        anchor = (x0, y0 + cfg.relist_step)
        prev = grab_screen(box)
        total, zeros, per_notch, notches = 0, 0, None, 0
        max_jump = 5 * cfg.relist_step     # au-delà, la mesure ne retrouve plus la liste
        while notches < cfg.relist_scroll_max:
            # 1er essai : 1 cran pour mesurer ; ensuite autant de crans que nécessaire d'un coup
            n = 1
            if per_notch:
                n = max(1, min(int((target - total) // per_notch), int(max_jump // per_notch)))
            scroll_at(anchor, n)
            notches += n
            time.sleep(0.12)
            img = grab_screen(box)
            d = measure_shift(prev, img, cfg.relist_step, per_notch * n if per_notch else None)
            if d is None:
                return total, "défilement non suivi (liste méconnaissable entre deux crans)"
            prev = img
            if d == 0:
                zeros += 1
                if zeros >= SCROLL_ZEROS:
                    break
                time.sleep(SCROLL_RETRY_WAIT)    # jeu occupé (liste redessinée) : on réessaie
                prev = grab_screen(box)
                continue
            zeros, total = 0, total + d
            per_notch = per_notch or d / n
            if total >= target:
                break
        wait_still(box, cfg.relist_delay)  # fin d'une éventuelle animation (≤ RELIST_DELAY)
        img = grab_screen(box)
        d = measure_shift(prev, img, cfg.relist_step, None)
        if d is None:
            return total, "défilement non suivi (animation)"
        return total + d, None

    def _note_listed(self, listed: set, res: "Result") -> bool:
        """Note la vente de cette ligne (clé, lot, prix actuel). False si on ne le sait pas
        (nom ou prix illisible) : la liste vue est alors incomplète."""
        key = getattr(self, "_row_ctx", {}).get("key")
        modified = res.level == "ok" and "modifié" in res.message
        price = res.new_price if modified else res.old_price
        if key is None or res.lot is None or price is None:
            return False
        listed.add((key, res.lot, price))
        return True

    def _rows_left(self, seen: int, total: Optional[int]) -> int:
        """Ventes restant à voir d'après le compteur (0 si inconnu ou presque fini : la
        mesure du défilement peut être décalée d'une ou deux lignes)."""
        cfg = self.cfg
        if total is None and cfg.count_region:
            try:
                c = read_counter(cfg)
                total = c[0] if c else None
            except Exception:
                total = None
        if not total:
            return 0
        left = total - (seen + 1)
        return left if left > 2 else 0

    def _relist_all(self) -> Result:
        """Parcourt la liste « mes ventes » : clic sur chaque ligne visible, mise à jour,
        puis défilement mesuré et lignes suivantes. Arrêt : bas de la liste, lecture
        suspecte, modification non confirmée, pause, RELIST_MAX lignes."""
        cfg = self.cfg
        if not cfg.relist_auto:
            return Result(None, "warn", "[MAJ] Mode boucle désactivé (interrupteur « toute la liste » "
                          f"ou RELIST_AUTO). Utilise {cfg.hotkeys['relist']} ligne par ligne.",
                          hint="Boucle désactivée")
        if not cfg.relist_row or cfg.relist_step <= 0:
            return Result(None, "error", f"[MAJ] Lignes non calibrées ({cfg.hotkeys['calibrate_rows']} ×2).",
                          hint="Calibre les lignes")
        x0, y0 = cfg.relist_row
        step = cfg.relist_step
        # bande de la liste (noms, durée, lot, prix ; sans la barre de défilement)
        box = (x0 - 80, y0 - step // 2, 260, step * cfg.relist_rows)
        back = mouse_position()
        done = changed = same = pages = shift = 0
        seen = -1                     # plus grand numéro global de ligne déjà traité
        # Origine = 1re ligne visible MAINTENANT (la liste a pu être défilée à la main).
        first = self._page_rows(0, y0)
        base = first[0][0] if first else y0
        rows0 = self._page_rows(0, base)
        # Souris posée sur une ligne de la liste : on commence à cette ligne (reprise).
        mx, my = back
        start_note = ""
        if rows0 and x0 - 150 <= mx <= x0 + 420 and rows0[0][0] - step // 2 <= my <= rows0[-1][0] + step // 2:
            y_s, g_s = min(rows0, key=lambda r: abs(r[0] - my))
            seen = g_s - 1
            start_note = ", départ ligne sous la souris"
        last_click = None
        page_last_y = None           # y de la dernière ligne traitée sur la page affichée
        swept = False                 # fin de liste : lignes sous la dernière traitée revues
        ok_rows: List[np.ndarray] = []  # images de lignes déjà au bon prix (même objet, même prix)
        bad: List[str] = []           # lignes douteuses laissées telles quelles
        fails = 0                     # lignes douteuses consécutives
        last_mod = None               # dernière modification (ligne, lot, ancien, nouveau)
        skipped = 0
        mine_box = (mine_regions(cfg) or [None])[0]
        stats0 = dict(ENGINE_STATS)
        changes: List[RowChange] = []   # résumé : prix modifiés et lignes douteuses
        self.timing = {}
        t_start = time.perf_counter()
        stop = "fin de la liste"
        self.stop_requested = False
        total = None                  # nombre de tes ventes (« 21/100 lots en vente »), si calibré
        # Liste déjà défilée au départ (reprise « souris sur la dernière ligne traitée ») : les
        # lignes sont numérotées depuis la 1re VISIBLE, le compteur ne dit donc rien de ce qui
        # reste (avant : « défilement bloqué » à tort en fin de liste, progression fausse).
        try:
            from_top = scrollbar_at_top(cfg) is not False    # None : liste sur une page / pas de barre
        except Exception:
            from_top = True
        if not from_top:
            start_note += ", liste déjà défilée au départ"
        listed: set = set()           # tes ventes vues (clé, lot, prix) : mémoire de tes prix à jour
        listed_ok = from_top and seen < 0
        if cfg.count_region and self.on_loop_progress and from_top:
            try:
                c = read_counter(cfg)
                total = c[0] if c else None
            except Exception:
                total = None

        def report(row=None, finished=False):
            if self.on_loop_progress:
                try:
                    self.on_loop_progress({"row": row, "done": done + skipped, "changed": changed,
                                           "bad": len(bad), "total": total, "finished": finished})
                except Exception:
                    pass
        try:
            while True:
                restart = True
                while restart:
                    restart = False
                    rows = self._page_rows(shift, base)   # relu à chaque fois : la liste a pu bouger
                    for y, g in rows:
                        if g <= seen:
                            continue
                        if self.paused or self.stop_requested:
                            stop = "pause" if self.paused else "arrêt demandé"
                            raise StopIteration
                        report(g + 1)
                        if done >= cfg.relist_max:
                            stop = f"limite {cfg.relist_max} lignes"
                            raise StopIteration
                        # Ligne identique (même objet, même prix) à une ligne déjà au bon prix :
                        # même résultat garanti -> pas de clic ni de lecture.
                        row_img = grab_screen((x0 - 90, y - step // 2 + 4, 430, step - 8))
                        if any(_same_row(row_img, r) for r in ok_rows):
                            same += 1
                            skipped += 1
                            seen = max(seen, g)
                            page_last_y = y
                            continue
                        t0 = time.perf_counter()
                        before = grab_screen(mine_box) if mine_box else None
                        click_at((x0, y))
                        last_click = (x0, y)
                        page_last_y = y
                        wait_change(mine_box, before, cfg.relist_delay)
                        self._tick("clic", t0)
                        res = self._relist(auto=True)
                        blocked = "NON confirmée" in res.message or res.hint == "Confirmation bloquée"
                        if res.level != "ok" and not blocked:
                            time.sleep(0.15)          # lecture douteuse : on relit une fois
                            res = self._relist(auto=True)
                        done += 1
                        listed_ok = listed_ok and self._note_listed(listed, res)
                        if self.progress:
                            try:
                                self.progress(res)
                            except Exception:
                                pass
                        if res.level != "ok":
                            if "NON confirmée" in res.message or res.hint == "Confirmation bloquée":
                                stop = f"ligne {g + 1} : {res.message}"  # sécurité : arrêt
                                raise StopIteration
                            # ligne douteuse : on n'y touche pas et on passe à la suivante
                            bad.append(f"ligne {g + 1} : {res.message}")
                            changes.append(RowChange(g + 1, res.lot, res.old_price, res.new_price, False,
                                                     res.hint or res.level, res.item_img))
                            # prix SUSPECT : décision voulue (on ne touche pas), pas un souci de
                            # lecture -> le parcours continue. Seules les lectures ratées comptent.
                            if res.hint != "Suspect":
                                fails += 1
                            seen = max(seen, g)
                            if fails >= 3:
                                stop = f"3 lignes douteuses de suite (calibration ?) : {res.message}"
                                raise StopIteration
                            continue
                        fails = 0
                        mod = (g, res.lot, res.old_price, res.new_price)
                        if "modifié" in res.message and mod == last_mod:
                            # Même ligne, même modification qu'à l'instant : elle n'a rien changé
                            # (prix déjà en place, mal lu ?). On passe, sinon boucle sans fin.
                            bad.append(f"ligne {g + 1} : modification répétée sans effet : {res.message}")
                            changes.append(RowChange(g + 1, res.lot, res.old_price, res.new_price, False,
                                                     "Modif. sans effet", res.item_img))
                            last_mod = None
                            listed_ok = False             # prix réel inconnu
                            seen = max(seen, g)
                            continue
                        if "modifié" in res.message:
                            last_mod = mod
                            # La ligne modifiée change de place : la liste se décale. On reprend
                            # À CETTE POSITION (relue), lignes repérées à nouveau à l'écran.
                            changed += 1
                            changes.append(RowChange(g + 1, res.lot, res.old_price, res.new_price, True,
                                                     img=res.item_img))
                            seen = g - 1
                            restart = True
                            break
                        same += 1
                        seen = max(seen, g)
                        if len(ok_rows) < 200:
                            ok_rows.append(row_img)
                # Défilement d'une demi-page (RELIST_SCROLL_PAGE) et relecture de la dernière
                # ligne traitée : une erreur de mesure d'une ligne ne fait jamais sauter
                # d'objet ; les lignes déjà vues ne sont pas recliquées (numéro global).
                target = max(step, int(len(rows) * cfg.relist_scroll_page) * step)
                t0 = time.perf_counter()
                moved, err = self._scroll_page(box, target)
                self._tick("défilement", t0)
                if err:
                    stop = err
                    break
                if moved <= 0:
                    # La liste ne bouge plus : en bas… sauf si le compteur « X/Y lots en vente »
                    # dit qu'il reste des ventes à voir (molette ignorée par le jeu).
                    # La barre de défilement (si visible) tranche : poignée en bas = vraie fin.
                    at_bottom = scrollbar_at_bottom(cfg)
                    left = 0 if at_bottom or not from_top else self._rows_left(seen, total)
                    if at_bottom is False and not left:
                        left = -1                 # barre pas en bas, compteur muet
                    if left:
                        time.sleep(0.5)
                        t0 = time.perf_counter()
                        moved, err = self._scroll_page(box, target)
                        self._tick("défilement", t0)
                        if err:
                            stop = err
                            break
                    if moved <= 0 and left and scrollbar_at_bottom(cfg):
                        left = 0                  # poignée arrivée en bas entre-temps : vraie fin
                    if moved <= 0:
                        if left:
                            more = (f"encore ~{left} vente(s) après la dernière ligne vue" if left > 0
                                    else "la barre de défilement n'est pas en bas")
                            stop = (f"défilement bloqué : la liste ne descend plus, {more}. Relance "
                                    "Ctrl+F3 avec la souris sur la dernière ligne traitée")
                            break
                        # Vraie fin : la liste ne bouge plus, les positions à l'écran sont sûres.
                        # Lignes SOUS la dernière traitée = pas encore traitées, quel que soit
                        # leur numéro (vidéo du joueur : la ligne du bas manquait aux lignes
                        # repérées sur la dernière page, « fin de la liste » sans la traiter).
                        if swept:
                            break
                        swept = True
                        ref = page_last_y if page_last_y is not None else -10 ** 9
                        below = [g for y, g in self._page_rows(shift, base) if y > ref + step // 2]
                        if not below:
                            break
                        log_line(f"[MAJ TOUT] Fin de la liste : {len(below)} ligne(s) sous la dernière "
                                 "traitée, revue(s).")
                        seen = min(below) - 1
                        continue
                shift += moved
                page_last_y = None
                seen -= 1
                pages += 1
        except StopIteration:
            pass
        finally:
            report(finished=True)
            try:
                import pyautogui
                # Arrêt en cours de route : souris laissée sur la dernière ligne traitée,
                # Ctrl+F3 reprendra là. Fin de liste : souris remise à sa place.
                if stop == "fin de la liste" or last_click is None:
                    pyautogui.moveTo(*back)
                else:
                    pyautogui.moveTo(*last_click)
            except Exception:
                pass
        if stop == "fin de la liste" and listed_ok and listed:
            try:
                n = self.my_prices.keep_only(listed)
                if n:
                    log_line(f"[MAJ TOUT] {n} prix de ventes terminées oubliés (plus dans la liste).")
            except Exception:
                pass
        level = "ok" if stop == "fin de la liste" and not bad else "warn"
        fast_n = ENGINE_STATS.get("chiffres", 0) - stats0.get("chiffres", 0)
        tess_n = ENGINE_STATS.get("tesseract", 0) - stats0.get("tesseract", 0)
        detail = f" | lecture rapide {fast_n}/{fast_n + tess_n}" if fast_n + tess_n else ""
        detail += " | " + timing_text(time.perf_counter() - t_start, done, self.timing)
        if bad:
            detail += f" | {len(bad)} ligne(s) douteuse(s) NON modifiée(s), à faire avec F3 : " + " / ".join(bad[:5])
        summary = {"seen": done + skipped, "changed": changed, "same": same, "bad": len(bad),
                   "stop": stop, "complete": stop == "fin de la liste",
                   "seconds": round(time.perf_counter() - t_start, 1)}
        return Result(None, level, f"[MAJ TOUT] {done + skipped} lignes vues ({pages + 1} pages, "
                      f"{skipped} identiques sautées{start_note}) : "
                      f"{changed} modifiées, {same} déjà au bon prix | arrêt : {stop}{detail}",
                      hint=f"{changed} modifiées", changes=changes, summary=summary)

    # ---- actions ----
    def sell(self, optimize: bool = False) -> Result:
        if not self._lock.acquire(blocking=False):
            return Result(None, "warn", "Lecture déjà en cours, ignoré.")
        try:
            self._reanchor()
            return self._sell(optimize)
        except Exception as e:  # ne jamais tuer le thread des hotkeys
            return Result(None, "error", f"Erreur: {e}", hint="Erreur")
        finally:
            self._lock.release()

    def sell_all(self) -> Result:
        """Met en vente la quantité affichée, puis recommence au MÊME prix tant que :
        - la quantité affichée ne change pas (sinon stock épuisé / passé sous le lot) ;
        - le prix en tête du tableau pour ce lot est le tien (sinon autre objet ou concurrent) ;
        - pas de pause (Ctrl+Alt+P) et moins de SELL_ALL_MAX ventes."""
        if not self._lock.acquire(blocking=False):
            return Result(None, "warn", "Lecture déjà en cours, ignoré.")
        try:
            self._reanchor()
            return self._sell_all()
        except Exception as e:
            return Result(None, "error", f"Erreur: {e}", hint="Erreur")
        finally:
            self._lock.release()

    def _sell_all(self) -> Result:
        cfg = self.cfg
        check = cfg.verify_count and bool(cfg.count_region)
        base = read_counter(cfg) if check else None
        if base and base[0] >= base[1]:
            return Result(None, "error", f"[TOUT] Plus de place : {base[0]}/{base[1]} lots en vente.",
                          hint="HDV plein")
        self.stop_requested = False
        watch = [tuple(r) for r in (cfg.count_region, cfg.qty_region, cfg.table_region) if r]
        snap = lambda: [grab_screen(r) for r in watch]
        before = snap()
        first = self._sell(False, force_validate=True)
        if first.level != "ok" or "mis en vente" not in first.message:
            return first  # lecture suspecte / erreur : on ne boucle pas
        lot, price = first.lot, first.new_price
        dumper = first.floored_top  # prix au plancher : en tête, ce sera toujours le brader
        segments = [[lot, price, 1]]          # [lot, prix, nombre] — ex. 4×10 puis 2×1
        n, stop = 1, "limite atteinte"
        sr = first.screen
        unverified = False
        while True:
            # Plus de pause fixe : on attend que l'écran bouge (compteur, quantité, tableau),
            # au plus SELL_ALL_DELAY, puis un court délai pour que l'affichage se termine.
            wait_any_change(watch, before, cfg.sell_all_delay)
            if base:
                err, full = self._check_counter(base, n)
                if err:
                    stop = err
                    break
                if full:
                    stop = f"plus de place ({base[0] + n}/{base[1]} lots)"
                    break
            elif check:
                unverified = True
            if n >= cfg.sell_all_max:
                break
            if self.paused or self.stop_requested:
                stop = "pause" if self.paused else "arrêt demandé"
                break
            sr = read_screen(cfg, self.debug_dir)
            if sr.selected is None:
                stop = "stock épuisé"
                break
            top = sr.prices.get(lot)
            if top is None or top.value not in (price, dumper):
                # ta dernière vente n'est plus en tête de son lot : autre objet ou concurrent
                stop = f"prix en tête du lot {lot} : {top.value if top else '?'} ≠ {price}"
                break
            if sr.selected == lot:
                before = snap()
                if not press_validate(cfg, expected=price):  # même lot, même prix -> Entrée
                    stop = f"le champ « Prix du lot » n'affiche plus {price} : pas validé"
                    break
                self.my_prices.add(item_key(grab_name(cfg)), lot, price)
                log_history("sell", lot, sr.selected, top, price, "sell_all", cfg)
                segments[-1][2] += 1
                n += 1
                continue
            if sr.selected > lot:
                stop = f"quantité passée à {sr.selected}"  # jamais vers un lot plus grand
                break
            # Quantité plus petite (ex. 42 objets : 4×10 vendus, il en reste 2 -> lot 1).
            # Même objet confirmé (notre prix est en tête de l'ancien lot) : nouveau prix, mêmes garde-fous.
            before = snap()
            res = self._sell(False, force_validate=True, screen=sr)
            if res.level != "ok" or "mis en vente" not in res.message:
                stop = f"lot {sr.selected} non vendu ({res.message})"
                break
            lot, price, dumper = res.lot, res.new_price, res.floored_top
            segments.append([lot, price, 1])
            n += 1
        detail = " + ".join(f"{c}×{l} à {p}" for l, p, c in segments)
        if base:
            detail += f" | compteur {base[0]}→{base[0] + n} ✓" if "non confirmée" not in stop else ""
        elif unverified:
            detail += " | compteur illisible, ventes non vérifiées"
        level = "warn" if "non confirmée" in stop else "ok"
        return Result(lot, level, f"[TOUT] {detail} | arrêt : {stop}", sr, price,
                      hint=f"{n} lot{'s' if n > 1 else ''} mis en vente")

    def _check_counter(self, base: Tuple[int, int], n: int) -> Tuple[Optional[str], bool]:
        """Après n ventes, le compteur doit valoir EXACTEMENT base + n (une valeur plus haute
        = chiffre mal lu ; plus basse = vente ratée ou un de tes lots vendu entre-temps).
        Une 2e lecture si le jeu est lent. Retourne (erreur, plein)."""
        expected = base[0] + n
        for attempt in range(2):
            c = read_counter(self.cfg)
            if c and c[0] == expected and c[1] == base[1]:
                return None, c[0] >= c[1]
            if attempt == 0:
                time.sleep(max(0.3, self.cfg.sell_all_delay))
        got = f"{c[0]}/{c[1]}" if c else "illisible"
        return f"vente non confirmée (compteur {got}, attendu {expected}/{base[1]})", False

    def peek(self) -> Optional[ScreenRead]:
        """Lecture discrète pour le HUD (objet sélectionné) : rien n'est cliqué ni tapé, aucune
        recalibration. None si une action est en cours ou si l'HDV n'est pas là où il a été calibré."""
        cfg = self.cfg
        if not cfg.table_region or not self._lock.acquire(blocking=False):
            return None
        try:
            if cfg.anchor_region:
                tpl = load_anchor(anchor_path(cfg))
                if tpl is not None and anchor_score(grab_screen(tuple(cfg.anchor_region)), tpl) < ANCHOR_OK:
                    return None                    # HDV fermé, caché ou déplacé : on n'invente rien
            return read_screen(cfg)
        finally:
            self._lock.release()

    def read_only(self) -> ScreenRead:
        with self._lock:
            self._reanchor()
            sr = read_screen(self.cfg, self.debug_dir)
            sr.listed = read_counter(self.cfg)
            sr.mine = read_mine(self.cfg).value if mine_regions(self.cfg) else None
            return sr

    def _sell(self, optimize: bool, force_validate: bool = False,
              screen: Optional[ScreenRead] = None) -> Result:
        cfg = self.cfg
        tag = "OPT" if optimize else "VENTE"
        if not cfg.table_region:
            return Result(None, "error", f"Tableau non calibré ({cfg.hotkeys['calibrate_table']} ×2).",
                          hint="Calibre le tableau")
        sr = screen if screen is not None else read_screen(cfg, self.debug_dir)
        key = item_key(grab_name(cfg))
        prices = sr.values
        sel = sr.selected

        # ---- lot visé
        if optimize:
            # Le jeu affiche par défaut le plus grand lot possible avec ton stock
            # (moins de 10 objets -> 1, 10 à 99 -> 10, ...) : les lots plus grands sont impossibles.
            possible = {l: p for l, p in prices.items() if sel is None or l <= sel}
            lot = pick_best_lot(possible, cfg.tie_tolerance)
            if lot is None and sel is not None:
                lot = sel  # personne ne vend les lots possibles : prix estimé plus bas
            if lot is None:
                return Result(None, "error", f"[{tag}] Aucun prix lu dans le tableau.", sr,
                              hint="Aucun prix lu")
            if sel is not None and sel != lot:
                p = prices.get(lot)
                new_p = compute_price(p, cfg.undercut_mode, cfg.undercut_value, cfg.rounding, cfg.min_price)
                return Result(lot, "warn",
                              f"[{tag}] Meilleur lot : {lot} (quantité affichée : {sel}). "
                              f"Change la quantité puis ré-appuie.", sr, new_p,
                              hint=f"Choisis quantité {lot}")
        else:
            if not cfg.qty_region:
                return Result(None, "error",
                              f"Zone Quantité non calibrée ({cfg.hotkeys['calibrate_qty']} ×2).", sr,
                              hint="Calibre la quantité")
            if sel is None:
                return Result(None, "error",
                              f"[{tag}] Quantité illisible (lu : {sr.selected_raw!r}).", sr,
                              hint="Quantité illisible")
            lot = sel

        # ---- prix de référence
        problems = []
        r = sr.prices.get(lot)
        if r is None or r.value is None:
            est = derive_price(lot, prices)
            if est is None:
                log_history("read", lot, sel, None, None, "no_price", cfg)
                return Result(lot, "error", f"[{tag}] Aucun prix en vente.", sr, hint="Aucun prix")
            conf = min((x.confidence for x in sr.prices.values()), default=-1)
            r = Reading(est, conf, "estimé")
            problems.append(f"personne ne vend le lot {lot}, prix estimé depuis les autres lots")
        own = r.raw != "estimé" and self.my_prices.has(key, lot, r.value, cfg.own_price_ttl)
        if own:  # le moins cher, c'est toi : on garde ton prix, pas d'undercut
            new_p = r.value
        else:
            new_p = compute_price(r.value, cfg.undercut_mode, cfg.undercut_value, cfg.rounding,
                                  cfg.min_price)

        # ---- garde-fous
        if r.confidence < cfg.min_confidence:
            problems.append(f"confiance OCR {r.confidence:.0f} < {cfg.min_confidence:.0f}")
        if r.raw != "estimé":
            incoh = check_coherence(lot, prices, cfg.max_ratio)
            if incoh:
                problems.append(incoh)
        if sel is None:
            problems.append("quantité non vérifiée")
        fp = floor_price(lot, sr.avg, cfg.floor_ratio) if cfg.floor_mode != "stop" else None
        floored = fp is not None and new_p < fp
        if floored:  # concurrent qui brade : on vend au plancher, pas sous son prix
            new_p = fp
            problems = [p for p in problems if not p.startswith("prix unitaire")]
        unit = new_p / lot
        if (cfg.floor_mode == "stop" and cfg.min_avg_ratio > 0 and sr.avg
                and unit < sr.avg * cfg.min_avg_ratio):
            problems.append(f"{unit:.0f}/u < {cfg.min_avg_ratio:.0%} du prix moyen ({sr.avg}/u)")

        prefix = (f"[{tag}] Lot {lot} | Lu: {r.value} -> {new_p}{' (ton prix)' if own else ''}"
                  f"{f' (plancher {cfg.floor_ratio:.0%} du prix moyen {sr.avg})' if floored else ''}")
        now = time.time()
        forced = (self._pending is not None and self._pending[:2] == (lot, new_p)
                  and now - self._pending[2] <= cfg.confirm_window)

        if problems and not forced:
            self._pending = (lot, new_p, now)
            input_price(new_p, cfg, paste=False)
            log_history("read", lot, sel, r, new_p, "suspect", cfg)
            return Result(lot, "warn",
                          f"{prefix} | SUSPECT ({'; '.join(problems)}). Copié seulement. "
                          f"Ré-appuie dans {cfg.confirm_window:.0f}s pour forcer.",
                          sr, new_p, hint="Suspect — ré-appuie pour forcer")

        self._pending = None
        paste = cfg.auto_paste or forced or force_validate
        validate = (cfg.auto_validate or force_validate) and not forced and not problems
        done = input_price(new_p, cfg, paste=paste, validate=validate)
        refused = "PAS validé" in done   # champ relu différent : rien n'a été mis en vente
        if paste and not refused:
            # mise en vente faite par l'outil : sûre ; simple collage (Entrée à toi) : mémoire courte
            self.my_prices.add(key, lot, new_p, sure="mis en vente" in done)
        log_history("sell" if paste else "copy", lot, sel, r, new_p,
                    "forced" if forced else done, cfg)
        return Result(lot, "warn" if refused else "ok", f"{prefix} | {done}{' (forcé)' if forced else ''}",
                      sr, new_p, hint="Prix collé incorrect" if refused else done.capitalize(),
                      floored_top=r.value if floored else None)

