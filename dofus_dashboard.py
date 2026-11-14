#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Tableau de bord — calculs
-------------------------
Lit dofus_price_history.csv (et les anciens fichiers archivés *_old_*.csv) et calcule
les chiffres affichés dans l'onglet « Tableau de bord » de l'interface : chiffres clés,
lots et kamas mis en vente par jour, prix modifiés par jour, activité par heure,
répartition par lot, baisse moyenne, dernières actions.
L'historique ne contient pas le NOM des objets : pas de détail par objet.
"""
from __future__ import annotations

import csv
from collections import Counter, OrderedDict
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

BASE_DIR = Path(__file__).resolve().parent
HISTORY = BASE_DIR / "dofus_price_history.csv"

SELL_STATUSES = ("mis en vente", "sell_all")


def load_rows(path: Path = HISTORY) -> List[Dict[str, str]]:
    files = sorted(path.parent.glob(path.stem + "_old_*.csv")) + [path]
    rows: List[Dict[str, str]] = []
    for f in files:
        if not f.exists():
            continue
        try:
            with f.open(encoding="utf-8", newline="") as fh:
                for r in csv.DictReader(fh):
                    if r.get("ts", "").isdigit():
                        rows.append(r)
        except (OSError, csv.Error):
            continue
    rows.sort(key=lambda r: int(r["ts"]))
    return rows


def _int(v: Optional[str]) -> Optional[int]:
    try:
        return int(float(v)) if v not in (None, "") else None
    except ValueError:
        return None


def kind(r: Dict[str, str]) -> str:
    """vente | modif | suspect | copie | autre"""
    a, st = r.get("action", ""), r.get("status", "")
    if a == "sell" and (any(s in st for s in SELL_STATUSES) or st == "forced"):
        return "vente"
    if a == "relist" and st in ("modified", "forced"):
        return "modif"
    if "suspect" in st:
        return "suspect"
    if a in ("sell", "copy"):
        return "copie"
    if a == "observe":
        return "vu"
    return "autre"


def compute(rows: List[Dict[str, str]]) -> Dict:
    days: "OrderedDict[str, Dict[str, int]]" = OrderedDict()
    hours = Counter()
    lots = Counter()
    drops: List[float] = []
    k = Counter()
    kamas = 0
    for r in rows:
        kd = kind(r)
        k[kd] += 1
        dt = datetime.fromtimestamp(int(r["ts"]))
        d = days.setdefault(dt.strftime("%Y-%m-%d"), {"ventes": 0, "kamas": 0, "modifs": 0})
        new, read, lot = _int(r.get("new_price")), _int(r.get("read_price")), _int(r.get("lot"))
        if kd == "vente":
            d["ventes"] += 1
            d["kamas"] += new or 0
            kamas += new or 0
            hours[dt.hour] += 1
            if lot:
                lots[lot] += 1
        elif kd == "modif":
            d["modifs"] += 1
            hours[dt.hour] += 1
        if kd in ("vente", "modif") and new and read and read > new:
            drops.append((read - new) / read * 100)
    acted = k["vente"] + k["modif"]
    items = compute_items(rows)
    return {
        "items": items,
        "rows": rows, "days": OrderedDict((d, v) for d, v in days.items() if any(v.values())), "hours": hours, "lots": lots, "count": k,
        "kamas": kamas, "drop": (sum(drops) / len(drops)) if drops else None,
        "suspect_rate": (k["suspect"] / (acted + k["suspect"]) * 100) if acted + k["suspect"] else None,
        "first": datetime.fromtimestamp(int(rows[0]["ts"])) if rows else None,
        "last": datetime.fromtimestamp(int(rows[-1]["ts"])) if rows else None,
    }


def compute_items(rows: List[Dict[str, str]]) -> Dict[str, Dict]:
    """Par objet (variantes de lecture regroupées) : ventes, modifs, et série de prix
    par objet dans le temps : moins cher lu, ton prix."""
    from dofus_items import group_names
    canon = group_names(r.get("item", "") for r in rows)
    out: Dict[str, Dict] = {}
    for r in rows:
        raw = r.get("item", "")
        if not raw:
            continue
        name = canon.get(raw, raw)
        it = out.setdefault(name, {"ventes": 0, "modifs": 0, "points": []})
        kd = kind(r)
        if kd == "vente":
            it["ventes"] += 1
        elif kd == "modif":
            it["modifs"] += 1
        lot, read, new = _int(r.get("lot")), _int(r.get("read_price")), _int(r.get("new_price"))
        if not lot or not read or kd in ("suspect",):
            continue
        mine = new / lot if new and kd in ("vente", "modif", "vu") else None
        it["points"].append((int(r["ts"]), read / lot, mine))
    for it in out.values():
        it["last_low"] = it["points"][-1][1] if it["points"] else None
    return dict(sorted(out.items(), key=lambda kv: -(len(kv[1]["points"]) + kv[1]["ventes"])))


def fmt(n) -> str:
    if n is None:
        return "—"
    if isinstance(n, float):
        return f"{n:,.1f}".replace(",", " ").replace(".", ",")
    return f"{n:,}".replace(",", " ")


LABELS = {"vente": "Mise en vente", "modif": "Prix modifié", "suspect": "Suspect",
          "copie": "Copié", "vu": "Déjà au bon prix", "autre": "Lecture"}
