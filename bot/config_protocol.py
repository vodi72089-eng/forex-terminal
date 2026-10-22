"""
Forex Terminal â€” protocole de configuration.

PRINCIPE : le fichier est valide ENTIEREMENT ou REJETE EN TOTAL.
Jamais de mise a jour champ par champ (le bot rejette tout fichier partiel).

Garde-fous ABSOLUS (clamp-only) : l'agent ne peut QUE resserrer les limites,
jamais les desserrer. Ces bornes sont appliquees DANS LE CODE, independamment
de ce que contient bot_config.set.
"""
from __future__ import annotations

import json
import os
import re
import threading

from strategy import validate_strategy

LOCK = threading.Lock()

TOP_FIELDS = {
    "version": int,
    "enabled": bool,
    "symbols": list,
    "strategy": dict,
    "risk": dict,
    "issued_by": str,
    "issued_at": str,
}
RISK_FIELDS = ("max_lot", "max_open_trades", "max_daily_loss_pct", "sl_pips", "tp_pips")

# â”€â”€ Garde-fous ABSOLUS : (min, max). Inclus dans le clamp, non negociables. â”€â”€
HARD_LIMITS = {
    "max_lot": (0.01, 0.10),
    "max_open_trades": (1, 3),
    "max_daily_loss_pct": (0.5, 3.0),
    # SL/TP : sans borne, l'IA pouvait mettre sl_pips=0.001 (stop loss inexistant)
    "sl_pips": (5.0, 500.0),
    "tp_pips": (5.0, 1000.0),
}

MAX_SYMBOLS = 5
_ALLOWED_SYMBOLS = {
    "EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCAD", "USDCHF",
    "NZDUSD", "EURGBP", "EURJPY", "GBPJPY", "XAUUSD", "BTCUSD",
}

def strip_code_fence(raw: str) -> str:
    """Retire les fences markdown (```json ... ```) d'une reponse LLM.
    Les modeles de chat enveloppent tres souvent le JSON, ce qui cassait
    json.loads() et donc la validation."""
    if not isinstance(raw, str):
        return ""
    s = raw.strip()
    if s.startswith("```"):
        nl = s.find("\n")
        s = s[nl + 1:] if nl != -1 else s
        idx = s.rfind("```")
        if idx != -1:
            s = s[:idx]
        s = s.strip()
    # dernier recours : extraire le premier objet JSON equilibre
    if not s.startswith("{"):
        m = re.search(r"\{.*\}", s, re.DOTALL)
        if m:
            s = m.group(0)
    return s


def validate_full(raw: str) -> dict:
    """Validation du FICHIER ENTIER (jamais champ par champ).
    Un seul defaut => exception => rejet total, l'ancienne config reste en vigueur."""
    if not isinstance(raw, str) or not raw.strip():
        raise ValueError("config vide")
    data = json.loads(strip_code_fence(raw))  # tronque/corrompu => exception => rejet
    if not isinstance(data, dict):
        raise ValueError("racine non-objet")
    for k, t in TOP_FIELDS.items():
        if k not in data:
            raise ValueError(f"champ racine manquant : {k}")
        v = data[k]
        if t is bool:
            if not isinstance(v, bool):
                raise ValueError(f"champ racine invalide : {k} (attendu bool)")
        elif not isinstance(v, t) or isinstance(v, bool):
            raise ValueError(f"champ racine invalide : {k} (attendu {t.__name__})")

    if data["version"] < 1:
        raise ValueError("version doit etre >= 1")

    risk = data["risk"]
    for k in RISK_FIELDS:
        v = risk.get(k)
        if not isinstance(v, (int, float)) or isinstance(v, bool) or v <= 0:
            raise ValueError(f"risk.{k} invalide (nombre > 0 attendu)")

    symbols = data["symbols"]
    if not symbols:
        raise ValueError("symbols vide")
    if len(symbols) > MAX_SYMBOLS:
        raise ValueError(f"symbols : {len(symbols)} > {MAX_SYMBOLS} maximum")
    for s in symbols:
        if not isinstance(s, str) or s.upper() not in _ALLOWED_SYMBOLS:
            raise ValueError(f"symbole non autorise : {s!r}")

    validate_strategy(data["strategy"])
    return data


def apply_policy(new_cfg: dict, current_cfg: dict | None) -> dict:
    """Borne les valeurs de risque par HARD_LIMITS et par la config en cours
    (clamp-only). Meme un agent compromis ne peut produire qu'une config PLUS
    stricte, jamais plus laxiste."""
    r = new_cfg["risk"]
    for k, (lo, hi) in HARD_LIMITS.items():
        val = min(max(float(r[k]), lo), hi)
        if current_cfg is not None:
            prev = current_cfg.get("risk", {}).get(k)
            if isinstance(prev, (int, float)) and not isinstance(prev, bool):
                val = min(val, float(prev))
        r[k] = val
    r["max_open_trades"] = int(r["max_open_trades"])
    return new_cfg


def effective_limits(cfg: dict | None) -> dict:
    """Limites de risque EFFECTIVES : config courante resserree par HARD_LIMITS.
    C'est ce dictionnaire que le bot doit utiliser pour TOUT controle."""
    out = {k: float(v[1]) for k, v in HARD_LIMITS.items()}
    out["max_open_trades"] = int(HARD_LIMITS["max_open_trades"][1])
    if cfg:
        r = cfg.get("risk", {})
        for k, (lo, hi) in HARD_LIMITS.items():
            v = r.get(k)
            if isinstance(v, (int, float)) and not isinstance(v, bool):
                out[k] = min(max(float(v), lo), hi)
        out["max_open_trades"] = int(out["max_open_trades"])
    return out


def load_if_changed(path: str, last_mtime: float):
    """Le bot relit le fichier periodiquement ; on ne valide que si mtime a change."""
    try:
        m = os.path.getmtime(path)
    except OSError:
        return None, last_mtime
    if m == last_mtime:
        return None, last_mtime
    with LOCK:
        try:
            with open(path, "r", encoding="utf-8-sig") as f:
                raw = f.read()
        except OSError:
            return None, last_mtime
    return raw, m
