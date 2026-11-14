#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Tableau de bord — Dofus Price Helper
------------------------------------
Lit dofus_price_history.csv (et les anciens fichiers archivés *_old_*.csv) et produit
dashboard.html : une page autonome (aucune connexion internet), ouverte dans le
navigateur.

    python dofus_dashboard.py            # génère et ouvre la page
    python dofus_dashboard.py --no-open  # génère seulement

Contenu : chiffres clés, mises en vente et kamas par jour, modifications de prix par
jour, activité par heure, répartition par lot, baisse moyenne appliquée, dernières
actions. L'historique ne contient pas le NOM des objets : pas de détail par objet.
"""
from __future__ import annotations

import csv
import html
import sys
import webbrowser
from collections import Counter, OrderedDict
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

BASE_DIR = Path(__file__).resolve().parent
HISTORY = BASE_DIR / "dofus_price_history.csv"
OUT = BASE_DIR / "dashboard.html"

# Palette (thème sombre, validée) : une couleur par graphique, une seule série chacun.
SURFACE, CARD, GRID = "#1a1a19", "#232322", "#33332f"
INK, INK2, MUTED = "#f0efec", "#c3c2b7", "#8f8e86"
BLUE, ORANGE, AQUA = "#3987e5", "#d95926", "#199e70"

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
    return {
        "rows": rows, "days": OrderedDict((d, v) for d, v in days.items() if any(v.values())), "hours": hours, "lots": lots, "count": k,
        "kamas": kamas, "drop": (sum(drops) / len(drops)) if drops else None,
        "suspect_rate": (k["suspect"] / (acted + k["suspect"]) * 100) if acted + k["suspect"] else None,
        "first": datetime.fromtimestamp(int(rows[0]["ts"])) if rows else None,
        "last": datetime.fromtimestamp(int(rows[-1]["ts"])) if rows else None,
    }


def fmt(n) -> str:
    if n is None:
        return "—"
    if isinstance(n, float):
        return f"{n:,.1f}".replace(",", " ").replace(".", ",")
    return f"{n:,}".replace(",", " ")


def bar_chart(labels: List[str], values: List[int], color: str, unit: str,
              width: int = 560, height: int = 220) -> str:
    """Barres verticales, une série. Survol = valeur exacte (info-bulle)."""
    if not values or max(values) == 0:
        return f'<p class="empty">Pas encore de données.</p>'
    left, bottom, top, right = 52, 34, 14, 8
    pw, ph = width - left - right, height - top - bottom
    vmax = max(values)
    step = _nice(vmax)
    vmax = step * ((vmax + step - 1) // step)
    n = len(values)
    slot = pw / n
    bw = max(3.0, min(36.0, slot - 2))  # 2 px d'écart entre barres
    out = [f'<svg viewBox="0 0 {width} {height}" role="img" class="chart">']
    for i in range(0, vmax + 1, step):
        y = top + ph - ph * i / vmax
        out.append(f'<line x1="{left}" x2="{width - right}" y1="{y:.1f}" y2="{y:.1f}" class="grid"/>')
        out.append(f'<text x="{left - 6}" y="{y + 4:.1f}" class="tick" text-anchor="end">{fmt(i)}</text>')
    every = max(1, n // 8)
    for i, (lab, v) in enumerate(zip(labels, values)):
        x = left + i * slot + (slot - bw) / 2
        h = ph * v / vmax if vmax else 0
        y = top + ph - h
        r = min(4.0, bw / 2, h)
        tip = html.escape(f"{lab} : {fmt(v)} {unit}")
        # zone de survol plus large que la barre
        out.append(f'<g class="bar"><title>{tip}</title>'
                   f'<rect x="{left + i * slot:.1f}" y="{top}" width="{slot:.1f}" height="{ph}" fill="transparent"/>')
        if h > 0:
            out.append(f'<path d="{_top_rounded(x, y, bw, h, r)}" fill="{color}"/>')
        out.append("</g>")
        if i % every == 0:
            out.append(f'<text x="{x + bw / 2:.1f}" y="{height - 12}" class="tick" text-anchor="middle">'
                       f'{html.escape(lab)}</text>')
    out.append(f'<line x1="{left}" x2="{width - right}" y1="{top + ph}" y2="{top + ph}" class="axis"/>')
    out.append("</svg>")
    return "".join(out)


def _top_rounded(x, y, w, h, r) -> str:
    """Rectangle dont seuls les coins du haut sont arrondis (posé sur l'axe)."""
    return (f"M{x:.1f},{y + h:.1f} V{y + r:.1f} Q{x:.1f},{y:.1f} {x + r:.1f},{y:.1f} "
            f"H{x + w - r:.1f} Q{x + w:.1f},{y:.1f} {x + w:.1f},{y + r:.1f} V{y + h:.1f} Z")


def _nice(vmax: int) -> int:
    if vmax <= 5:
        return 1
    raw = vmax / 4
    mag = 10 ** (len(str(int(raw))) - 1)
    for m in (1, 2, 5, 10):
        if raw <= m * mag:
            return int(m * mag)
    return int(10 * mag)


def render(data: Dict) -> str:
    c = data["count"]
    days = data["days"]
    dl = [d[5:].replace("-", "/") for d in days]  # MM/JJ
    period = (f"du {data['first']:%d/%m/%Y} au {data['last']:%d/%m/%Y}" if data["first"] else "aucune donnée")
    tiles = [
        ("Lots mis en vente", fmt(c["vente"]), ""),
        ("Kamas mis en vente", fmt(data["kamas"]), "somme des prix de mise en vente"),
        ("Prix modifiés", fmt(c["modif"]), "F3 / Ctrl+F3"),
        ("Baisse moyenne", (fmt(data["drop"]) + " %") if data["drop"] is not None else "—",
         "par rapport au moins cher lu"),
        ("Lectures suspectes", fmt(c["suspect"]),
         (fmt(data["suspect_rate"]) + " % des actions") if data["suspect_rate"] is not None else ""),
    ]
    tiles_html = "".join(f'<div class="tile"><div class="tl">{html.escape(a)}</div>'
                         f'<div class="tv">{html.escape(b)}</div><div class="ts">{html.escape(s)}</div></div>'
                         for a, b, s in tiles)
    lots = data["lots"]
    lot_keys = sorted(lots)
    hours = data["hours"]
    recent = list(reversed(data["rows"][-40:]))
    labels = {"vente": "Mise en vente", "modif": "Prix modifié", "suspect": "Suspect",
              "copie": "Copié", "autre": "Lecture"}
    trs = "".join(
        f"<tr><td>{html.escape(r['datetime'])}</td><td>{labels[kind(r)]}</td>"
        f"<td class='n'>{html.escape(r.get('lot', ''))}</td><td class='n'>{fmt(_int(r.get('read_price')))}</td>"
        f"<td class='n'>{fmt(_int(r.get('new_price')))}</td><td>{html.escape(r.get('status', ''))}</td></tr>"
        for r in recent)
    day_table = "".join(f"<tr><td>{d}</td><td class='n'>{fmt(v['ventes'])}</td><td class='n'>{fmt(v['kamas'])}</td>"
                        f"<td class='n'>{fmt(v['modifs'])}</td></tr>" for d, v in reversed(days.items()))
    return f"""<!DOCTYPE html>
<html lang="fr"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Tableau de bord — Dofus Price Helper</title>
<style>
:root {{ color-scheme: dark; }}
* {{ box-sizing: border-box; }}
body {{ margin: 0; background: {SURFACE}; color: {INK}; font: 14px/1.45 "Segoe UI", system-ui, sans-serif; }}
main {{ max-width: 1240px; margin: 0 auto; padding: 24px; }}
h1 {{ font-size: 22px; margin: 0; }}
.sub {{ color: {INK2}; margin: 4px 0 20px; }}
.tiles {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(190px, 1fr)); gap: 12px; margin-bottom: 16px; }}
.tile {{ background: {CARD}; border-radius: 10px; padding: 14px 16px; }}
.tl {{ color: {INK2}; font-size: 13px; }}
.tv {{ font-size: 28px; font-weight: 600; margin: 2px 0; font-variant-numeric: tabular-nums; }}
.ts {{ color: {MUTED}; font-size: 12px; min-height: 16px; }}
.grid2 {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(480px, 1fr)); gap: 12px; }}
.card {{ background: {CARD}; border-radius: 10px; padding: 14px 16px 8px; }}
.card h2 {{ font-size: 15px; margin: 0 0 2px; }}
.card p.note {{ color: {MUTED}; font-size: 12px; margin: 0 0 6px; }}
svg.chart {{ width: 100%; height: auto; display: block; }}
.grid {{ stroke: {GRID}; stroke-width: 1; }}
.axis {{ stroke: {MUTED}; stroke-width: 1; }}
.tick {{ fill: {MUTED}; font-size: 11px; font-variant-numeric: tabular-nums; }}
.bar:hover path {{ opacity: .8; }}
.empty {{ color: {MUTED}; }}
table {{ width: 100%; border-collapse: collapse; font-variant-numeric: tabular-nums; }}
th, td {{ text-align: left; padding: 5px 8px; border-bottom: 1px solid {GRID}; white-space: nowrap; }}
th {{ color: {INK2}; font-weight: 600; font-size: 12px; }}
td.n, th.n {{ text-align: right; }}
.scroll {{ max-height: 360px; overflow: auto; }}
details summary {{ cursor: pointer; color: {INK2}; margin: 6px 0; }}
footer {{ color: {MUTED}; font-size: 12px; margin-top: 18px; }}
</style></head>
<body><main>
<h1>Tableau de bord</h1>
<div class="sub">Dofus Price Helper — historique {period} · {fmt(len(data['rows']))} lignes · généré le {datetime.now():%d/%m/%Y à %H:%M}</div>
<div class="tiles">{tiles_html}</div>
<div class="grid2">
  <section class="card"><h2>Lots mis en vente par jour</h2><p class="note">F1, F2 (avec mise en vente), forcées comprises</p>
    {bar_chart(dl, [v['ventes'] for v in days.values()], BLUE, "lots")}</section>
  <section class="card"><h2>Kamas mis en vente par jour</h2><p class="note">Somme des prix des lots mis en vente</p>
    {bar_chart(dl, [v['kamas'] for v in days.values()], AQUA, "kamas")}</section>
  <section class="card"><h2>Prix modifiés par jour</h2><p class="note">Mises à jour de tes ventes (F3 / Ctrl+F3)</p>
    {bar_chart(dl, [v['modifs'] for v in days.values()], ORANGE, "modifications")}</section>
  <section class="card"><h2>Activité par heure</h2><p class="note">Ventes + modifications, toutes journées confondues</p>
    {bar_chart([f"{h}h" for h in range(24)], [hours.get(h, 0) for h in range(24)], BLUE, "actions")}</section>
  <section class="card"><h2>Mises en vente par taille de lot</h2><p class="note">Nombre de lots vendus par quantité</p>
    {bar_chart([f"lot {l}" for l in lot_keys], [lots[l] for l in lot_keys], BLUE, "lots")}</section>
  <section class="card"><h2>Par jour (tableau)</h2>
    <div class="scroll"><table><tr><th>Jour</th><th class="n">Lots</th><th class="n">Kamas</th><th class="n">Modifs</th></tr>{day_table}</table></div></section>
</div>
<section class="card" style="margin-top:12px"><h2>Dernières actions</h2>
  <div class="scroll"><table><tr><th>Date</th><th>Action</th><th class="n">Lot</th><th class="n">Prix lu</th><th class="n">Nouveau prix</th><th>Statut</th></tr>{trs}</table></div>
</section>
<footer>« Kamas mis en vente » = prix affichés à l'HDV, pas des ventes conclues (le jeu ne les communique pas à l'outil). L'historique ne contient pas le nom des objets.</footer>
</main></body></html>"""


def build(history: Path = HISTORY, out: Path = OUT) -> Path:
    data = compute(load_rows(history))
    out.write_text(render(data), encoding="utf-8")
    return out


def main(argv: List[str]) -> int:
    out = build()
    print(f"Tableau de bord : {out}")
    if "--no-open" not in argv:
        webbrowser.open(out.as_uri())
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
