"""
Forex Terminal — execution des ordres et controle du risque.

Les garde-fous sont appliques DANS LE CODE, independamment de bot_config.set :
ils ne peuvent pas etre contournes par l'IA. Les limites EFFECTIVES
(issue de la config, elle-meme bornee par HARD_LIMITS) sont injectees par
le bot a chaque appel.
"""
from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta

import MetaTrader5 as mt5

from config_protocol import HARD_LIMITS

log = logging.getLogger("bot.trader")

MAX_SPREAD_POINTS = 30  # refus d'ordre si spread trop large
MAGIC = 20261021


class Trader:
    """Donnees de marche / ordres / risques."""

    def __init__(self, conn, limits: dict | None = None):
        self.c = conn
        self.limits = dict(limits or {})
        self._pnl_cache: tuple[float, float] | None = None   # (ts, pct)

    # ── Limites effectives (config resserree par HARD_LIMITS) ────────────────
    def set_limits(self, limits: dict | None) -> None:
        self.limits = dict(limits or {})

    def _lim(self, key: str, fallback: float) -> float:
        v = self.limits.get(key)
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            return float(v)
        return float(fallback)

    # ── Donnees ─────────────────────────────────────────────────────────────
    def rates(self, symbol: str, tf=mt5.TIMEFRAME_M5, n: int = 300):
        """Barres brutes MT5. Index 0 = barre EN COURS (incomplete)."""
        self.c.ensure()
        return mt5.copy_rates_from_pos(symbol, tf, 0, n)

    def closed_bars(self, symbol: str, tf=mt5.TIMEFRAME_M5, n: int = 300) -> list[dict]:
        """Barres CLOSES uniquement, de la plus ancienne a la plus recente."""
        raw = self.rates(symbol, tf, n + 1)
        if raw is None or len(raw) < 2:
            return []
        out = []
        for b in raw[1:]:  # on exclut la barre 0 (en formation)
            out.append({
                "t": int(b["time"]),
                "o": float(b["open"]), "h": float(b["high"]),
                "l": float(b["low"]), "c": float(b["close"]),
                "v": float(b["tick_volume"]),
            })
        return out

    def positions(self, symbol: str | None = None):
        self.c.ensure()
        pos = mt5.positions_get(symbol=symbol) if symbol else mt5.positions_get()
        return list(pos or [])

    def symbol_has_position(self, symbol: str) -> bool:
        return len(self.positions(symbol)) > 0

    # ── Risque ──────────────────────────────────────────────────────────────
    def realized_pnl_today(self) -> float:
        """PnL REALISE du jour (tous les deals de la journee : profit +
        commission + swap). Inclut les trades fermes ET ceux encore ouverts."""
        acc = mt5.account_info()
        if acc is None:
            return 0.0
        now = datetime.now()
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        try:
            deals = mt5.history_deals_get(start, now + timedelta(minutes=1))
        except Exception as e:
            log.warning("history_deals_get : %s", e)
            return 0.0
        total = 0.0
        for d in (deals or []):
            total += float(d.profit) + float(d.commission) + float(d.swap)
        return total

    def floating_pnl(self) -> float:
        return sum(float(p.profit) + float(p.swap) for p in self.positions())

    def daily_pnl_pct(self) -> float:
        """PnL du jour (realise + flottant) en % du BALANCE.
        Le kill-switch doit reacting aux pertes REALISEES, pas seulement au
        flottant des positions encore ouvertes.
        Cache 2 s : history_deals_get est appele 1x/seconde par la boucle."""
        now = time.time()
        if self._pnl_cache and now - self._pnl_cache[0] < 2.0:
            return self._pnl_cache[1]
        acc = mt5.account_info()
        if acc is None:
            return 0.0
        base = float(acc.balance) or 1e-9
        total = self.realized_pnl_today() + self.floating_pnl()
        pct = 100.0 * total / base
        self._pnl_cache = (now, pct)
        return pct

    def kill_switch_active(self) -> bool:
        """Le kill-switch utilise la limite EFFECTIVE (config resserree)."""
        limit = self._lim("max_daily_loss_pct", HARD_LIMITS["max_daily_loss_pct"][1])
        return self.daily_pnl_pct() <= -abs(limit)

    # ── Ordres ──────────────────────────────────────────────────────────────
    def _fill_mode(self, symbol: str, info) -> int:
        """Choisit un mode de remplissage accepte par le symbole
        (IOC n'est pas supporte partout)."""
        modes = []
        sym_modes = getattr(info, "filling_mode", 0) if info else 0
        for bit, mode in ((1, mt5.ORDER_FILLING_FOK),
                          (2, mt5.ORDER_FILLING_IOC),
                          (4, mt5.ORDER_FILLING_RETURN)):
            if sym_modes & bit:
                modes.append(mode)
        if not modes:
            modes = [mt5.ORDER_FILLING_IOC, mt5.ORDER_FILLING_FOK,
                     mt5.ORDER_FILLING_RETURN]
        return modes[0]

    def market_order(self, symbol: str, side: str, lot: float,
                     sl_pips: float, tp_pips: float) -> dict:
        # ── GUARDRAILS INFAILIBLES (code, pas config) ──
        max_lot = self._lim("max_lot", HARD_LIMITS["max_lot"][1])
        max_trades = int(self._lim("max_open_trades", HARD_LIMITS["max_open_trades"][1]))
        max_loss = self._lim("max_daily_loss_pct", HARD_LIMITS["max_daily_loss_pct"][1])
        min_sl = HARD_LIMITS["sl_pips"][0]
        min_tp = HARD_LIMITS["tp_pips"][0]

        lot = min(float(lot), max_lot)
        if lot < HARD_LIMITS["max_lot"][0]:
            return {"ok": False, "why": f"lot {lot} < minimum {HARD_LIMITS['max_lot'][0]}"}
        if len(self.positions()) >= max_trades:
            return {"ok": False, "why": f"max_open_trades atteint ({max_trades})"}
        if self.daily_pnl_pct() <= -abs(max_loss):
            return {"ok": False, "why": f"kill-switch : perte journaliere max ({max_loss}%)"}
        if float(sl_pips) < min_sl:
            return {"ok": False, "why": f"sl_pips {sl_pips} < minimum {min_sl}"}
        if float(tp_pips) < min_tp:
            return {"ok": False, "why": f"tp_pips {tp_pips} < minimum {min_tp}"}

        tick = mt5.symbol_info_tick(symbol)
        info = mt5.symbol_info(symbol)
        if tick is None or info is None or info.point == 0:
            return {"ok": False, "why": f"symbole {symbol} indisponible"}
        if (tick.ask - tick.bid) / info.point > MAX_SPREAD_POINTS:
            return {"ok": False, "why": "spread trop large"}
        if not mt5.symbol_select(symbol, True):
            return {"ok": False, "why": f"symbole {symbol} non selectionnable"}

        buy = side == "buy"
        price = tick.ask if buy else tick.bid
        pip = info.point * (10 if info.digits in (3, 5) else 1)
        sl = price - sl_pips * pip if buy else price + sl_pips * pip
        tp = price + tp_pips * pip if buy else price - tp_pips * pip

        req = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": symbol,
            "volume": lot,
            "type": mt5.ORDER_TYPE_BUY if buy else mt5.ORDER_TYPE_SELL,
            "price": price,
            "sl": sl,
            "tp": tp,
            "deviation": 20,
            "magic": MAGIC,
            "comment": "opencode-bot",
            "type_filling": self._fill_mode(symbol, info),
        }
        res = mt5.order_send(req)
        if res is None:
            return {"ok": False, "why": f"order_send None : {mt5.last_error()}"}
        ok = res.retcode == mt5.TRADE_RETCODE_DONE
        if not ok:
            log.warning("ordre refuse : retcode=%s comment=%s", res.retcode, res.comment)
        return {
            "ok": ok,
            "retcode": res.retcode,
            "comment": res.comment,
            "order": res.order,
            "price": res.price,
            "sl": sl, "tp": tp, "lot": lot,
        }

    def close_all(self, symbol: str | None = None) -> int:
        """Fermeture de secours (action humaine uniquement, jamais par l'IA)."""
        closed = 0
        for p in self.positions(symbol):
            tick = mt5.symbol_info_tick(p.symbol)
            if tick is None:
                continue
            is_buy = p.type == mt5.POSITION_TYPE_BUY
            info = mt5.symbol_info(p.symbol)
            req = {
                "action": mt5.TRADE_ACTION_DEAL,
                "position": p.ticket,
                "symbol": p.symbol,
                "volume": p.volume,
                "type": mt5.ORDER_TYPE_SELL if is_buy else mt5.ORDER_TYPE_BUY,
                "price": tick.bid if is_buy else tick.ask,
                "deviation": 20,
                "magic": MAGIC,
                "comment": "close-all",
                "type_filling": self._fill_mode(p.symbol, info),
            }
            res = mt5.order_send(req)
            if res is not None and res.retcode == mt5.TRADE_RETCODE_DONE:
                closed += 1
        return closed
