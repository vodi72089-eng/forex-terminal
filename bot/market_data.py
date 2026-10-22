"""
Forex Terminal — couche donnees de marche (APIs PUBLIQUES, sans cle).

Sources (toutes gratuites, aucune inscription) :
  - Frankfurter      https://api.frankfurter.app        taux de reference BCE
  - open.er-api.com  https://open.er-api.com/v6/       taux de change live
  - Yahoo Finance    query1.finance.yahoo.com/v8/      chandeliers OHLC + quote
  - ForexFactory     nfs.faireconomy.media/            calendrier economique
  - Google News RSS  news.google.com/rss/              Actualites Forex
  - BCE XML          eurofxref-daily.xml               taux officiels BCE

Aucune de ces APIs n'est un flux de tick MT5 : elles servent au CONTEXTE
(agent + dashboard). La decision d'execution reste au bot MT5.
"""
from __future__ import annotations

import csv
import io
import json
import logging
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

log = logging.getLogger("bot.market_data")

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) forex-terminal/0.1"
TIMEOUT = 15

# ── Symboles ────────────────────────────────────────────────────────────────
FOREX_SYMBOLS = [
    "EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCAD",
    "USDCHF", "NZDUSD", "EURGBP", "EURJPY", "GBPJPY", "XAUUSD",
]

# Mapping Yahoo Finance
YAHOO_MAP = {
    "EURUSD": "EURUSD=X", "GBPUSD": "GBPUSD=X", "USDJPY": "JPY=X",
    "AUDUSD": "AUDUSD=X", "USDCAD": "CAD=X", "USDCHF": "CHF=X",
    "NZDUSD": "NZDUSD=X", "EURGBP": "EURGBP=X", "EURJPY": "EURJPY=X",
    "GBPJPY": "GBPJPY=X", "XAUUSD": "GC=F", "BTCUSD": "BTC-USD",
    "US30": "^DJI", "NAS100": "^NDX", "SPX500": "^GSPC", "USOIL": "CL=F",
}


def _get_bytes(url: str, headers: dict | None = None) -> bytes:
    """GET HTTP en binaire (certains flux XML declarent windows-1252)."""
    h = {"User-Agent": UA, "Accept": "*/*"}
    if headers:
        h.update(headers)
    req = urllib.request.Request(url, headers=h)
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        return r.read()


def _get(url: str, headers: dict | None = None) -> str:
    """GET HTTP avec User-Agent (Yahoo/Google exigent un UA navigateur)."""
    h = {"User-Agent": UA, "Accept": "*/*"}
    if headers:
        h.update(headers)
    req = urllib.request.Request(url, headers=h)
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        return r.read().decode("utf-8", errors="replace")


# ── Cache TTL (certaines APIs publiques rate-limitent fortement) ───────────
_CACHE: dict[str, tuple[float, object]] = {}
_CACHE_TTL = {"calendar": 600.0, "news": 180.0, "rates": 300.0}


def _cached(key: str, producer):
    """Retourne la valeur en cache si encore fraiche, sinon la regenere.
    En cas d'echec du producer, la valeur en cache (meme perimee) est
    prefernee a une panne : le dashboard ne doit pas se vider."""
    import time as _t
    ttl = _CACHE_TTL.get(key)
    if ttl is None:
        ttl = 180.0 if key.startswith("news:") else 300.0
    hit = _CACHE.get(key)
    if hit and (_t.time() - hit[0]) < ttl:
        return hit[1]
    try:
        val = producer()
    except Exception as e:
        log.warning("%s indisponible : %s", key, e)
        if hit is not None:
            log.info("%s : retour au cache perime", key)
            return hit[1]
        return None
    _CACHE[key] = (_t.time(), val)
    return val


def _get_json(url: str) -> dict | list:
    return json.loads(_get(url))


def _get_xml(url: str) -> ET.Element:
    return ET.fromstring(_get(url))


