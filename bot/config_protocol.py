import json
import os
import threading

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

# Garde-fous ABSOLUS : clamp-only, l'agent ne peut QUE resserrer, jamais desserrer.
HARD_LIMITS = {
    "max_lot": (0.01, 0.10),
    "max_open_trades": (1, 3),
    "max_daily_loss_pct": (0.5, 3.0),
}


def validate_full(raw: str) -> dict:
    """Validation du FICHIER ENTIER (jamais champ par champ).
    Un seul defaut => exception => rejet total, l'ancienne config reste en vigueur."""
    data = json.loads(raw)  # fichier tronque/corrompu => exception => rejet
    if not isinstance(data, dict):
        raise ValueError("racine non-objet")
    for k, t in TOP_FIELDS.items():
        if k not in data:
            raise ValueError(f"champ racine manquant : {k}")
        if not isinstance(data[k], t):
            raise ValueError(f"champ racine invalide : {k} (attendu {t.__name__})")
    risk = data["risk"]
    for k in RISK_FIELDS:
        v = risk.get(k)
        if not isinstance(v, (int, float)) or isinstance(v, bool) or v <= 0:
            raise ValueError(f"risk.{k} invalide")
    if not data["symbols"]:
        raise ValueError("symbols vide")
    return data


def apply_policy(new_cfg: dict, current_cfg: dict | None) -> dict:
    """Borne les valeurs de risque par HARD_LIMITS et par la config en cours (clamp-only).
    Meme un agent compromis ne peut produire qu'une config PLUS stricte, jamais plus laxiste."""
    r = new_cfg["risk"]
    for k, (lo, hi) in HARD_LIMITS.items():
        val = min(max(float(r[k]), lo), hi)
        if current_cfg is not None:
            val = min(val, float(current_cfg["risk"][k]))
        r[k] = val
    r["max_open_trades"] = int(r["max_open_trades"])
    return new_cfg


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
            with open(path, "r", encoding="utf-8") as f:
                raw = f.read()
        except OSError:
            return None, last_mtime
    return raw, m
