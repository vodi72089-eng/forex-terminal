"""
Forex Terminal — bot MT5 embarque (module Python du projet Tauri/Next.js).

Lance par Tauri au demarrage de l'app :
    python -u bot/main.py
Expose une API locale FastAPI sur 127.0.0.1:8100 + une boucle temps reel :
  - reconnexion MT5 automatique (1s -> 60s)
  - lecture/validation/application de shared/bot_config.set si mtime change
    (INDEPENDANTE de la connexion MT5 : la config est toujours chargee)
  - moteur de strategies (bot/strategy.py) : signaux sur barres CLOSES
  - ecriture atomique de shared/bot_runtime.json (etat temps reel + journal)
"""
from __future__ import annotations

import json
import logging
import os
import sys
import threading
import time
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from fastapi import Body, FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
# uvicorn est importe ICI, pas dans __main__ : l'import de uvicorn monte
# l'extension httptools (~9 s) et, s'il se fait en concurrence avec le thread
# MT5 qui tient le GIL, il bloque le demarrage de l'API pendant 9 s.
import uvicorn  # noqa: E402

import paths
import market_data
import strategy as strategy_mod
from connector import MT5Connector
from config_protocol import (HARD_LIMITS, apply_policy, effective_limits,
                             load_if_changed, validate_full)
from runtime import log_add, log_tail, write_atomic
from trader import Trader

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("bot.main")

# ── Chemins ────────────────────────────────────────────────────────────────
SHARED = paths.ensure_shared()
paths.seed_shared_from_resources()
CFG_PATH = paths.path_in_shared("bot_config.set")
RT_PATH = paths.path_in_shared("bot_runtime.json")
CREDS_PATH = paths.path_in_shared("credentials.json")
LOG_PATH = paths.path_in_shared("bot.log")

log.info("shared dir = %s", SHARED)

# ── Identifiants ───────────────────────────────────────────────────────────
def _load_creds() -> dict:
    """Identifiants : variables d'env prioritaire, sinon shared/credentials.json."""
    creds = {}
    try:
        with open(CREDS_PATH, "r", encoding="utf-8") as f:
            creds = json.load(f)
    except Exception as e:
        log.warning("credentials.json illisible (%s) — variables d'env attendues", e)
    try:
        login = int(os.environ.get("MT5_LOGIN") or creds.get("login") or 0)
    except (TypeError, ValueError):
        login = 0
    return {
        "login": login,
        "password": os.environ.get("MT5_PASSWORD") or creds.get("password", ""),
        "server": os.environ.get("MT5_SERVER") or creds.get("server", ""),
        "token": os.environ.get("BOT_TOKEN") or creds.get("bot_token") or "dev-token-local",
    }


CREDS = _load_creds()
conn = MT5Connector(login=CREDS["login"], password=CREDS["password"], server=CREDS["server"])
trader = Trader(conn)

cfg: dict | None = None
cfg_mtime = 0.0
cfg_error: str | None = None
last_signal: dict = {}          # symbol -> {"bar_ts": int, "action": str}
last_order_ts: float = 0.0
COOLDOWN_S = 60.0

app = FastAPI(title="forex-terminal-bot", docs_url=None, redoc_url=None)

# ── CORS : le dashboard vit dans un WebView Tauri (origine tauri.localhost)
# Sans ces headers, le navigateur BLOQUE la reponse et le dashboard reste
# vide. Le bot n'ecoute QUE sur 127.0.0.1 : n'importe quel process local
# peut deja l'atteindre sans navigateur, donc CORS n'est pas une barriere de
# securite ici — les endpoints mutateurs sont proteges par le token.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
    expose_headers=["*"],
)


def _auth(x_bot_token: str):
    if x_bot_token != CREDS["token"]:
        log_add("WARN", "requete refusee : token invalide", "api")
        raise HTTPException(401, "unauthorized")