# ── 1. Taux de change ───────────────────────────────────────────────────────
def fx_rates(base: str = "USD") -> dict:
    """Taux de change live depuis open.er-api.com (fallback Frankfurter)."""
    base = base.upper()
    try:
        d = _get_json(f"https://open.er-api.com/v6/latest/{base}")
        if d.get("result") == "success":
            rates = d.get("rates", {})
            return {
                "source": "open.er-api.com",
                "base": base,
                "date": d.get("time_last_update_utc", "")[:10],
                "rates": {k: v for k, v in rates.items() if k in ("EUR", "GBP", "JPY", "CHF", "CAD", "AUD", "NZD", "CNY")},
                "pairs": {
                    p: rates.get(p[:3]) and round(rates[p[:3]] / rates[p[3:]], 6)
                    for p in ("EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCAD", "USDCHF")
                    if rates.get(p[:3]) and rates.get(p[3:])
                },
            }
    except Exception as e:  # pragma: no cover - reseau
        log.warning("fx_rates open.er-api indisponible : %s", e)

    # Fallback Frankfurter (base EUR)
    try:
        d = _get_json("https://api.frankfurter.app/latest?base=EUR")
        rates = d.get("rates", {})
        eur = rates.get("USD", 0)
        return {
            "source": "frankfurter.app (BCE)",
            "base": "EUR",
            "date": d.get("date"),
            "rates": rates,
            "pairs": {
                "EURUSD": eur,
                "GBPUSD": round(rates.get("USD", 0) / rates.get("GBP", 1), 6) if rates.get("GBP") else None,
                "USDJPY": round(rates.get("JPY", 0) / rates.get("USD", 1), 4) if rates.get("USD") else None,
            },
        }
    except Exception as e:
        log.warning("fx_rates frankfurter indisponible : %s", e)
        return {"source": None, "error": str(e), "rates": {}, "pairs": {}}


def ecb_reference_rates() -> dict:
    """Taux de reference officiels BCE (XML)."""
    try:
        root = _get_xml("https://www.ecb.europa.eu/stats/eurofxref/eurofxref-daily.xml")
        ns = {"e": "http://www.ecb.int/vocabulary/2002-08-01/eurofxref"}
        cube = root.find(".//e:Cube[@time]", ns)
        if cube is None:
            return {}
        out = {"date": cube.get("time"), "base": "EUR", "rates": {}}
        for c in cube.findall("e:Cube", ns):
            out["rates"][c.get("currency")] = float(c.get("rate"))
        return out
    except Exception as e:
        log.warning("ecb_reference_rates : %s", e)
        return {}


# ── 2. Chandeliers / quotes ─────────────────────────────────────────────────
def yahoo_symbol(symbol: str) -> str:
    s = symbol.upper().replace("/", "")
    return YAHOO_MAP.get(s, s)


def candles(symbol: str, interval: str = "5m", rng: str = "1d", limit: int = 200) -> dict:
    """Chandeliers OHLC depuis Yahoo Finance. Retourne {symbol, interval, candles: [{t,o,h,l,c,v}]}."""
    y = yahoo_symbol(symbol)
    url = (f"https://query1.finance.yahoo.com/v8/finance/chart/{urllib.parse.quote(y)}"
           f"?interval={interval}&range={rng}")
    d = _get_json(url)
    res = (d.get("chart") or {}).get("result")
    if not res:
        return {"symbol": symbol, "yahoo_symbol": y, "error": (d.get("chart") or {}).get("error"), "candles": []}
    r = res[0]
    ts = r.get("timestamp") or []
    q = ((r.get("indicators") or {}).get("quote") or [{}])[0]
    out = []
    for i, t in enumerate(ts):
        c = (q.get("close") or [None] * len(ts))[i]
        if c is None:
            continue
        out.append({
            "t": int(t),
            "o": (q.get("open") or [None] * len(ts))[i],
            "h": (q.get("high") or [None] * len(ts))[i],
            "l": (q.get("low") or [None] * len(ts))[i],
            "c": c,
            "v": (q.get("volume") or [None] * len(ts))[i],
        })
    out = out[-limit:]
    meta = r.get("meta", {})
    return {
        "symbol": symbol,
        "yahoo_symbol": y,
        "interval": interval,
        "range": rng,
        "currency": meta.get("currency"),
        "price": meta.get("regularMarketPrice"),
        "prev_close": meta.get("chartPreviousClose"),
        "candles": out,
    }


