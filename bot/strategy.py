"""
Forex Terminal — moteur de strategies.

CONTRAIT : ce module ne touche JAMAIS a MetaTrader5 et n'ouvre aucun ordre.
Il transforme des barres de marche + une config en une DECISION.
Le bot (main.py) est seul autorise a executer cette decision.

REGISTRE DYNAMIQUE
Les strategies sont des modules Python dans bot/strategies/*.py (incluses) et
dans %APPDATA%\\com.forex.terminal\\strategies\\*.py (les tiennes). Chaque
module expose :
    NAME        : identifiant unique
    DESCRIPTION : texte affiche dans le dashboard
    PARAMS      : {nom: {type, min, max, default, label}}
    evaluate(bars, params) -> {"action": "buy"|"sell"|"none", "reason": str, ...}

Pour ajouter une strategie : depose ton .py dans le dossier strategies, il
apparait automatiquement dans l'interface (redemarre le bot).
"""
from __future__ import annotations

import importlib.util
import logging
import os
import sys

log = logging.getLogger("bot.strategy")

# ── Indicateurs (partages) ─────────────────────────────────────────────────
def ema(values: list[float], period: int) -> list[float]:
    """EMA standard, amorcage par SMA sur les `period` premieres valeurs."""
    if not values:
        return []
    k = 2.0 / (period + 1.0)
    seed = values[:period]
    if len(seed) < period:
        return [sum(values[: i + 1]) / (i + 1) for i in range(len(values))]
    prev = sum(seed) / period
    out = [prev]
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


# ── Registre ───────────────────────────────────────────────────────────────
_BUILTIN_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "strategies")
_MODULES: dict[str, object] = {}


def user_strategies_dir() -> str:
    """Dossier des strategies perso (%APPDATA%)."""
    base = os.environ.get("APPDATA") or os.path.expanduser("~")
    return os.path.join(base, "com.forex.terminal", "strategies")


def _load_module(path: str, name: str):
    try:
        spec = importlib.util.spec_from_file_location(f"strategy_{name}", path)
        if spec is None or spec.loader is None:
            return None
        mod = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = mod
        spec.loader.exec_module(mod)
        if not hasattr(mod, "evaluate") or not hasattr(mod, "NAME"):
            log.warning("strategie %s ignoree (NAME/evaluate manquant)", name)
            return None
        return mod
    except Exception as e:
        log.warning("strategie %s illisible : %s", name, e)
        return None


def _scan() -> None:
    """(re)charge le registre depuis les deux dossiers de strategies."""
    _MODULES.clear()
    for d in (_BUILTIN_DIR, user_strategies_dir()):
        if not os.path.isdir(d):
            continue
        for fn in sorted(os.listdir(d)):
            if not fn.endswith(".py") or fn.startswith("_"):
                continue
            name = fn[:-3]
            mod = _load_module(os.path.join(d, fn), name)
            if mod is None:
                continue
            mod.BUILTIN = (d == _BUILTIN_DIR)
            _MODULES[mod.NAME] = mod
    log.info("strategies chargees : %s", ", ".join(sorted(_MODULES)) or "aucune")


_scan()


def reload() -> list[str]:
    """Recharge le registre (apres avoir depose une nouvelle strategie)."""
    _scan()
    return sorted(_MODULES)


def available() -> list[dict]:
    """Liste des strategies disponibles, avec le schema de leurs parametres."""
    out = []
    for name, mod in sorted(_MODULES.items()):
        params = dict(getattr(mod, "PARAMS", {}) or {})
        params["allow_reentry"] = {
            "type": "bool", "default": True,
            "label": "Re-entree (apres SL/TP)",
        }
        out.append({
            "name": name,
            "description": getattr(mod, "DESCRIPTION", ""),
            "builtin": bool(getattr(mod, "BUILTIN", False)),
            "params": params,
        })
    return out


def get(name: str):
    return _MODULES.get(name)


def validate_strategy(strategy: dict) -> dict:
    """Validation stricte du bloc 'strategy' de bot_config.set."""
    if not isinstance(strategy, dict):
        raise ValueError("strategy doit etre un objet")
    name = strategy.get("name")
    mod = get(name)
    if mod is None:
        raise ValueError(
            f"strategy.name inconnu : {name!r} "
            f"(disponibles : {', '.join(sorted(_MODULES)) or 'aucune'})"
        )
    tf = strategy.get("timeframe")
    if tf not in TIMEFRAMES:
        raise ValueError(f"strategy.timeframe invalide : {tf!r} (autorise : {', '.join(TIMEFRAMES)})")

    schema = dict(getattr(mod, "PARAMS", {}) or {})
    for key, spec in schema.items():
        if key not in strategy:
            raise ValueError(f"strategy.{key} manquant")
        v = strategy[key]
        t = spec.get("type", "float")
        if t == "int":
            if not isinstance(v, int) or isinstance(v, bool):
                raise ValueError(f"strategy.{key} doit etre un entier")
        elif t == "float":
            if not isinstance(v, (int, float)) or isinstance(v, bool):
                raise ValueError(f"strategy.{key} doit etre un nombre")
        if "min" in spec and v < spec["min"]:
            raise ValueError(f"strategy.{key} ({v}) < minimum {spec['min']}")
        if "max" in spec and v > spec["max"]:
            raise ValueError(f"strategy.{key} ({v}) > maximum {spec['max']}")
    # coherence des seuils (RSI)
    if "oversold" in schema and "overbought" in schema:
        if not (0 < float(strategy["oversold"]) < float(strategy["overbought"]) < 100):
            raise ValueError("strategy.oversold doit etre < strategy.overbought")
    if "fast" in schema and "slow" in schema:
        if int(strategy["fast"]) >= int(strategy["slow"]):
            raise ValueError("strategy.fast doit etre < strategy.slow")
    return strategy


def evaluate(strategy: dict, bars: list[dict]) -> dict:
    """Evalue la config 'strategy' sur les barres CLOSES fournies."""
    name = (strategy or {}).get("name")
    mod = get(name)
    if mod is None:
        return {"action": "none", "reason": f"strategie inconnue : {name}"}
    params = {k: v for k, v in (strategy or {}).items()
              if k not in ("name", "timeframe", "allow_reentry")}
    params["allow_reentry"] = bool((strategy or {}).get("allow_reentry", True))
    try:
        return mod.evaluate(bars, params)
    except Exception as e:
        log.exception("strategie %s : %s", name, e)
        return {"action": "none", "reason": f"erreur de la strategie : {e}"}


TIMEFRAMES = {
    "M1": 1, "M5": 5, "M15": 15, "M30": 30,
    "H1": 60, "H4": 240, "D1": 1440,
}
