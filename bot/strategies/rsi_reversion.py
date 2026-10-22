"""
Strategies - RSI mean reversion.

Retour a la moyenne : on achete en survente, on vend en surachat.
"""
from __future__ import annotations

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from strategy import rsi  # noqa: E402

NAME = "rsi_reversion"
DESCRIPTION = "Retour a la moyenne : survente / surachat (RSI)"
PARAMS = {
    "period": {"type": "int", "min": 2, "max": 50, "default": 14, "label": "Periode RSI"},
    "oversold": {"type": "float", "min": 5, "max": 49, "default": 30, "label": "Survente (<)"},
    "overbought": {"type": "float", "min": 51, "max": 95, "default": 70, "label": "Surachat (>)"},
}


def evaluate(bars, params):
    period = int(params.get("period", PARAMS["period"]["default"]))
    oversold = float(params.get("oversold", PARAMS["oversold"]["default"]))
    overbought = float(params.get("overbought", PARAMS["overbought"]["default"]))
    reentry = bool(params.get("allow_reentry", True))

    closes = [b["c"] for b in bars if b.get("c") is not None]
    if len(closes) < period + 3:
        return {"action": "none", "reason": f"historique insuffisant pour RSI{period}"}
    if not (0 < oversold < overbought < 100):
        return {"action": "none", "reason": f"seuils invalides ({oversold}/{overbought})"}

    r = rsi(closes, period)
    if len(r) < 2:
        return {"action": "none", "reason": "RSI non calculable"}

    now, prev = r[-1], r[-2]
    info = {"rsi": round(now, 2), "prev_rsi": round(prev, 2),
            "oversold": oversold, "overbought": overbought}

    if now < oversold:
        if prev >= oversold:
            return {"action": "buy", "reason": f"RSI entre en survente ({now:.1f})", **info}
        if reentry:
            return {"action": "buy", "reason": f"toujours en survente (RSI {now:.1f}) - re-entree", **info}
        return {"action": "none", "reason": "survente mais re-entree desactivee", **info}
    if now > overbought:
        if prev <= overbought:
            return {"action": "sell", "reason": f"RSI entre en surachat ({now:.1f})", **info}
        if reentry:
            return {"action": "sell", "reason": f"toujours en surachat (RSI {now:.1f}) - re-entree", **info}
        return {"action": "none", "reason": "surachat mais re-entree desactivee", **info}
    return {"action": "none", "reason": f"RSI neutre ({now:.1f})", **info}
