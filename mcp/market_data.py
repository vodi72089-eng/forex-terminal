"""
Forex Terminal — serveur MCP "market-data".

Donne a l'agent OpenCode un acces DIRECT aux APIs de marche publiques
(gratuites, sans cle) : taux de change, quotes, chandeliers OHLC, calendrier
economique, actualites Forex.

L'agent reste SANS ACCES a MetaTrader5 : ces outils sont de la DONNEE DE
CONTEXTE (read-only), pas de l'execution.

Lancement (stdio) :
    python -u mcp/market_data.py
"""
from __future__ import annotations

import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)
if os.path.join(_ROOT, "bot") not in sys.path:
    sys.path.insert(0, os.path.join(_ROOT, "bot"))

try:
    # mcp >= 2.0 : FastMCP a ete renomme MCPServer
    from mcp.server.mcpserver import MCPServer as _Server
except ImportError:  # pragma: no cover - mcp 1.x
    from mcp.server.fastmcp import FastMCP as _Server

import market_data  # noqa: E402  (bot/market_data.py)

mcp = _Server("market-data")


@mcp.tool()
def market_snapshot(symbols: str = "EURUSD,GBPUSD,USDJPY,XAUUSD") -> dict:
    """Vue d'ensemble du marche : quotes (prix + variation 24h), taux de change,
    calendrier economique de la semaine et dernieres actualites Forex.
    Utilise cet outil en premier pour avoir une vision globale."""
    syms = [s.strip().upper() for s in symbols.split(",") if s.strip()]
    return market_data.market_snapshot(syms, news_limit=8, calendar_limit=10)


@mcp.tool()
def fx_rates(base: str = "USD") -> dict:
    """Taux de change actuels (source : open.er-api.com, fallback Frankfurter/BCE).
    Retourne notamment les paires EURUSD, GBPUSD, USDJPY, AUDUSD, USDCAD, USDCHF."""
    return market_data.fx_rates(base.upper())


@mcp.tool()
def ecb_reference_rates() -> dict:
    """Taux de reference officiels de la Banque Centrale Europeenne (XML BCE)."""
    return market_data.ecb_reference_rates()


@mcp.tool()
def market_quote(symbol: str = "EURUSD") -> dict:
    """Prix actuel et variation 24h d'un symbole (EURUSD, GBPUSD, USDJPY, XAUUSD...)."""
    return market_data.quote(symbol.strip().upper())


@mcp.tool()
def ohlc_candles(symbol: str = "EURUSD", interval: str = "5m", range: str = "1d") -> dict:
    """Chandeliers OHLC (Yahoo Finance). interval: 1m,5m,15m,1h,1d. range: 1d,5d,1mo,3mo.
    Retourne une liste {t, o, h, l, c, v} — t en timestamp unix.
    Utilise-le pour calculer toi-meme la volatilite, les ranges, les moyennes."""
    return market_data.candles(symbol.strip().upper(), interval=interval, rng=range, limit=200)


@mcp.tool()
def economic_calendar(impact: str = "") -> dict:
    """Calendrier economique Forex de la semaine (ForexFactory).
    impact: 'High', 'Medium', 'Low' ou vide pour tout afficher.
    Les evenements 'High' justifient de RESSERRER les risques."""
    items = market_data.economic_calendar(impact.strip() or None)
    return {"count": len(items), "events": items[:40]}


@mcp.tool()
def market_news(query: str = "forex EURUSD Federal Reserve", limit: int = 15) -> dict:
    """Actualites Forex via Google News RSS (gratuit, sans cle).
    query: 'EURUSD', 'gold price', 'ECB rate decision', 'US jobs report'..."""
    items = market_data.news(query, limit=max(1, min(int(limit), 40)))
    return {"count": len(items), "query": query, "articles": items}


if __name__ == "__main__":
    mcp.run()