def _persist(cfg: dict) -> None:
    """Ecrit la config appliquee dans shared/bot_config.set.

    Sans cela, une config poussee par le dashboard (Activer/Desactiver) ou
    par l'IA ne survit PAS au redemarrage du bot : le fichier reste la
    version d'origine et le bot recharge l'ancienne config au demarrage."""
    global cfg_mtime
    payload = dict(cfg)
    payload["version"] = int(payload.get("version", 1))
    raw = json.dumps(payload, indent=2, ensure_ascii=False) + "\n"
    try:
        with open(CFG_PATH, "r", encoding="utf-8") as f:
            if f.read() == raw:
                return  # deja a jour
    except Exception:
        pass
    tmp = CFG_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(raw)
    os.replace(tmp, CFG_PATH)
    cfg_mtime = os.path.getmtime(CFG_PATH)


def apply_config(raw: str, persist: bool = True):
    """Le fichier ENTIER est valide puis applique. Tout defaut => rejet total.
    Renvoie la config effective. Lève une exception en cas de rejet."""
    global cfg, cfg_error
    data = validate_full(raw)
    new_cfg = apply_policy(data, cfg)
    cfg = new_cfg
    cfg_error = None
    trader.set_limits(effective_limits(cfg))
    log_add("INFO", f"bot_config.set applique : version={cfg['version']} "
                     f"enabled={cfg['enabled']} strategy={cfg['strategy'].get('name')} "
                     f"risk={ {k: round(float(v), 4) for k, v in cfg['risk'].items()} }", "config")
    if persist:
        try:
            _persist(cfg)
        except Exception as e:
            log_add("WARN", f"config non persistee : {e}", "config")
            log.warning("config non persistee : %s", e)
    return cfg


# ── Moteur de strategies ───────────────────────────────────────────────────
def _tf_constant(tf: str):
    import MetaTrader5 as mt5
    return {
        "M1": mt5.TIMEFRAME_M1, "M5": mt5.TIMEFRAME_M5, "M15": mt5.TIMEFRAME_M15,
        "M30": mt5.TIMEFRAME_M30, "H1": mt5.TIMEFRAME_H1, "H4": mt5.TIMEFRAME_H4,
        "D1": mt5.TIMEFRAME_D1,
    }.get(tf, mt5.TIMEFRAME_M5)


def run_strategies():
    """Boucle de signal : 1 evaluation par BARRE CLOSE (pas par tick).
    Un signal n'est declenche qu'une seule fois par barre, et jamais si le
    bot est desactive, si le kill-switch est actif, ou si un ordre vient
    d'etre envoye (cooldown)."""
    global last_order_ts
    if not cfg or not cfg.get("enabled"):
        return
    if trader.kill_switch_active():
        return
    if time.time() - last_order_ts < COOLDOWN_S:
        return

    st = cfg["strategy"]
    tf = st.get("timeframe", "M5")
    risk = cfg["risk"]

    for symbol in cfg.get("symbols", []):
        try:
            if trader.symbol_has_position(symbol):
                continue
            bars = trader.closed_bars(symbol, _tf_constant(tf), n=300)
            if len(bars) < 5:
                continue
            bar_ts = bars[-1]["t"]
            prev = last_signal.get(symbol)
            if prev and prev.get("bar_ts") == bar_ts:
                continue  # deja traite cette barre

            sig = strategy_mod.evaluate(st, bars)
            last_signal[symbol] = {"bar_ts": bar_ts, "action": sig["action"]}

            if sig["action"] == "none":
                log_add("DEBUG", f"{symbol} {tf} : {sig['reason']}", "strategy")
                continue

            log_add("INFO", f"{symbol} {tf} : SIGNAL {sig['action'].upper()} — {sig['reason']}", "strategy")
            res = trader.market_order(
                symbol, sig["action"],
                float(risk["max_lot"]), float(risk["sl_pips"]), float(risk["tp_pips"]),
            )
            if res.get("ok"):
                last_order_ts = time.time()
                log_add("INFO", f"{symbol} ordre {sig['action']} @ {res.get('price')} "
                                f"lot={res.get('lot')} sl={res.get('sl')} tp={res.get('tp')}", "order")
            else:
                log_add("WARN", f"{symbol} ordre REFUSE : {res.get('why')}", "order")
        except Exception as e:
            log.exception("strategie %s : %s", symbol, e)
            log_add("ERROR", f"strategie {symbol} : {e}", "strategy")


