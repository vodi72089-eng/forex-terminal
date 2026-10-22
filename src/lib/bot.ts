export const BOT = "http://127.0.0.1:8100";

/** Ports possibles du bot. 8100 est le defaut ; si un processus etranger
 *  l'occupe, Tauri choisit le suivant et le dashboard le decouvre en
 *  testant la liste (meme ordre que Tauri). */
export const BOT_PORTS = [8100, 8101, 8102, 8110, 8180];

let BOT_BASE: string | null = null;
let BOT_DISCOVERY_FAILED = false;

/** Resout la base URL du bot (une seule tentative de decouverte).
 *  Si la decouverte echoue (bot pas encore demarre), on NE fige pas le
 *  resultat : la prochaine appellation reessaie. */
export async function botBase(): Promise<string> {
  if (BOT_BASE) return BOT_BASE;
  for (const p of BOT_PORTS) {
    const base = `http://127.0.0.1:${p}`;
    try {
      const ctrl = new AbortController();
      const t = setTimeout(() => ctrl.abort(), 1500);
      const r = await fetch(`${base}/health`, { signal: ctrl.signal });
      clearTimeout(t);
      if (r.ok) {
        BOT_BASE = base;
        BOT_DISCOVERY_FAILED = false;
        return base;
      }
    } catch { /* port indisponible -> suivant */ }
  }
  BOT_DISCOVERY_FAILED = true;
  return BOT;
}

/** true si le bot n'a pas encore repondu (diagnostic affiche dans l'UI). */
export const botUnreachable = () => BOT_DISCOVERY_FAILED;

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
export async function j<T>(url: string, init?: RequestInit, timeoutMs = 8000): Promise<T> {
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), timeoutMs);
  try {
    const r = await fetch(url, { ...init, signal: init?.signal ?? ctrl.signal });
    if (!r.ok) throw new Error(`${url} -> HTTP ${r.status}`);
    return (await r.json()) as T;
  } catch (e) {
    const err = e as Error;
    if (err.name === "AbortError") {
      throw new Error(`Le bot ne repond pas (${url} : timeout ${timeoutMs} ms)`);
    }
    if (err instanceof TypeError || /Failed to fetch|NetworkError|load failed/i.test(err.message)) {
      throw new Error(
        `Bot injoignable sur ${url} : le process du bot est arreté ou le port est bloque. ` +
        `Verifie %APPDATA%\\com.forex.terminal\\bot.log.err`,
      );
    }
    throw e;
  } finally {
    clearTimeout(timer);
  }
}

export const getRuntime = async () => j<Runtime>(`${await botBase()}/runtime`);
export const health = async () => j<{ ok: boolean }>(`${await botBase()}/health`);
export const getLogs = async () => j<LogLine[]>(`${await botBase()}/logs`);
export const getConfig = async () => j<Record<string, unknown>>(`${await botBase()}/config`);

export const getSnapshot = async (symbols = "EURUSD,GBPUSD,USDJPY,XAUUSD") =>
  j<Snapshot>(`${await botBase()}/market/snapshot?symbols=${encodeURIComponent(symbols)}`, undefined, 25000);

export const getQuote = async (symbol: string) =>
  j<Quote>(`${await botBase()}/market/quote?symbol=${encodeURIComponent(symbol)}`);

export const getCalendar = async () => j<CalendarEvent[]>(`${await botBase()}/market/calendar`);

export const getNews = async (q = "forex EURUSD", limit = 10) =>
  j<NewsItem[]>(`${await botBase()}/market/news?q=${encodeURIComponent(q)}&limit=${limit}`);