def quote(symbol: str) -> dict:
    """Quote compacte (prix, variation 24h) via l'endpoint chart de Yahoo."""
    try:
        d = candles(symbol, interval="5m", rng="1d", limit=2)
        meta_price = d.get("price")
        closes = [c["c"] for c in d.get("candles", []) if c.get("c") is not None]
        prev = d.get("prev_close") or (closes[0] if closes else None)
        price = meta_price or (closes[-1] if closes else None)
        chg = None
        if price and prev:
            chg = round(100.0 * (price - prev) / prev, 3)
        return {
            "symbol": symbol,
            "price": price,
            "prev_close": prev,
            "change_pct": chg,
            "currency": d.get("currency"),
            "ts": int(datetime.now(timezone.utc).timestamp()),
            "error": d.get("error"),
        }
    except Exception as e:
        return {"symbol": symbol, "error": str(e), "price": None, "change_pct": None}


# ── 3. Calendrier economique ───────────────────────────────────────────────
def _calendar_from_xml() -> list:
    """Calendrier ForexFactory via le flux XML.
    L'endpoint JSON (/ff_calendar_thisweek.json) renvoie tres souvent 429,
    le XML lui n'est pas rate-limite : c'est le repli principal."""
    root = ET.fromstring(_get_bytes("https://nfs.faireconomy.media/ff_calendar_thisweek.xml"))
    items = []
    for ev in root.findall("event"):
        def _t(tag: str) -> str:
            el = ev.find(tag)
            return (el.text or "").strip() if el is not None else ""
        raw_date = _t("date")
        # le XML donne MM-DD-YYYY, le JSON donne de l'ISO : on normalise en ISO
        iso_date = raw_date
        m = re.match(r"^(\d{2})-(\d{2})-(\d{4})$", raw_date)
        if m:
            iso_date = f"{m.group(3)}-{m.group(1)}-{m.group(2)}"
        items.append({
            "title": _t("title"),
            "country": _t("country"),
            "date": iso_date,
            "time": _t("time"),
            "impact": _t("impact"),
            "forecast": _t("forecast"),
            "previous": _t("previous"),
            "url": _t("url"),
        })
    return items


def economic_calendar(impact: str | None = None) -> list:
    """Calendrier economique ForexFactory (semaine en cours).
    Cache 10 min. Source : JSON si disponible, sinon XML (pas de 429)."""
    def _fetch() -> list:
        try:
            raw = _get_json("https://nfs.faireconomy.media/ff_calendar_thisweek.json")
            items = []
            for ev in raw if isinstance(raw, list) else []:
                try:
                    items.append({
                        "title": ev.get("title"),
                        "country": ev.get("country"),
                        "date": ev.get("date"),
                        "time": "",
                        "impact": ev.get("impact"),
                        "forecast": ev.get("forecast"),
                        "previous": ev.get("previous"),
                        "url": ev.get("url", ""),
                    })
                except Exception:
                    continue
            if items:
                return items
        except Exception as e:
            log.warning("calendrier JSON indisponible (%s) -> repli XML", e)
        return _calendar_from_xml()

    items = _cached("calendar", _fetch) or []
    if impact:
        items = [i for i in items if (i.get("impact") or "").lower() == impact.lower()]
    return items


