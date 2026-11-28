"""Tes prix : reconnaître TES ventes dans le tableau (pas d'undercut contre toi-même)."""
from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path
from typing import Dict, Optional

import numpy as np

from .base import BASE_DIR
from .anchor import _gray


# --------------------------------------------------------------------------
# Tes prix : reconnaître TES ventes dans le tableau (pas d'undercut contre toi-même)
# --------------------------------------------------------------------------
MY_PRICES_PATH = BASE_DIR / "dofus_my_prices.json"
MY_PRICES_TTL = 2 * 86400   # s : un prix de vente vu ou posé est oublié après 2 jours


def item_key(img: Optional[np.ndarray]) -> Optional[str]:
    """Empreinte de l'objet = image binarisée de son nom (même objet -> mêmes pixels).
    None si rien n'est écrit (panneau vide) : on ne sait alors pas de quel objet il s'agit."""
    if img is None or img.size == 0:
        return None
    import hashlib
    ink = _gray(img) > 110
    if ink.sum() < 15:
        return None
    return hashlib.sha1(np.packbits(ink).tobytes() + str(ink.shape).encode()).hexdigest()[:16]


class MyPrices:
    """Prix de tes ventes en cours, par objet (empreinte du nom) et par lot.
    Si le moins cher du tableau est l'un d'eux, c'est toi : on s'aligne au lieu de passer
    dessous. Sans ça, chaque Ctrl+F3 baissait tes propres ventes d'un cran.
    - « sûr » (objet reconnu, vente confirmée ou prix lu) : gardé 2 jours, sur le disque ;
    - sinon (objet inconnu) : mémoire courte (OWN_PRICE_TTL), par lot seulement, comme avant."""

    def __init__(self, path: Optional[Path] = None):
        self.path = path
        self._lock = threading.Lock()
        self._data: Optional[Dict[str, Dict[str, float]]] = None   # "clé|lot" -> {prix: t}
        self._short: Dict[tuple, float] = {}                       # (clé, lot, prix) -> t

    def _load(self) -> Dict[str, Dict[str, float]]:
        if self._data is None:
            self._data = {}
            if self.path and self.path.exists():
                try:
                    raw = json.loads(self.path.read_text(encoding="utf-8"))
                    self._data = {k: {str(p): float(t) for p, t in v.items()} for k, v in raw.items()}
                except (OSError, ValueError, AttributeError):
                    self._data = {}
        return self._data

    def _save(self) -> None:
        if not self.path:
            return
        now = time.time()
        data = {k: {p: t for p, t in v.items() if now - t <= MY_PRICES_TTL} for k, v in self._data.items()}
        data = {k: v for k, v in data.items() if v}
        self._data = data
        try:
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps(data), encoding="utf-8")
            os.replace(tmp, self.path)
        except OSError as e:
            print(f"[Tes prix] Sauvegarde impossible : {e}")

    def has(self, key: Optional[str], lot: int, price: Optional[int], short_ttl: float) -> bool:
        if price is None:
            return False
        now = time.time()
        with self._lock:
            if key is not None:
                t = self._load().get(f"{key}|{lot}", {}).get(str(price))
                if t is not None and now - t <= MY_PRICES_TTL:
                    return True
            # clé None = objet non reconnu à ce moment-là : peut être le même objet (prudence)
            ts = [self._short.get((k, lot, price)) for k in {key, None}]
            return any(t is not None and now - t <= short_ttl for t in ts)

    def keep_only(self, listed: set) -> int:
        """Après un parcours COMPLET de « mes ventes » : seules les ventes vues {(clé, lot, prix)}
        existent encore. Les autres ont été vendues : oubliées, sinon un concurrent au même prix
        passait pour toi pendant 2 jours (aligné au lieu de passer dessous).
        Retourne le nombre de prix oubliés."""
        removed = 0
        with self._lock:
            data = self._load()
            for k, prices in list(data.items()):
                key, _, lot = k.rpartition("|")
                for p in list(prices):
                    try:
                        seen = (key, int(lot), int(p)) in listed
                    except ValueError:
                        seen = False
                    if not seen:
                        del prices[p]
                        removed += 1
            if removed:
                self._save()
        return removed

    def add(self, key: Optional[str], lot: int, price: Optional[int], sure: bool = True,
            replaces: Optional[int] = None) -> None:
        """Note une de tes ventes à `price`. `replaces` = son ancien prix (modifiée)."""
        if price is None:
            return
        with self._lock:
            self._short[(key, lot, price)] = time.time()
            if key is None or not sure:
                return
            entry = self._load().setdefault(f"{key}|{lot}", {})
            if replaces is not None and replaces != price:
                entry.pop(str(replaces), None)
            entry[str(price)] = time.time()
            self._save()