def loop():
    """Boucle principale (1 Hz). La CONFIG est chargee meme si MT5 est hors
    ligne : seule l'execution des ordres depend de la connexion MT5."""
    global cfg_mtime, cfg_error

    threading.Thread(target=_connect_loop, daemon=True).start()

    while True:
        try:
            # 1. Config (independante de MT5)
            raw, cfg_mtime = load_if_changed(CFG_PATH, cfg_mtime)
            if raw is not None:
                try:
                    apply_config(raw)
                except Exception as e:
                    cfg_error = str(e)
                    log_add("ERROR", f"bot_config.set REJETE (fichier entier ignore) : {e}", "config")
                    log.error("bot_config.set REJETE : %s", e)

            # 2. Execution (seulement si MT5 connecte)
            if conn.connected:
                try:
                    run_strategies()
                except Exception as e:
                    log.exception("strategie : %s", e)

            # 3. Etat temps reel
            write_runtime()
        except Exception as e:
            log.exception("boucle : %s", e)
        time.sleep(1)


def _connect_loop():
    """Connexion MT5 persistante (ne bloque pas la boucle principale).

    ATTENTION : le sleep est INDISPENSABLE. Sans lui, quand la connexion est
    etablie, cette boucle tourne en boucle serree et MONOPOLISE le GIL :
    le thread principal (serveur uvicorn) est affame et l'API met ~9 s a
    repondre, le CPU est a 100%."""
    while True:
        try:
            if not conn.connected:
                conn.connect()
        except Exception as e:
            log.exception("connexion : %s", e)
        time.sleep(1)


def write_runtime():
    """Ecrit l'etat temps reel (consomme par le dashboard ET par l'agent)."""
    acc = None
    positions = []
    pnl = 0.0
    kill = False
    try:
        import MetaTrader5 as mt5
        if conn.connected:
            a = mt5.account_info()
            if a is not None:
                acc = {"login": a.login, "server": a.server,
                       "equity": a.equity, "balance": a.balance,
                       "currency": a.currency, "margin_free": a.margin_free}
            positions = [
                {"ticket": p.ticket, "symbol": p.symbol,
                 "side": "buy" if p.type == 0 else "sell",
                 "lot": p.volume, "profit": round(p.profit, 2),
                 "price_open": p.price_open, "sl": p.sl, "tp": p.tp,
                 "swap": round(p.swap, 2)}
                for p in trader.positions()
            ]
            pnl = round(trader.daily_pnl_pct(), 3)
            kill = trader.kill_switch_active()
    except Exception as e:
        log.warning("runtime : %s", e)

    write_atomic(RT_PATH, {
        "ts": time.time(),
        "updated_at": datetime.now().isoformat(timespec="seconds"),
        "connected": conn.connected,
        "account": acc,
        "positions": positions,
        "pnl_today_pct": pnl,
        "kill_switch": kill,
        "config_version": (cfg or {}).get("version"),
        "config_enabled": (cfg or {}).get("enabled", False),
        "strategy": (cfg or {}).get("strategy"),
        "risk": (cfg or {}).get("risk"),
        "limits": effective_limits(cfg),
        "last_error": cfg_error,
        "log": log_tail(40),
        "shared_dir": SHARED,
    })


# ── API ────────────────────────────────────────────────────────────────────
class OrderIn(BaseModel):
    symbol: str
    side: str
    lot: float
    sl_pips: float
    tp_pips: float


@app.get("/health")
def health():
    return {"ok": conn.connected, "config": bool(cfg), "shared": SHARED}


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