/** Pousse le FICHIER ENTIER de config. Le bot valide puis rejette en total. */
export const pushConfig = async (raw: string) => {
  const base = await botBase();
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), 15000);
  try {
    const r = await fetch(`${base}/config/raw`, {
      method: "POST",
      headers: { "Content-Type": "text/plain", "X-Bot-Token": TOKEN },
      body: raw,
      signal: ctrl.signal,
    });
    if (!r.ok) {
      let detail = `HTTP ${r.status}`;
      try {
        const j = await r.json();
        detail = j.detail ?? detail;
      } catch { /* reponse non JSON */ }
      throw new Error(detail);
    }
    return await r.json();
  } catch (e) {
    if ((e as Error).name === "AbortError") throw new Error("push config : timeout (15s)");
    throw e;
  } finally {
    clearTimeout(timer);
  }
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
  const base = await botBase();
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), 15000);
  try {
    const r = await fetch(`${base}/close-all`, {
      method: "POST",
      headers: { "X-Bot-Token": TOKEN },
      signal: ctrl.signal,
    });
    if (!r.ok) throw new Error(`close-all -> ${r.status}`);
    return await r.json();
  } catch (e) {
    if ((e as Error).name === "AbortError") throw new Error("close-all : timeout (15s)");
    throw e;
  } finally {
    clearTimeout(timer);
  }
};

export const sendOrder = async (body: {
  symbol: string; side: string; lot: number; sl_pips: number; tp_pips: number;
}) => {
  const base = await botBase();
  return fetch(`${base}/order`, {
    method: "POST",
    headers: { "Content-Type": "application/json", "X-Bot-Token": TOKEN },
    body: JSON.stringify(body),
  });
};

/* ── MT5 ─────────────────────────────────────────────────────────────── */

export type Mt5Status = {
  connected: boolean;
  login: number;
  server: string;
  has_password: boolean;
  attempts: number;
  last_error: string | null;
  account: { login: number; server: string; name: string; currency: string } | null;
  mt5forge: boolean;
  credentials_path: string;
  credentials_hint: string;
};

export const getMt5Status = async () => {
  const base = await botBase();
  return j<Mt5Status>(`${base}/mt5/status`);
};

export const connectMt5 = async () => {
  const base = await botBase();
  const r = await fetch(`${base}/mt5/connect`, {
    method: "POST",
    headers: { "X-Bot-Token": TOKEN },
  });
  if (!r.ok) throw new Error(`connect MT5 -> ${r.status}`);
  return r.json();
};

export const saveMt5Credentials = async (body: {
  login: number; password: string; server: string; bot_token?: string;
}) => {
  const base = await botBase();
  const r = await fetch(`${base}/mt5/credentials`, {
    method: "POST",
    headers: { "Content-Type": "application/json", "X-Bot-Token": TOKEN },
    body: JSON.stringify(body),
  });
  if (!r.ok) {
    let d = `HTTP ${r.status}`;
    try { d = (await r.json()).detail ?? d; } catch { /* non JSON */ }
    throw new Error(d);
  }
  return r.json();
};

/* ── Strategies ──────────────────────────────────────────────────────── */

export type StrategyParam = {
  type: "int" | "float" | "bool";
  min?: number; max?: number; default: number | boolean; label: string;
};

export type StrategyDef = {
  name: string;
  description: string;
  builtin: boolean;
  params: Record<string, StrategyParam>;
};

export type StrategiesPayload = {
  available: StrategyDef[];
  current: Record<string, unknown> | null;
  user_dir: string;
  timeframes: string[];
};

export const getStrategies = async () => {
  const base = await botBase();
  return j<StrategiesPayload>(`${base}/strategies`);
};

export const applyStrategy = async (body: {
  name: string; timeframe: string; params: Record<string, unknown>;
}) => {
  const base = await botBase();
  const r = await fetch(`${base}/strategy`, {
    method: "POST",
    headers: { "Content-Type": "application/json", "X-Bot-Token": TOKEN },
    body: JSON.stringify(body),
  });
  if (!r.ok) {
    let d = `HTTP ${r.status}`;
    try { d = (await r.json()).detail ?? d; } catch { /* non JSON */ }
    throw new Error(d);
  }
  return r.json();
};
