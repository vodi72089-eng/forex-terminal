"""
Forex Terminal — bot MT5 embarque (module Python du projet Tauri/Next.js).

Lance par Tauri au demarrage de l'app :
    python -u bot/main.py
Expose une API locale FastAPI sur 127.0.0.1:8100 + une boucle temps reel :
  - reconnexion MT5 automatique (1s)
  - lecture/validation/application de shared/bot_config.set si mtime change
  - ecriture atomique de shared/bot_runtime.json (etat temps reel)
"""
import json
import logging
import os
import sys
import threading
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel

from connector import MT5Connector
from trader import Trader
from config_protocol import validate_full, apply_policy, load_if_changed
from runtime import write_atomic

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("bot.main")

RUNTIME_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SHARED = os.path.join(RUNTIME_ROOT, "shared")
CFG_PATH = os.path.join(SHARED, "bot_config.set")
RT_PATH = os.path.join(SHARED, "bot_runtime.json")
CREDS_PATH = os.path.join(SHARED, "credentials.json")


def _load_creds() -> dict:
    """Identifiants : variables d'env prioritaire, sinon shared/credentials.json."""
    creds = {}
    try:
        with open(CREDS_PATH, "r", encoding="utf-8") as f:
            creds = json.load(f)
    except Exception:
        pass
    return {
        "login": int(os.environ.get("MT5_LOGIN") or creds.get("login") or 0),
        "password": os.environ.get("MT5_PASSWORD") or creds.get("password", ""),
        "server": os.environ.get("MT5_SERVER") or creds.get("server", ""),
        "token": os.environ.get("BOT_TOKEN") or creds.get("bot_token", "dev-token-local"),
    }


CREDS = _load_creds()
conn = MT5Connector(login=CREDS["login"], password=CREDS["password"], server=CREDS["server"])
trader = Trader(conn)
cfg: dict | None = None
cfg_mtime = 0.0

app = FastAPI(title="forex-terminal-bot", docs_url=None, redoc_url=None)


def _auth(x_bot_token: str):
    if x_bot_token != CREDS["token"]:
        raise HTTPException(401, "unauthorized")


def apply_config(raw: str):
    """Le fichier ENTIER est valide puis applique. Tout defaut => rejet total."""
    global cfg
    data = validate_full(raw)
    cfg = apply_policy(data, cfg)
    log.info("bot_config.set applique : version=%s enabled=%s", cfg["version"], cfg["enabled"])


def loop():
    global cfg_mtime
    conn.connect()
    while True:
        try:
            conn.ensure()
            raw, cfg_mtime = load_if_changed(CFG_PATH, cfg_mtime)
            if raw is not None:
                try:
                    apply_config(raw)
                except Exception as e:
                    log.error("bot_config.set REJETE (fichier entier ignore) : %s", e)
            acc = None
            import MetaTrader5 as mt5
            a = mt5.account_info()
            if a is not None:
                acc = {"login": a.login, "server": a.server,
                       "equity": a.equity, "balance": a.balance}
            write_atomic(RT_PATH, {
                "ts": time.time(),
                "connected": conn.connected,
                "account": acc,
                "positions": [
                    {"ticket": p.ticket, "symbol": p.symbol,
                     "side": "buy" if p.type == 0 else "sell",
                     "lot": p.volume, "profit": round(p.profit, 2),
                     "price_open": p.price_open}
                    for p in trader.positions()
                ],
                "pnl_today_pct": round(trader.daily_pnl_pct(), 3),
                "kill_switch": trader.kill_switch_active(),
                "config_version": (cfg or {}).get("version"),
                "config_enabled": (cfg or {}).get("enabled", False),
                "strategy": (cfg or {}).get("strategy"),
                "last_error": None,
            })
        except Exception as e:
            log.exception("boucle : %s", e)
        time.sleep(1)


class OrderIn(BaseModel):
    symbol: str
    side: str
    lot: float
    sl_pips: float
    tp_pips: float


@app.get("/health")
def health():
    return {"ok": conn.connected}


@app.get("/runtime")
def runtime():
    try:
        with open(RT_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"ts": 0, "connected": False}


@app.get("/positions")
def positions():
    return [
        {"ticket": p.ticket, "symbol": p.symbol, "lot": p.volume,
         "profit": round(p.profit, 2)}
        for p in trader.positions()
    ]


@app.get("/config")
def config():
    return cfg or {"version": None}


@app.post("/order")
def order(o: OrderIn, x_bot_token: str = Header(default="")):
    _auth(x_bot_token)
    if cfg is not None and not cfg.get("enabled", False):
        raise HTTPException(409, "bot desactive par bot_config.set (enabled=false)")
    return trader.market_order(o.symbol, o.side, o.lot, o.sl_pips, o.tp_pips)


@app.post("/config/raw")
def config_raw(raw: str, x_bot_token: str = Header(default="")):
    """Pont OpenCode : l'agent pousse le FICHIER ENTIER ici.
    Validation complete avant application — rejet total si un seul defaut."""
    _auth(x_bot_token)
    apply_config(raw)
    return {"applied": True, "version": cfg["version"]}


@app.post("/close-all")
def close_all(x_bot_token: str = Header(default="")):
    """Bouton d'urgence humain — jamais accessible a l'IA."""
    _auth(x_bot_token)
    return {"closed": trader.close_all()}


if __name__ == "__main__":
    os.makedirs(SHARED, exist_ok=True)
    threading.Thread(target=loop, daemon=True).start()
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8100, log_level="warning")