@app.get("/logs")
def logs():
    return log_tail(60)


@app.get("/opencode/port")
def opencode_port():
    """Port reellement utilise par le serveur opencode.
    Tauri le choisit dynamiquement (un port fixe peut etre occupe par un
    processus etranger) et l'ecrit dans shared/opencode.port."""
    return {"port": paths.read_oc_port()}


@app.get("/market/snapshot")
def market_snapshot(symbols: str | None = None, news_limit: int = 8):
    """Marche public (APIs gratuites sans cle) : quotes, taux, calendrier, actus."""
    syms = [s.strip().upper() for s in (symbols or "EURUSD,GBPUSD,USDJPY,XAUUSD").split(",") if s.strip()]
    return market_data.market_snapshot(syms, news_limit=news_limit)


@app.get("/market/quote")
def market_quote(symbol: str = "EURUSD"):
    return market_data.quote(symbol.upper())


@app.get("/market/candles")
def market_candles(symbol: str = "EURUSD", interval: str = "5m", rng: str = "1d"):
    return market_data.candles(symbol.upper(), interval=interval, rng=rng, limit=200)


@app.get("/market/calendar")
def market_calendar(impact: str | None = None):
    return market_data.economic_calendar(impact)


@app.get("/market/news")
def market_news(q: str = "forex EURUSD", limit: int = 15):
    return market_data.news(q, limit=limit)


@app.post("/order")
def order(o: OrderIn, x_bot_token: str = Header(default="")):
    _auth(x_bot_token)
    if cfg is None:
        raise HTTPException(409, "aucune configuration chargee : le bot refuse d'ordonner")
    if not cfg.get("enabled", False):
        raise HTTPException(409, "bot desactive par bot_config.set (enabled=false)")
    return trader.market_order(o.symbol, o.side, o.lot, o.sl_pips, o.tp_pips)


@app.post("/config/raw")
def config_raw(raw: str = Body(..., media_type="text/plain"),
               x_bot_token: str = Header(default="")):
    """Pont OpenCode : l'agent pousse le FICHIER ENTIER ici.
    Validation complete avant application — rejet total si un seul defaut.

    NOTE technique : sans Body(...), FastAPI interprete `raw: str` comme un
    QUERY PARAM et l'endpoint repondait toujours 422."""
    global cfg_error
    _auth(x_bot_token)
    try:
        c = apply_config(raw)
    except Exception as e:
        cfg_error = str(e)
        log_add("ERROR", f"config/raw rejete : {e}", "api")
        log.error("config/raw rejete : %s", e)
        raise HTTPException(422, f"config rejete : {e}")
    return {"applied": True, "version": c["version"], "risk": c["risk"],
            "strategy": c["strategy"], "enabled": c["enabled"]}


@app.post("/close-all")
def close_all(x_bot_token: str = Header(default="")):
    """Bouton d'urgence humain — jamais accessible a l'IA."""
    _auth(x_bot_token)
    n = trader.close_all()
    log_add("WARN", f"CLOSE ALL execute par l'utilisateur : {n} position(s) fermee(s)", "order")
    return {"closed": n}


if __name__ == "__main__":
    os.makedirs(SHARED, exist_ok=True)
    # fichier de log persistant (les stdout du sidecar sont jetes par Tauri)
    try:
        fh = logging.FileHandler(LOG_PATH, encoding="utf-8")
        fh.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
        logging.getLogger().addHandler(fh)
    except Exception:
        pass
    threading.Thread(target=loop, daemon=True).start()
    # Le port est choisi par Tauri (un port fixe peut etre occupe par un
    # processus etranger) et ecrit dans shared/bot.port.
    BOT_PORT = paths.read_port_file("bot.port", 8100)
    log.info("API bot sur 127.0.0.1:%d", BOT_PORT)
    uvicorn.run(app, host="127.0.0.1", port=BOT_PORT, log_level="warning")
