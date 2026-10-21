import MetaTrader5 as mt5

from config_protocol import HARD_LIMITS

MAX_SPREAD_POINTS = 30  # refus d'ordre si spread trop large


class Trader:
    """Donnees de marche / ordres / risques.
    Les guardrails sont appliques DANS LE CODE, independamment de bot_config.set :
    ils ne peuvent pas etre contournes par l'IA."""

    def __init__(self, conn):
        self.c = conn

    def rates(self, symbol: str, tf=mt5.TIMEFRAME_M5, n: int = 200):
        self.c.ensure()
        return mt5.copy_rates_from_pos(symbol, tf, 0, n)

    def positions(self, symbol: str | None = None):
        self.c.ensure()
        pos = mt5.positions_get(symbol=symbol) if symbol else mt5.positions_get()
        return list(pos or [])

    def daily_pnl_pct(self) -> float:
        acc = mt5.account_info()
        if acc is None:
            return 0.0
        total = sum(p.profit for p in self.positions())
        return 100.0 * total / max(acc.equity, 1e-9)

    def kill_switch_active(self) -> bool:
        return self.daily_pnl_pct() <= -3.0

    def market_order(self, symbol: str, side: str, lot: float,
                     sl_pips: float, tp_pips: float) -> dict:
        # ── GUARDRAILS INFAILIBLES (code, pas config) ──
        lot = min(lot, HARD_LIMITS["max_lot"][1])
        if len(self.positions()) >= HARD_LIMITS["max_open_trades"][1]:
            return {"ok": False, "why": "max_open_trades atteint"}
        if self.daily_pnl_pct() <= -HARD_LIMITS["max_daily_loss_pct"][1]:
            return {"ok": False, "why": "kill-switch : perte journaliere max"}
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
            "magic": 20261021,
            "comment": "opencode-bot",
            "type_filling": mt5.ORDER_FILLING_IOC,
        }
        res = mt5.order_send(req)
        if res is None:
            return {"ok": False, "why": f"order_send None : {mt5.last_error()}"}
        return {
            "ok": res.retcode == mt5.TRADE_RETCODE_DONE,
            "retcode": res.retcode,
            "comment": res.comment,
            "order": res.order,
            "price": res.price,
        }

    def close_all(self, symbol: str | None = None) -> int:
        """Fermeture de secours (utilisee manuellement, jamais par l'IA)."""
        closed = 0
        for p in self.positions(symbol):
            tick = mt5.symbol_info_tick(p.symbol)
            if tick is None:
                continue
            is_buy = p.type == mt5.POSITION_TYPE_BUY
            req = {
                "action": mt5.TRADE_ACTION_DEAL,
                "position": p.ticket,
                "symbol": p.symbol,
                "volume": p.volume,
                "type": mt5.ORDER_TYPE_SELL if is_buy else mt5.ORDER_TYPE_BUY,
                "price": tick.bid if is_buy else tick.ask,
                "deviation": 20,
                "magic": 20261021,
                "comment": "close-all",
                "type_filling": mt5.ORDER_FILLING_IOC,
            }
            res = mt5.order_send(req)
            if res is not None and res.retcode == mt5.TRADE_RETCODE_DONE:
                closed += 1
        return closed
