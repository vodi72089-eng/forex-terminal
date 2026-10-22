const BOT = "http://127.0.0.1:8100";

// Token du bot. Doit correspondre a `bot_token` dans shared/credentials.json.
// Surcharge possible a la construction : NEXT_PUBLIC_BOT_TOKEN=... npm run build
const TOKEN = process.env.NEXT_PUBLIC_BOT_TOKEN || "dev-token-local";

export type Position = {
  ticket: number; symbol: string; side: string;
  lot: number; profit: number; price_open: number;
  sl?: number; tp?: number; swap?: number;
};

export type LogLine = { ts: string; level: string; source: string; msg: string };

export type Runtime = {
  ts: number;
  updated_at?: string;
  connected: boolean;
  account: { login: number; server: string; equity: number; balance: number;
             currency?: string; margin_free?: number } | null;
  positions: Position[];
  pnl_today_pct: number;
  kill_switch: boolean;
  config_version: number | null;
  config_enabled: boolean;
  strategy: Record<string, unknown> | null;
  risk?: Record<string, number>;
  limits?: Record<string, number>;
  last_error: string | null;
  log?: LogLine[];
  shared_dir?: string;
};

export type Quote = {
  symbol: string; price: number | null; prev_close: number | null;
  change_pct: number | null; currency?: string; error?: string;
};

export type CalendarEvent = {
  title: string; country: string; date: string;
  time?: string;
  impact: string; forecast: string; previous: string;
};

export type NewsItem = { title: string; source: string; link: string; published: string };

export type Snapshot = {
  ts: number;
  quotes: Quote[];
  fx_rates: { source?: string; base?: string; date?: string; pairs?: Record<string, number> };
  calendar: CalendarEvent[];
  news: NewsItem[];
};

/** Timeout par requete. Sans cela, UN endpoint qui ne repond pas (serveur
 *  zombie, port occupe) fige la chaine de rafraichissement du dashboard. */
async function j<T>(url: string, init?: RequestInit, timeoutMs = 8000): Promise<T> {
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), timeoutMs);
  try {
    const r = await fetch(url, { ...init, signal: init?.signal ?? ctrl.signal });
    if (!r.ok) throw new Error(`${url} -> ${r.status}`);
    return (await r.json()) as T;
  } catch (e) {
    if ((e as Error).name === "AbortError") {
      throw new Error(`${url} -> timeout (${timeoutMs}ms)`);
    }
    throw e;
  } finally {
    clearTimeout(timer);
  }
}

export const getRuntime = () => j<Runtime>(`${BOT}/runtime`);
export const health = () => j<{ ok: boolean }>(`${BOT}/health`);
export const getLogs = () => j<LogLine[]>(`${BOT}/logs`);
export const getConfig = () => j<Record<string, unknown>>(`${BOT}/config`);

export const getSnapshot = (symbols = "EURUSD,GBPUSD,USDJPY,XAUUSD") =>
  j<Snapshot>(`${BOT}/market/snapshot?symbols=${encodeURIComponent(symbols)}`, undefined, 25000);

export const getQuote = (symbol: string) =>
  j<Quote>(`${BOT}/market/quote?symbol=${encodeURIComponent(symbol)}`);

export const getCalendar = () => j<CalendarEvent[]>(`${BOT}/market/calendar`);

export const getNews = (q = "forex EURUSD", limit = 10) =>
  j<NewsItem[]>(`${BOT}/market/news?q=${encodeURIComponent(q)}&limit=${limit}`);

/** Pousse le FICHIER ENTIER de config. Le bot valide puis rejette en total. */
export const pushConfig = async (raw: string) => {
  const r = await fetch(`${BOT}/config/raw`, {
    method: "POST",
    headers: { "Content-Type": "text/plain", "X-Bot-Token": TOKEN },
    body: raw,
  });
  if (!r.ok) {
    let detail = `HTTP ${r.status}`;
    try {
      const j = await r.json();
      detail = j.detail ?? detail;
    } catch { /* reponse non JSON */ }
    throw new Error(detail);
  }
  return r.json();
};

/** Active / desactive le bot en repoussant la config courante complete. */
export const setEnabled = async (enabled: boolean) => {
  const cfg = await getConfig();
  if (!cfg || !cfg.version) throw new Error("aucune config chargee");
  const next = { ...cfg, enabled, version: Number(cfg.version) + 1,
                 issued_by: "dashboard", issued_at: new Date().toISOString() };
  return pushConfig(JSON.stringify(next));
};

export const closeAll = async () => {
  const r = await fetch(`${BOT}/close-all`, { method: "POST", headers: { "X-Bot-Token": TOKEN } });
  if (!r.ok) throw new Error(`close-all -> ${r.status}`);
  return r.json();
};

export const sendOrder = (body: {
  symbol: string; side: string; lot: number; sl_pips: number; tp_pips: number;
}) =>
  fetch(`${BOT}/order`, {
    method: "POST",
    headers: { "Content-Type": "application/json", "X-Bot-Token": TOKEN },
    body: JSON.stringify(body),
  });
