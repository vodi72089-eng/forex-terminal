"""
Forex Terminal — moteur de strategies.

CONTRAIT : ce module ne touche JAMAIS a MetaTrader5 et n'ouvre aucun ordre.
Il transforme des donnees de marche (barres) + une config en une DECISION.
Le bot (main.py) est seul autorise a executer cette decision.

Strategies disponibles :
  ema_cross       croisement EMA rapide / EMA lente
  rsi_reversion   retour a la moyenne sur extremite RSI
  breakout        cassure du plus haut / plus bas des N dernieres barres

Chaque signal est calcule sur des BARRES CLOSES uniquement (index 0 exclu :
dans mt5.copy_rates_from_pos la barre 0 est la barre en cours de formation).
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

log = logging.getLogger("bot.strategy")

# ── Timeframes supportes (minutes) ─────────────────────────────────────────
TIMEFRAMES = {
    "M1": 1, "M5": 5, "M15": 15, "M30": 30,
    "H1": 60, "H4": 240, "D1": 1440,
}

STRATEGY_NAMES = ("ema_cross", "rsi_reversion", "breakout")


# ── Indicateurs ─────────────────────────────────────────────────────────────
def ema(values: list[float], period: int) -> list[float]:
    """EMA standard, amorcage par SMA sur les `period` premieres valeurs."""
    if not values:
        return []
    k = 2.0 / (period + 1.0)
    out: list[float] = []
    seed = values[:period]
    if len(seed) < period:
        # historique insuffisant : on degrade en SMA des valeurs disponibles
        return [sum(values[: i + 1]) / (i + 1) for i in range(len(values))]
    prev = sum(seed) / period
    out.append(prev)
    for v in values[period:]:
        prev = v * k + prev * (1 - k)
        out.append(prev)
    return out


def rsi(values: list[float], period: int = 14) -> list[float]:
    """RSI de Wilder."""
    if len(values) < period + 1:
        return []
    gains, losses = [], []
    for i in range(1, len(values)):
        d = values[i] - values[i - 1]
        gains.append(max(d, 0.0))
        losses.append(max(-d, 0.0))
    ag = sum(gains[:period]) / period
    al = sum(losses[:period]) / period
    out = [100.0 if al == 0 else 100.0 - (100.0 / (1.0 + ag / al))]
    for i in range(period, len(gains)):
        ag = (ag * (period - 1) + gains[i]) / period
        al = (al * (period - 1) + losses[i]) / period
        out.append(100.0 if al == 0 else 100.0 - (100.0 / (1.0 + ag / al)))
    return out


# ── Signaux ─────────────────────────────────────────────────────────────────
def _signal(action: str, reason: str, **extra) -> dict:
    s = {"action": action, "reason": reason}
    s.update(extra)
    return s


def ema_cross(closes: list[float], fast: int, slow: int,
              allow_reentry: bool = True) -> dict:
    """Tendance EMA fast/slow.

    Le signal est un ETAT, pas un evenement ponctuel : si EMA_fast > EMA_slow,
    l'etat est « buy ». Un simple croisement ne se produit qu'UNE fois par
    tendance : avec une logique d'evenement pur, le bot_STOPPERAIT de trader
    apres son premier trade dans une tendance (plus de croisement a venir).
    L'etat permet la RE-ENTREE apres un SL/TP (le bot refuse juste d'empiler
    une position si le symbole est deja ouvert).
    """
    if len(closes) < slow + 3:
        return _signal("none", f"historique insuffisant ({len(closes)} barres, {slow}+3 requis)")
    ef = ema(closes, fast)
    es = ema(closes, slow)
    if len(ef) < 2 or len(es) < 2:
        return _signal("none", "EMA non calculable")
    d_now = ef[-1] - es[-1]
    d_prev = ef[-2] - es[-2]
    info = {"fast": round(ef[-1], 6), "slow": round(es[-1], 6),
            "spread": round(d_now, 8), "prev_spread": round(d_prev, 8)}
    if d_now > 0:
        if d_prev <= 0:
            return _signal("buy", f"EMA{fast} croise au-dessus de EMA{slow}", **info)
        if allow_reentry:
            return _signal("buy", f"tendance haussiere maintenue (EMA{fast} > EMA{slow}) — re-entree",
                           **info)
        return _signal("none", "tendance haussiere mais re-entree desactivee", **info)
    if d_now < 0:
        if d_prev >= 0:
            return _signal("sell", f"EMA{fast} croise sous EMA{slow}", **info)
        if allow_reentry:
            return _signal("sell", f"tendance baissiere maintenue (EMA{fast} < EMA{slow}) — re-entree",
                           **info)
        return _signal("none", "tendance baissiere mais re-entree desactivee", **info)
    return _signal("none", f"EMA{fast} et EMA{slow} confondues", **info)


def rsi_reversion(closes: list[float], period: int = 14, oversold: float = 30.0,
                  overbought: float = 70.0, allow_reentry: bool = True) -> dict:
    """Retour a la moyenne : etat « survente » => buy, « surachat » => sell."""
    if len(closes) < period + 3:
        return _signal("none", f"historique insuffisant pour RSI{period}")
    r = rsi(closes, period)
    if len(r) < 2:
        return _signal("none", "RSI non calculable")
    now, prev = r[-1], r[-2]
    info = {"rsi": round(now, 2), "prev_rsi": round(prev, 2),
            "oversold": oversold, "overbought": overbought}
    if now < oversold:
        if prev >= oversold:
            return _signal("buy", f"RSI entre en survente ({now:.1f})", **info)
        if allow_reentry:
            return _signal("buy", f"toujours en survente (RSI {now:.1f}) — re-entree", **info)
        return _signal("none", "survente mais re-entree desactivee", **info)
    if now > overbought:
        if prev <= overbought:
            return _signal("sell", f"RSI entre en surachat ({now:.1f})", **info)
        if allow_reentry:
            return _signal("sell", f"toujours en surachat (RSI {now:.1f}) — re-entree", **info)
        return _signal("none", "surachat mais re-entree desactivee", **info)
    return _signal("none", f"RSI neutre ({now:.1f})", **info)


def breakout(closes: list[float], highs: list[float], lows: list[float],
             lookback: int = 20, allow_reentry: bool = True) -> dict:
    """Cassure du plus haut (ou plus bas) des `lookback` barres precedentes.
    Etat : le dernier close reste au-dessus du plus haut precedent => buy."""
    n = lookback + 1
    if len(closes) < n + 1:
        return _signal("none", f"historique insuffisant pour breakout({lookback})")
    last_c = closes[-1]
    prev_hi = max(highs[-n - 1: -1])
    prev_lo = min(lows[-n - 1: -1])
    info = {"close": last_c, "prev_high": prev_hi, "prev_low": prev_lo, "lookback": lookback}
    if last_c > prev_hi:
        return _signal("buy", f"au-dessus du plus haut precedent ({prev_hi:.6f})", **info)
    if last_c < prev_lo:
        return _signal("sell", f"sous le plus bas precedent ({prev_lo:.6f})", **info)
    return _signal("none", "pas de cassure", **info)


# ── Dispatcher ──────────────────────────────────────────────────────────────
def evaluate(strategy: dict, bars: list[dict]) -> dict:
    """bars : liste de dicts {t,o,h,l,c,v} ORDREES du plus ancien au plus recent
    (la barre EN COURS, incomplete, doit etre EXCLUE par l'appelant)."""
    name = (strategy or {}).get("name", "ema_cross")
    reentry = bool(strategy.get("allow_reentry", True))
    closes = [b["c"] for b in bars if b.get("c") is not None]
    if len(closes) < 3:
        return _signal("none", "pas assez de barres")

    if name == "ema_cross":
        fast = int(strategy.get("fast", 9))
        slow = int(strategy.get("slow", 21))
        if fast <= 0 or slow <= 0 or fast >= slow:
            return _signal("none", f"parametres EMA invalides (fast={fast}, slow={slow})")
        return ema_cross(closes, fast, slow, allow_reentry=reentry)

    if name == "rsi_reversion":
        return rsi_reversion(
            closes,
            period=int(strategy.get("period", 14)),
            oversold=float(strategy.get("oversold", 30.0)),
            overbought=float(strategy.get("overbought", 70.0)),
            allow_reentry=reentry,
        )

    if name == "breakout":
        highs = [b.get("h") for b in bars if b.get("h") is not None]
        lows = [b.get("l") for b in bars if b.get("l") is not None]
        if len(highs) != len(closes) or len(lows) != len(closes):
            return _signal("none", "donnees OHLC incompletes")
        return breakout(closes, highs, lows, lookback=int(strategy.get("lookback", 20)),
                        allow_reentry=reentry)

    return _signal("none", f"strategie inconnue : {name}")


def validate_strategy(strategy: dict) -> dict:
    """Validation stricte du bloc 'strategy' de bot_config.set."""
    if not isinstance(strategy, dict):
        raise ValueError("strategy doit etre un objet")
    name = strategy.get("name")
    if name not in STRATEGY_NAMES:
        raise ValueError(f"strategy.name inconnu : {name!r} (autorise : {', '.join(STRATEGY_NAMES)})")
    tf = strategy.get("timeframe")
    if tf not in TIMEFRAMES:
        raise ValueError(f"strategy.timeframe invalide : {tf!r} (autorise : {', '.join(TIMEFRAMES)})")
    if name == "ema_cross":
        fast, slow = strategy.get("fast"), strategy.get("slow")
        for v, k in ((fast, "fast"), (slow, "slow")):
            if not isinstance(v, int) or isinstance(v, bool) or v < 2 or v > 200:
                raise ValueError(f"strategy.{k} invalide : {v!r} (entier 2..200)")
        if fast >= slow:
            raise ValueError(f"strategy.fast ({fast}) doit etre < strategy.slow ({slow})")
    if name == "rsi_reversion":
        p = strategy.get("period", 14)
        if not isinstance(p, int) or isinstance(p, bool) or p < 2 or p > 50:
            raise ValueError(f"strategy.period invalide : {p!r} (entier 2..50)")
        os_, ob = float(strategy.get("oversold", 30.0)), float(strategy.get("overbought", 70.0))
        if not (0 < os_ < ob < 100):
            raise ValueError(f"strategy.oversold/overbought invalides : {os_}/{ob}")
    if name == "breakout":
        lb = strategy.get("lookback", 20)
        if not isinstance(lb, int) or isinstance(lb, bool) or lb < 5 or lb > 200:
            raise ValueError(f"strategy.lookback invalide : {lb!r} (entier 5..200)")
    return strategy