# ── 4. Actualites ───────────────────────────────────────────────────────────
def _rss_items(xml_text: str, limit: int) -> list:
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return []
    ns = {"a": "http://www.w3.org/2005/Atom"}
    out = []
    for it in root.findall(".//item")[:limit]:
        title = (it.findtext("title") or "").strip()
        link = (it.findtext("link") or "").strip()
        pub = (it.findtext("pubDate") or "").strip()
        src_el = it.find("source")
        src = (src_el.text or "").strip() if src_el is not None else ""
        if not src:
            m = re.search(r"<\s*source[^>]*>(.*?)<\s*/\s*source>", xml_text)
            src = m.group(1) if m else ""
        out.append({"title": title, "source": src, "link": link, "published": pub})
    if not out:  # flux Atom
        for it in root.findall(".//a:entry", ns)[:limit]:
            t = it.find("a:title", ns)
            s = it.find("a:source", ns)
            out.append({
                "title": (t.text or "").strip() if t is not None else "",
                "source": (s.get("title") or "") if s is not None else "",
                "link": "", "published": "",
            })
    return out


def news(query: str = "forex EURUSD", limit: int = 15, lang: str = "en-US") -> list:
    """Actualites via Google News RSS, repli FXStreet RSS (specialiste Forex).
    Cache 3 min."""
    def _fetch() -> list:
        q = urllib.parse.quote(query)
        if lang.startswith("fr"):
            url = f"https://news.google.com/rss/search?q={q}&hl=fr&gl=FR&ceid=FR:fr"
        else:
            url = f"https://news.google.com/rss/search?q={q}&hl={lang}&gl=US&ceid=US:en"
        try:
            items = _rss_items(_get(url), limit)
            if items:
                return items
        except Exception as e:
            log.warning("news Google indisponible : %s", e)
        # Repli : flux Forex/technique (FXStreet)
        try:
            return _rss_items(_get("https://www.fxstreet.com/rss/news"), limit)
        except Exception as e:
            log.warning("news FXStreet indisponible : %s", e)
            return []

    key = f"news:{query[:60]}"
    return _cached(key, _fetch) or []


# ── 5. Snapshot combine (dashboard) ────────────────────────────────────────
def market_snapshot(symbols: list[str] | None = None, news_limit: int = 8,
                    calendar_limit: int = 10) -> dict:
    """Vue d'ensemble de marche : quotes + calendrier + actus. Tous les appels
    sont tolerants aux pannes : un source KO ne doit pas casser le snapshot.
    Les appels sont PARALLELES (le dashboard ne doit pas attendre 15 s)."""
    from concurrent.futures import ThreadPoolExecutor

    syms = symbols or ["EURUSD", "GBPUSD", "USDJPY", "XAUUSD"]

    def _q(s):
        try:
            return quote(s)
        except Exception as e:
            return {"symbol": s, "error": str(e), "price": None}

    def _rates():
        try:
            return fx_rates()
        except Exception as e:
            return {"error": str(e), "pairs": {}}

    def _cal():
        try:
            return economic_calendar()
        except Exception:
            return []

    def _news():
        try:
            return news("forex OR EURUSD OR Federal Reserve", limit=news_limit)
        except Exception:
            return []

    with ThreadPoolExecutor(max_workers=4) as ex:
        f_q = [ex.submit(_q, s) for s in syms]
        f_r = ex.submit(_rates)
        f_c = ex.submit(_cal)
        f_n = ex.submit(_news)
        quotes = [f.result() for f in f_q]
        rates = f_r.result()
        cal = f_c.result()
        nw = f_n.result()

    return {
        "ts": int(datetime.now(timezone.utc).timestamp()),
        "quotes": quotes,
        "fx_rates": rates,
        "calendar": cal[:calendar_limit],
        "news": nw,
    }


if __name__ == "__main__":  # smoke test
    import json as _json
    print(_json.dumps(market_snapshot(), indent=2, ensure_ascii=False)[:4000])
