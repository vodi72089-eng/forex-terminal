"""
Strategies - EMA crossover.

Module de strategie interchangeable. Pour en ajouter une :
  1. cree un fichier .py dans bot/strategies/ (ou dans le dossier
     %APPDATA%\\com.forex.terminal\\strategies\\ pour une strategie perso)
  2. expose NAME, DESCRIPTION, PARAMS et une fonction evaluate(bars, params)
  3. elle apparait automatiquement dans le dashboard

Contrat de evaluate() :
  bars   : liste de barres CLOSES, de la plus ancienne a la plus recente
           [{t, o, h, l, c, v}, ...]
  params : dictionnaire de parametres (deja valide par le bot)
  retour : {"action": "buy" | "sell" | "none", "reason": "...", ...}
"""
from __future__ import annotations

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from strategy import ema  # noqa: E402

NAME = "ema_cross"
DESCRIPTION = "Tendance : croisement EMA rapide / EMA lente"
PARAMS = {
    "fast": {"type": "int", "min": 2, "max": 200, "default": 9, "label": "EMA rapide"},
    "slow": {"type": "int", "min": 2, "max": 200, "default": 21, "label": "EMA lente"},
}


def evaluate(bars, params):
    fast = int(params.get("fast", PARAMS["fast"]["default"]))
    slow = int(params.get("slow", PARAMS["slow"]["default"]))
    reentry = bool(params.get("allow_reentry", True))

    closes = [b["c"] for b in bars if b.get("c") is not None]
    if len(closes) < slow + 3:
        return {"action": "none", "reason": f"historique insuffisant ({len(closes)} barres)"}
    if fast >= slow:
        return {"action": "none", "reason": f"EMA rapide ({fast}) doit etre < EMA lente ({slow})"}

    ef = ema(closes, fast)
    es = ema(closes, slow)
    if len(ef) < 2 or len(es) < 2:
        return {"action": "none", "reason": "EMA non calculable"}

    d_now = ef[-1] - es[-1]
    d_prev = ef[-2] - es[-2]
    info = {
        "fast_value": round(ef[-1], 6),
        "slow_value": round(es[-1], 6),
        "spread": round(d_now, 8),
        "prev_spread": round(d_prev, 8),
    }

    if d_now > 0:
        if d_prev <= 0:
            return {"action": "buy", "reason": f"EMA{fast} croise au-dessus de EMA{slow}", **info}
        if reentry:
            return {"action": "buy",
                    "reason": f"tendance haussiere maintenue (EMA{fast} > EMA{slow}) - re-entree",
                    **info}
        return {"action": "none", "reason": "tendance haussiere mais re-entree desactivee", **info}
    if d_now < 0:
        if d_prev >= 0:
            return {"action": "sell", "reason": f"EMA{fast} croise sous EMA{slow}", **info}
        if reentry:
            return {"action": "sell",
                    "reason": f"tendance baissiere maintenue (EMA{fast} < EMA{slow}) - re-entree",
                    **info}
        return {"action": "none", "reason": "tendance baissiere mais re-entree desactivee", **info}
    return {"action": "none", "reason": f"EMA{fast} et EMA{slow} confondues", **info}
