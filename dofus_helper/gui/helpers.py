"""Fonctions pures de l'interface (aperçu des prix, journal, historique des Ctrl+F3, HUD, visite guidée) : testées sans fenêtre."""
from __future__ import annotations

import os
import sys
import time
from typing import Optional

from dofus_helper import core
from dofus_helper.gui import style

from .common import fmt, price_delta


# ---------------------------------------------------------------- aperçu des prix (onglet Prix)
PREVIEW_TOP = 1000     # prix d'exemple du moins cher (lot de 1)
PREVIEW_AVG = 1000     # prix moyen d'exemple (par objet)
PREVIEW_LOW = 500      # un vendeur qui brade


def price_preview(mode: str, value, rounding: str, min_price: int, floor_ratio: float,
                  floor_mode: str, min_avg_ratio: float = 0.5) -> list:
    """Exemple chiffré des réglages de prix, comme le moteur les applique (lot de 1).
    mode / rounding / floor_mode : clés de config ("fixed", "down_10", "keep"…)."""
    new = core.compute_price(PREVIEW_TOP, mode, value, rounding, min_price)
    fp = core.floor_price(1, PREVIEW_AVG, floor_ratio) if floor_mode != "stop" else None
    line = f"Moins cher {fmt(PREVIEW_TOP)} → ton prix {fmt(new)}"
    if fp:
        line += f"   (plancher {fmt(fp)})"
    out = [line]
    low = core.compute_price(PREVIEW_LOW, mode, value, rounding, min_price)
    head = f"Un vendeur brade à {fmt(PREVIEW_LOW)} (prix moyen {fmt(PREVIEW_AVG)}) → "
    if fp and low < fp:
        if floor_mode == "keep":
            out.append(head + f"vente au plancher {fmt(fp)} ; une de tes ventes garde son prix")
        else:
            out.append(head + f"ton prix {fmt(fp)} (plancher)")
    elif floor_mode == "stop" and min_avg_ratio > 0 and low < PREVIEW_AVG * min_avg_ratio:
        out.append(head + f"{fmt(low)} jugé suspect : arrêt (même touche ×2 pour forcer)")
    else:
        out.append(head + f"ton prix {fmt(low)}")
    return out


# ---------------------------------------------------------------- journal : filtres
SALE_PREFIXES = ("[VENTE]", "[OPT]", "[TOUT]", "[MAJ]", "[MAJ TOUT]")
LOG_FILTERS = {"Tout": "all", "Ventes": "sale", "Problèmes": "problem"}


def log_category(msg: str, tag: str) -> str:
    """« problem » (avertissement / erreur), « sale » (vente, mise à jour) ou « info »."""
    if tag in ("WARN", "ERROR"):
        return "problem"
    if msg.lstrip().startswith(SALE_PREFIXES):
        return "sale"
    return "info"


def log_visible(category: str, flt: str, in_block: bool = False) -> bool:
    """La ligne passe-t-elle le filtre ? Un problème est aussi une ligne de vente s'il en vient."""
    if flt == "all":
        return True
    if flt == "problem":
        return category == "problem"
    return category == "sale" or in_block


LOG_ICONS = {"sale": "◆", "update": "✎", "warn": "▲", "error": "✖", "cal": "◎", "ok": "✓", "info": "·"}


def log_kind(msg: str, tag: str) -> str:
    """Type d'une ligne du journal, pour son icône : vente, mise à jour, alerte, erreur…"""
    m = msg.lstrip()
    if tag == "ERROR":
        return "error"
    if tag == "WARN":
        return "warn"
    if m.startswith(("[MAJ TOUT]", "[MAJ]")):
        return "update"
    if m.startswith(("[VENTE]", "[TOUT]", "[OPT]")):
        return "sale"
    if tag == "CAL":
        return "cal"
    return "ok" if tag in ("OK", "OPT") else "info"


# ---------------------------------------------------------------- historique des Ctrl+F3
RUNS_PATH = core.BASE_DIR / "dofus_relist_runs.json"
MAX_RUNS = 10


def runs_to_json(runs: list) -> list:
    """Parcours -> JSON (sans les images des noms, gardées en mémoire seulement)."""
    return [{"time": r["time"], "summary": r.get("summary") or {}, "changes": [
        {"row": c.row, "lot": c.lot, "old": c.old, "new": c.new, "modified": c.modified, "note": c.note}
        for c in r["changes"]]} for r in runs]


