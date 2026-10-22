"""
Strategies - Breakout.

Le cloture depasse le plus haut (ou le plus bas) des N dernieres barres
precedentes : on entre dans le sens du mouvement.
"""
from __future__ import annotations

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

NAME = "breakout"
DESCRIPTION = "Cassure du range des N dernieres barres"
PARAMS = {
    "lookback": {"type": "int", "min": 5, "max": 200, "default": 20, "label": "Lookback (barres)"},
}


def evaluate(bars, params):
    lookback = int(params.get("lookback", PARAMS["lookback"]["default"]))
    reentry = bool(params.get("allow_reentry", True))

    closes = [b["c"] for b in bars if b.get("c") is not None]
    highs = [b.get("h") for b in bars if b.get("h") is not None]
    lows = [b.get("l") for b in bars if b.get("l") is not None]
    n = lookback + 1
    if len(closes) < n + 1:
        return {"action": "none", "reason": f"historique insuffisant pour breakout({lookback})"}
    if len(highs) != len(closes) or len(lows) != len(closes):
        return {"action": "none", "reason": "donnees OHLC incompletes"}

    last_c = closes[-1]
    prev_hi = max(highs[-n - 1: -1])
    prev_lo = min(lows[-n - 1: -1])
    info = {"close": last_c, "prev_high": prev_hi, "prev_low": prev_lo, "lookback": lookback}

    if last_c > prev_hi:
        if reentry:
            return {"action": "buy", "reason": f"au-dessus du plus haut precedent ({prev_hi:.6f})", **info}
        return {"action": "none", "reason": "au-dessus du range mais re-entree desactivee", **info}
    if last_c < prev_lo:
        if reentry:
            return {"action": "sell", "reason": f"sous le plus bas precedent ({prev_lo:.6f})", **info}
        return {"action": "none", "reason": "sous le range mais re-entree desactivee", **info}
    return {"action": "none", "reason": "pas de cassure", **info}
