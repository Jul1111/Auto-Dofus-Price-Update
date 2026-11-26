#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Dofus Price Helper — version ligne de commande
----------------------------------------------
Même moteur que l'interface graphique (dofus_core.py), sans fenêtre.

Raccourcis par défaut (clé HOTKEYS de la config) :
  F1                  vendre (objet de l'inventaire) OU mettre à jour (une de tes ventes) :
                      le mode est détecté seul (SMART_F1 ; --f1-simple = toujours vendre)
  F2                  tout vendre au même prix (s'arrête seul : stock épuisé, autre objet, concurrent)
  F4                  optimiser (meilleur prix unitaire)
  (même touche 2x)    forcer une lecture suspecte
  Ctrl+Alt+F1 (x2)    calibrer le tableau « Actuellement en vente » (coin haut-gauche, puis bas-droit)
  Ctrl+Alt+F2 (x2)    calibrer le menu « Quantité »
  Ctrl+Alt+F3         calibrer le champ « Prix du lot »
  Ctrl+Alt+F4         calibrer le bouton « Mettre en vente »
  F3 / Ctrl+F3        mes ventes : mettre à jour la ligne sélectionnée / toute la liste
  Ctrl+Alt+F7 (x2)    mes ventes : texte du champ « Prix du lot » ; Ctrl+Alt+F8 : bouton « Modifier »
  Ctrl+Alt+F9 (x2)    mes ventes : 1re puis 2e ligne de la liste
  Ctrl+Alt+F10 (x2)   repère : titre « Hôtel de vente » (les zones suivent l'HDV déplacé)
  Ctrl+Alt+F11 (x2)   (optionnel) nom de l'objet (historique des prix)
  Ctrl+Alt+F5 (x2)    (optionnel) calibrer la valeur du « Prix moyen »
  Ctrl+Alt+F6 (x2)    (optionnel) calibrer le compteur « 21/100 lots en vente »
  Ctrl+Shift+P        afficher ce qui est lu (debug)
  Ctrl+Alt+P          pause / reprise
  Ctrl+Alt+Q          quitter   (Échap n'est plus utilisé : il ferme les fenêtres du jeu)

Options de vente rapide : AUTO_PASTE, CLICK_FIELD, AUTO_VALIDATE dans la config.

Options de la ligne de commande (enregistrées dans la config, comme dans l'interface) :
  --plancher PCT         prix plancher = PCT % du « Prix moyen » (0 = désactivé)
  --sous-plancher MODE   concurrent sous le plancher : plancher | garder | arret
  --f1-simple            F1 vend toujours (pas de mise à jour automatique)
  --f1-intelligent       F1 vend OU met à jour selon le panneau ouvert (défaut)
  --debug                enregistre les images envoyées à l'OCR dans captures/
"""
from __future__ import annotations

import argparse
import queue
import sys
import threading
import time
from typing import List, Optional

import dofus_core as core

FLOOR_MODES = {"plancher": "floor", "garder": "keep", "arret": "stop"}
FLOOR_LABELS = {"floor": "au plancher", "keep": "garder mon prix", "stop": "arrêt (suspect)"}

STALE_JOB_S = 1.5   # s : touche appuyée pendant une autre action (F2, Ctrl+F3) -> ignorée


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="Dofus Price Helper, version ligne de commande.")
    ap.add_argument("--plancher", type=float, metavar="PCT",
                    help="prix plancher en %% du « Prix moyen » (0 = désactivé)")
    ap.add_argument("--sous-plancher", choices=list(FLOOR_MODES), dest="sous_plancher",
                    help="concurrent sous le plancher : plancher, garder (mon prix) ou arret")
    f1 = ap.add_mutually_exclusive_group()
    f1.add_argument("--f1-simple", dest="smart_f1", action="store_false", default=None,
                    help="F1 vend toujours")
    f1.add_argument("--f1-intelligent", dest="smart_f1", action="store_true",
                    help="F1 vend OU met à jour une de tes ventes (défaut)")
    ap.add_argument("--debug", action="store_true", help="images OCR dans captures/")
    return ap.parse_args(argv)


def apply_args(cfg: "core.Config", args: argparse.Namespace) -> bool:
    """Reporte les options dans la config. True si quelque chose a changé."""
    changed = False
    if args.plancher is not None:
        if args.plancher < 0:
            raise ValueError("--plancher doit être positif (0 = désactivé)")
        cfg.floor_ratio = round(args.plancher / 100, 4)
        changed = True
    if args.sous_plancher is not None:
        cfg.floor_mode = FLOOR_MODES[args.sous_plancher]
        changed = True
    if args.smart_f1 is not None:
        cfg.smart_f1 = args.smart_f1
        changed = True
    return changed


def describe(cfg: "core.Config") -> str:
    """Résumé des réglages de prix et du mode F1, affiché au démarrage."""
    if cfg.floor_mode == "stop":
        floor = (f"arrêt si < {cfg.min_avg_ratio:.0%} du prix moyen" if cfg.min_avg_ratio > 0
                 else "désactivé")
    elif cfg.floor_ratio > 0:
        floor = f"{cfg.floor_ratio:.0%} du prix moyen, concurrent dessous : {FLOOR_LABELS[cfg.floor_mode]}"
    else:
        floor = "désactivé"
    if cfg.floor_mode != "stop" and cfg.floor_ratio > 0 and not cfg.avg_region:
        floor += " (zone « Prix moyen » à calibrer : Ctrl+Alt+F5)"
    f1 = "vendre OU mettre à jour (auto)" if cfg.smart_f1 else "vendre"
    if cfg.smart_f1 and not cfg.modify_button:
        f1 += " (bouton « Modifier » à calibrer : Ctrl+Alt+F8)"
    return f"F1 : {f1}\nPlancher : {floor}"


def main(argv: Optional[List[str]] = None) -> int:
    try:
        args = parse_args(argv)
    except SystemExit as e:
        return int(e.code or 0)
    import keyboard  # Windows : chargé ici pour que --help et les tests marchent sans

    debug_dir = core.BASE_DIR / "captures" if args.debug else None
    try:
        core.setup_file_log()   # tout ce qui s'affiche est aussi gardé dans journaux/journal.log
    except OSError:
        pass
    cfg = core.Config.load()
    try:
        if apply_args(cfg, args):
            cfg.save()
            print("[Param] Réglages enregistrés dans la config.")
    except ValueError as e:
        print("[Erreur]", e)
        return 2
    engine = core.PriceEngine(cfg, debug_dir=debug_dir)
    engine.progress = lambda r: print(f"   [{r.level.upper():5}] {r.message}")   # Ctrl+F3 : chaque ligne

    err = core.setup_tesseract(cfg)
    if err:
        print("[Erreur]", err)
        return 1

    def report(res: core.Result):
        print(f"[{res.level.upper():5}] {res.message}")
        core.beep(res.level, cfg)

    # Les actions tournent dans un thread à part : exécutées dans le thread du module
    # keyboard, elles bloquaient les autres raccourcis (Ctrl+Alt+P n'arrêtait pas F2 / Ctrl+F3).
    jobs: "queue.Queue[tuple]" = queue.Queue()

    def worker():
        while True:
            action, pressed = jobs.get()
            if engine.paused or time.time() - pressed > STALE_JOB_S:
                print("[Hotkeys] Raccourci ignoré (pause, ou appuyé pendant une autre action).")
                continue
            try:
                report(action())
            except Exception as e:
                print(f"[Erreur] {e}")

    threading.Thread(target=worker, daemon=True).start()

    def unstick():
        # touches que `keyboard` croit enfoncées à tort : sans ça, plus aucun raccourci ne répond
        while True:
            time.sleep(1.0)
            try:
                freed = core.release_stuck_keys()
            except Exception:
                freed = []
            if freed:
                print(f"[Hotkeys] Touche restée « enfoncée » libérée : {', '.join(freed)}")

    threading.Thread(target=unstick, daemon=True).start()

    def game_action(optimize: bool, all_: bool = False):
        def cb():
            if engine.paused:
                return
            if not core.game_has_focus(cfg):
                info = core.foreground_info() or ("?", "?")
                print(f"[Focus] Ignoré : fenêtre active « {info[0]} » ({info[1]})")
                return
            jobs.put((engine.sell_all if all_ else (lambda: engine.sell(optimize=True)) if optimize
                      else engine.smart, time.time()))
        return cb

    def calib_rect(name):
        state, val = engine.calibrate_rect(name)
        if state == "first":
            print(f"[Calib] {name} : coin 1 = {val}. Souris sur le coin opposé, puis ré-appuie.")
        else:
            print(f"[Calib] {name} = {val}")
            hint = core.zone_hint(name, val) or core.cut_text_hint(name, val)
            if hint:
                print(f"[Calib] Attention : {hint}")

    def calib_point(name):
        print(f"[Calib] {name} = {engine.calibrate_point(name)}")

    def print_all():
        sr = engine.read_only()
        print(f"Quantité affichée : {sr.selected} (lu {sr.selected_raw!r})"
              f" | prix moyen : {sr.avg if sr.avg else 'non lu'}")
        for lot, r in sr.prices.items():
            new_p = core.compute_price(r.value, cfg.undercut_mode, cfg.undercut_value,
                                       cfg.rounding, cfg.min_price)
            fp = (core.floor_price(lot, sr.avg, cfg.floor_ratio)
                  if cfg.floor_mode != "stop" else None)
            extra = ""
            if fp and new_p is not None and new_p < fp:
                extra = f"  -> plancher {fp} ({cfg.floor_ratio:.0%} du prix moyen)"
            print(f"  Lot {lot:>4}: {r.value} (conf {r.confidence:.0f}) -> {new_p}{extra}")

    def toggle_pause():
        engine.paused = not engine.paused
        print("[Hotkeys]", "En pause" if engine.paused else "Actifs")

    hk = cfg.hotkeys
    keyboard.add_hotkey(hk["sell"], game_action(False))
    keyboard.add_hotkey(hk["optimize"], game_action(True))
    keyboard.add_hotkey(hk["sell_all"], game_action(False, all_=True))
    keyboard.add_hotkey(hk["calibrate_table"], lambda: calib_rect("table"))
    keyboard.add_hotkey(hk["calibrate_qty"], lambda: calib_rect("qty"))
    keyboard.add_hotkey(hk["calibrate_avg"], lambda: calib_rect("avg"))
    keyboard.add_hotkey(hk["calibrate_count"], lambda: calib_rect("count"))
    keyboard.add_hotkey(hk["calibrate_field"], lambda: calib_point("price_field"))
    keyboard.add_hotkey(hk["calibrate_button"], lambda: calib_point("sell_button"))
    def relist_action(all_: bool):
        def cb():
            if engine.paused or not core.game_has_focus(cfg):
                return
            jobs.put((engine.relist_all if all_ else engine.relist, time.time()))
        return cb

    def calib_rows():
        print(f"[Calib] lignes : {engine.calibrate_rows()}")

    keyboard.add_hotkey(hk["relist"], relist_action(False))
    keyboard.add_hotkey(hk["relist_all"], relist_action(True))
    keyboard.add_hotkey(hk["calibrate_mine"], lambda: calib_rect("mine"))
    keyboard.add_hotkey(hk["calibrate_anchor"], lambda: calib_rect("anchor"))
    keyboard.add_hotkey(hk["calibrate_name"], lambda: calib_rect("name"))
    keyboard.add_hotkey(hk["calibrate_modify"], lambda: calib_point("modify_button"))
    keyboard.add_hotkey(hk["calibrate_rows"], calib_rows)
    keyboard.add_hotkey(hk["pause"], toggle_pause)
    keyboard.add_hotkey("ctrl+shift+p", print_all)

    print("Dofus Price Helper (CLI) prêt.")
    print(f"Tableau: {'OK' if cfg.table_region else 'à calibrer'} | "
          f"Quantité: {'OK' if cfg.qty_region else 'à calibrer'} | coller auto : {cfg.auto_paste}")
    print(describe(cfg))
    print(f"Quitter : {hk['quit']}")
    try:
        keyboard.wait(hk["quit"])
    except KeyboardInterrupt:
        pass
    print("Bye!")
    return 0


if __name__ == "__main__":
    sys.exit(main())