def runs_from_json(data) -> list:
    runs = []
    for r in data if isinstance(data, list) else []:
        try:
            summary = r.get("summary")
            runs.append({"time": float(r["time"]), "summary": summary if isinstance(summary, dict) else {},
                         "changes": [core.RowChange(
                row=int(c["row"]), lot=c.get("lot"), old=c.get("old"), new=c.get("new"),
                modified=bool(c.get("modified")), note=str(c.get("note", ""))) for c in r["changes"]]})
        except (KeyError, TypeError, ValueError):
            continue
    return runs[-MAX_RUNS:]


def load_runs(path=None) -> list:
    import json
    path = path or RUNS_PATH
    try:
        return runs_from_json(json.loads(path.read_text(encoding="utf-8")))
    except (OSError, ValueError):
        return []


def save_runs(runs: list, path=None) -> None:
    import json
    path = path or RUNS_PATH
    path.write_text(json.dumps(runs_to_json(runs[-MAX_RUNS:]), ensure_ascii=False), encoding="utf-8")


def run_title(run: dict) -> str:
    mod = sum(1 for c in run["changes"] if c.modified)
    bad = len(run["changes"]) - mod
    txt = time.strftime("%d/%m %H:%M", time.localtime(run["time"]))
    txt += f"  —  {mod} prix modifié{'s' if mod > 1 else ''}"
    if bad:
        txt += f"  ·  {bad} à revoir"
    return txt


# ---------------------------------------------------------------- fenêtre / apparence
UI_SCALES = {"90 %": 0.9, "100 %": 1.0, "110 %": 1.1, "125 %": 1.25, "150 %": 1.5}


def scale_label(scale: float) -> str:
    return min(UI_SCALES, key=lambda k: abs(UI_SCALES[k] - scale))


def geometry_on_screen(geom: str, bounds) -> bool:
    """« LxH+X+Y » enregistré : la fenêtre serait-elle (au moins en partie) visible ?
    (écran débranché depuis -> fenêtre perdue hors de l'écran)."""
    import re
    m = re.fullmatch(r"(\d+)x(\d+)\+(-?\d+)\+(-?\d+)", geom or "")
    if not m:
        return False
    w, h, x, y = map(int, m.groups())
    sx, sy, sw, sh = bounds
    return w >= 200 and h >= 120 and sx - w + 80 <= x <= sx + sw - 80 and sy <= y <= sy + sh - 40


# ---------------------------------------------------------------- panneau « Activité »
ACTION_KINDS = (("[MAJ TOUT]", "Toute la liste"), ("[TOUT]", "Tout vendre"), ("[VENTE]", "Vente"),
                ("[OPT]", "Meilleur lot"), ("[MAJ]", "Mise à jour"))


def action_entry(res, when: float = None) -> dict:
    """Une ligne du panneau Activité à partir du résultat d'une action."""
    msg = res.message.lstrip()
    kind = next((label for prefix, label in ACTION_KINDS if msg.startswith(prefix)), "Action")
    if msg.startswith("[MAJ TOUT]"):
        text = kind
    elif res.old_price and res.new_price is not None and res.old_price != res.new_price:
        text = f"{kind} · lot {res.lot or '?'} : {fmt(res.old_price)} → {fmt(res.new_price)}"
    elif res.new_price is not None:
        text = f"{kind} · lot {res.lot or '?'} → {fmt(res.new_price)}"
    else:
        text = kind + (f" · lot {res.lot}" if res.lot else "")
    delta = None if msg.startswith("[MAJ TOUT]") else price_delta(res.old_price, res.new_price)
    icon = "tag" if kind.startswith("Vente") or msg.startswith(("[VENTE]", "[TOUT]")) else \
        "edit" if msg.startswith(("[MAJ]", "[OPT]")) else "dot"
    return {"time": time.strftime("%H:%M", time.localtime(when or time.time())), "text": text,
            "hint": res.hint or {"ok": "ok", "warn": "à vérifier", "error": "erreur"}.get(res.level, ""),
            "level": res.level, "delta": delta, "icon": icon}


# ---------------------------------------------------------------- progression des boucles (F2, Ctrl+F3)
def progress_text(d: dict) -> tuple:
    """(texte, fraction 0..1 ou None si le total est inconnu) pour la barre de progression."""
    row, total = d.get("row"), d.get("total")
    parts = [f"Ligne {row}" + (f" / {total}" if total else "") if row else "Démarrage…"]
    if d.get("changed"):
        parts.append(f"{d['changed']} modifiée{'s' if d['changed'] > 1 else ''}")
    if d.get("bad"):
        parts.append(f"{d['bad']} à revoir")
    frac = min(1.0, max(0.0, row / total)) if row and total else None
    return " · ".join(parts), frac


