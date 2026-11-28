"""Calcul du prix (pur, testé)."""
from __future__ import annotations

import math
import statistics
from typing import Dict, Optional


# --------------------------------------------------------------------------
# Calcul du prix (pur, testé)
# --------------------------------------------------------------------------
def floor_price(lot: int, avg: Optional[int], ratio: float) -> Optional[int]:
    """Prix plancher du lot = ratio × prix moyen (par objet) × lot, arrondi au-dessus."""
    if not avg or ratio <= 0:
        return None
    # round() avant l'arrondi au-dessus : 3 × 0.8 × 10 = 24.000000000000004 en flottant -> 25
    return max(1, math.ceil(round(avg * ratio * lot, 6)))


def smart_round(p: int, mode: str) -> int:
    """Arrondi toujours VERS LE BAS (ne doit jamais remonter le prix)."""
    if mode == "down_10":
        return (p // 10) * 10
    if mode == "down_100":
        return (p // 100) * 100
    if mode == "end_9":
        return p if p % 10 == 9 else p - (p % 10) - 1
    return p


def compute_price(price: Optional[int], mode: str, value, rounding: str,
                  min_price: int) -> Optional[int]:
    """Prix d'undercut. Garantit new < price (sauf si on bute sur min_price)."""
    if price is None:
        return None
    if mode == "percent":
        try:
            v = float(value)
        except (TypeError, ValueError):
            v = 1.0
        new_p = int(price * (1 - v / 100.0))  # floor
    else:
        try:
            v = int(float(value))
        except (TypeError, ValueError):
            v = 1
        new_p = price - v
    new_p = smart_round(new_p, rounding)
    if new_p >= price:
        new_p = price - 1
    return max(int(min_price), new_p)


def pick_best_lot(prices: Dict[int, Optional[int]], tolerance: float = 0.01) -> Optional[int]:
    """Lot au meilleur prix unitaire. Ex aequo (± tolerance) -> plus petit lot."""
    unit = {lot: p / lot for lot, p in prices.items() if p}
    if not unit:
        return None
    best = max(unit.values())
    return min(lot for lot, u in unit.items() if u >= best * (1 - tolerance))


def check_coherence(lot: int, prices: Dict[int, Optional[int]], max_ratio: float) -> Optional[str]:
    """Écart du prix unitaire du lot vs les autres lots (chiffre perdu/ajouté)."""
    p = prices.get(lot)
    if not p:
        return None
    others = [q / l for l, q in prices.items() if l != lot and q]
    if not others:
        return None
    u, ref = p / lot, statistics.median(others)
    if ref <= 0:
        return None
    ratio = u / ref
    if ratio > max_ratio or ratio < 1 / max_ratio:
        return f"prix unitaire {u:.0f} vs {ref:.0f} pour les autres lots (x{ratio:.1f})"
    return None


def derive_price(lot: int, prices: Dict[int, Optional[int]]) -> Optional[int]:
    """Personne ne vend ce lot : estimation = plus bas prix unitaire des autres lots × lot."""
    units = [p / l for l, p in prices.items() if p and l != lot]
    if not units:
        return None
    return max(1, int(min(units) * lot))