LONG_LOOP_S = 20   # s : au-delà, une notification Windows signale la fin (outil en arrière-plan)


def windows_notify(title: str, body: str) -> bool:
    """Notification Windows (centre de notifications), sans dépendance : passe par PowerShell.
    Le texte passe par des variables d'environnement (jamais interprété comme du code)."""
    import os
    import subprocess
    import sys
    if sys.platform != "win32":
        return False
    script = (
        "$ErrorActionPreference='Stop';"
        "[Windows.UI.Notifications.ToastNotificationManager,Windows.UI.Notifications,ContentType=WindowsRuntime]>$null;"
        "[Windows.Data.Xml.Dom.XmlDocument,Windows.Data.Xml.Dom.XmlDocument,ContentType=WindowsRuntime]>$null;"
        "$t=[Security.SecurityElement]::Escape($env:DPH_TITLE);$b=[Security.SecurityElement]::Escape($env:DPH_BODY);"
        "$x=New-Object Windows.Data.Xml.Dom.XmlDocument;"
        "$x.LoadXml(\"<toast><visual><binding template='ToastGeneric'><text>$t</text><text>$b</text>"
        "</binding></visual></toast>\");"
        r"$app='{1AC14E77-02E7-4E5D-B744-2EB1AE5198B7}\WindowsPowerShell\v1.0\powershell.exe';"
        "[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier($app).Show("
        "[Windows.UI.Notifications.ToastNotification]::new($x))")
    env = dict(os.environ, DPH_TITLE=title, DPH_BODY=body)
    try:
        subprocess.Popen(["powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
                          "-Command", script], env=env, creationflags=0x08000000,   # CREATE_NO_WINDOW
                         stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True
    except OSError:
        return False


# ---------------------------------------------------------------- raccourcis dans la fenêtre de l'outil
TAB_NAMES = ("Accueil", "Prix", "Mes ventes", "Calibration", "Raccourcis", "Options")


def tab_index_for_key(keycode: int, keysym: str) -> Optional[int]:
    """Ctrl+1 … Ctrl+6 -> onglet 0 … 5. Par le code de la touche : marche aussi en AZERTY,
    où la rangée du haut donne & é " ' ( - sans Maj."""
    if 49 <= keycode <= 54:          # rangée du haut (VK_1 … VK_6)
        return keycode - 49
    if 97 <= keycode <= 102:         # pavé numérique
        return keycode - 97
    if len(keysym) == 1 and keysym in "123456":
        return int(keysym) - 1
    return None


RELAUNCH_FLAG = "--relance"


def relaunch_command() -> list:
    """Commande qui relance l'outil (après un changement de thème)."""
    import sys
    args = [a for a in sys.argv[1:] if a != RELAUNCH_FLAG] + [RELAUNCH_FLAG]
    if getattr(sys, "frozen", False):          # version .exe
        return [sys.executable] + args
    return [sys.executable, sys.argv[0]] + args


# ---------------------------------------------------------------- dernière lecture : fiabilité
def reading_quality(reading, min_conf: float) -> tuple:
    """(niveau "good" | "doubt" | "bad" | None, texte) pour la pastille d'un prix lu."""
    if reading is None or reading.value is None:
        return None, "Pas lu"
    conf = reading.confidence
    if reading.raw == "estimé":
        return "doubt", "Estimé d'après les autres lots (pas lu directement)"
    if conf >= max(80.0, min_conf + 15):
        level = "good"
    elif conf >= min_conf:
        level = "doubt"
    else:
        level = "bad"
    words = {"good": "lecture sûre", "doubt": "lecture moyenne : vérifie le prix",
             "bad": "lecture douteuse : l'outil ne collera pas ce prix tout seul"}[level]
    raw = f" · lu « {reading.raw} »" if reading.raw and reading.raw != str(reading.value) else ""
    return level, f"Fiabilité {conf:.0f} % : {words}{raw}"


def validate_reminder(res, cfg) -> Optional[str]:
    """Rappel pour le HUD quand le prix est prêt mais pas mis en vente (validation automatique
    coupée) : « Entrée pour valider », ou « Ctrl+V puis Entrée » s'il est seulement copié."""
    msg = res.message.lstrip()
    if res.level != "ok" or not msg.startswith(("[VENTE]", "[OPT]")) or res.new_price is None:
        return None
    done = msg.rsplit(" | ", 1)[-1]
    if done.startswith("saisi") and "mis en vente" not in done:
        return "Prix saisi · Entrée pour valider"
    if done.startswith("copié"):
        return "Prix copié · Ctrl+V puis Entrée"
    return None


HUD_SEL_N = 3          # lignes « objet sélectionné » du HUD (lots 1, 10, 100)
SEL_WATCH_MS = 500     # surveillance du tableau de l'HDV (simple capture, aucune action dans le jeu)


def hud_selected_lines(prices: dict, selected: Optional[int] = None) -> list:
    """Lignes du HUD pour l'objet sélectionné : (texte, couleur ou None), une par lot.
    prices : {lot: prix le moins cher ou None} ; selected : quantité sélectionnée (mise en avant)."""
    out = []
    for lot in sorted(prices)[:HUD_SEL_N]:
        v = prices[lot]
        unit = f"  {fmt(round(v / lot))}/u" if v and lot > 1 else ""
        text = f"x{lot:<4}{fmt(v) if v else '—':>10}{unit}"
        out.append((("◆ " if lot == selected else "  ") + text, "gold" if lot == selected and v else None))
    return out


def layout_for(width: float, height: float) -> dict:
    """Mise en page selon la taille de la fenêtre (en unités d'interface, hors mise à l'échelle)."""
    return {"side": width >= 1000, "subtitle": width >= 760, "log_hint": width >= 860,
            "log_lines": 6 if height >= 760 else 5 if height >= 640 else 4}


def table_signature(img) -> bytes:
    """Empreinte légère d'une capture du tableau : change quand un autre objet est sélectionné."""
    small = img[::6, ::6]
    return (small // 24).tobytes()


def duration_text(seconds) -> str:
    s = max(0, int(round(seconds or 0)))
    return f"{s} s" if s < 60 else f"{s // 60} min {s % 60:02d}"


# ---------------------------------------------------------------- visite guidée
# (onglet, widgets visés par ordre de préférence, titre, texte) ; {touche} = raccourci actuel
TOUR = (
    ("Accueil", ("steps_outer",), "Bienvenue ! D'abord, la calibration",
     "L'outil lit l'Hôtel de vente à l'écran. Ouvre l'HDV sur l'onglet « Vente », puis clique « Calibrer » : "
     "toutes les zones sont placées seules."),
    ("Accueil", ("keys_outer",), "Les touches, dans le jeu",
     "{sell} vend l'objet sélectionné juste sous le moins cher, {sell_all} remet tout en vente et {relist} "
     "met à jour une de tes ventes. {cheatsheet} affiche l'aide-mémoire par-dessus le jeu."),
    ("Accueil", ("chips:state",), "Arrêter un parcours",
     "Pendant Tout vendre ou Toute la liste, {pause} depuis le jeu arrête le parcours après la ligne en "
     "cours. Ici, cette pastille devient « ■ Arrêter le parcours » : un clic fait pareil."),
    ("Options", ("hud_switch",), "Le HUD, par-dessus le jeu",
     "Une ligne discrète montre le résultat de chaque action et la progression d'un parcours. {hud} "
     "l'affiche ou le cache, « Déplacer » le pose où tu veux."),
    ("Accueil", ("log_frame",), "Le journal",
     "Tout ce que fait l'outil, ligne par ligne. Un clic sur une ligne avec un prix le copie. "
     "Pour revoir cette visite : « Visite guidée », dans l'onglet Accueil."),
)


def tour_steps(hk: dict) -> list:
    keys = {k: str(v).upper() for k, v in hk.items()}
    return [{"tab": tab, "targets": targets, "title": title, "text": text.format(**keys)}
            for tab, targets, title, text in TOUR]


def tour_place(target, size, area, gap: int = 12) -> tuple:
    """Position (x, y) de la bulle de taille `size` près de `target` (x, y, l, h), dans `area`
    (x0, y0, x1, y1) : dessous, sinon dessus, à droite, à gauche ; au centre sans cible."""
    bw, bh = size
    x0, y0, x1, y1 = area

    def clamp(v, lo, hi):
        return max(lo, min(v, hi)) if hi >= lo else lo
    if target is None:
        return (x0 + (x1 - x0 - bw) // 2, y0 + (y1 - y0 - bh) // 2)
    tx, ty, tw, th = target
    cx = clamp(tx, x0 + gap, x1 - bw - gap)
    cy = clamp(ty, y0 + gap, y1 - bh - gap)
    if ty + th + gap + bh <= y1:
        return (cx, ty + th + gap)
    if ty - gap - bh >= y0:
        return (cx, ty - gap - bh)
    if tx + tw + gap + bw <= x1:
        return (tx + tw + gap, cy)
    if tx - gap - bw >= x0:
        return (tx - gap - bw, cy)
    return (cx, clamp(y1 - bh - gap, y0, y1))


HUD_SIZES = {"small": ("Petit", 11), "normal": ("Normal", 12), "large": ("Grand", 15)}
HUD_CONTENTS = {"state": "État", "action": "Action", "both": "Les deux", "dot": "Pastille"}
HUD_SHAPES = {"card": "Carte", "pill": "Pilule", "minimal": "Minimal"}
HUD_COUNT_MS = 380     # le nouveau prix « défile » jusqu'à sa valeur
HUD_RESIZE_MS = 150    # le HUD change de taille en douceur
HUD_BREATH_S = 1.8     # pendant un parcours, le rond d'état « respire » (période)
HUD_PULSE_S = 0.6      # à chaque résultat, le rond s'illumine puis revient


def count_value(start: int, end: int, frac: float) -> int:
    """Valeur affichée pendant le défilement d'un prix (frac 0..1, courbe douce)."""
    return round(start + (end - start) * style.ease_out(frac))


def breath(t: float, period: float = HUD_BREATH_S) -> float:
    """0..1..0 en douceur sur une période (respiration du rond d'état)."""
    import math
    return (1 - math.cos(2 * math.pi * (t % period) / period)) / 2
HUD_AUTOHIDE = {0: "Jamais", 10: "10 s", 30: "30 s", 60: "1 min"}
HUD_EXPAND_S = 2.5    # mode pastille : le HUD s'agrandit ce temps-là à chaque action
ALT_HOLD_S = 0.25     # Alt maintenu ce temps-là (seul) : HUD cliquable


def eta_text(elapsed: float, frac: Optional[float]) -> Optional[str]:
    """Temps restant d'un parcours, d'après le rythme jusqu'ici ; None trop tôt pour estimer."""
    if frac is None or frac < 0.05 or elapsed < 5:
        return None
    left = elapsed * (1 - frac) / frac
    if left < 10:
        return "presque fini"
    if left < 60:
        return f"≈ {max(10, int(round(left / 5) * 5))} s restantes"
    return f"≈ {-int(-left // 60)} min restantes"


CALIB_WATCH_MS = 5000      # vérification de la calibration (fenêtre du jeu, écran)
HUD_ALERT_LEN = 70


def hud_calib_alert(drift: Optional[str], hdv_state: Optional[str], calibrated: bool) -> Optional[tuple]:
    """Alerte calibration pour le HUD : (titre, détail), ou None si tout va bien.
    drift = texte du bandeau « calibration décalée » ; hdv_state = "lost" si le repère est introuvable."""
    if not calibrated:
        return None                               # déjà signalé : « Calibration à faire »
    if drift:
        why = drift.split(" : ", 1)[-1].split(". ")[0].strip().rstrip(".")
        if len(why) > HUD_ALERT_LEN:
            why = why[:HUD_ALERT_LEN - 1].rstrip(" ,") + "…"
        return "Calibration décalée", why
    if hdv_state == "lost":
        return "HDV introuvable", "l'HDV est-il ouvert, onglet Vente ?"
    return None


def alt_alone_down() -> bool:
    """Alt enfoncé seul (sans Ctrl, Maj, Windows ni Tab : pas un raccourci ni Alt+Tab). Windows."""
    if sys.platform != "win32":
        return False
    try:
        import ctypes
        state = ctypes.windll.user32.GetAsyncKeyState

        def down(vk):
            return bool(state(vk) & 0x8000)
        return down(0x12) and not any(down(vk) for vk in (0x11, 0x10, 0x5B, 0x5C, 0x09))
    except Exception:
        return False


# ---------------------------------------------------------------- accueil : premiers pas
FIRST_STEPS = (("calib", "Calibrer l'HDV"), ("read", "Tester une lecture"), ("sell", "Première vente"))

