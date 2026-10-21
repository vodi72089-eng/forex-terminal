const BOT = "http://127.0.0.1:8100";
const TOKEN = "dev-token-local"; // = bot_token dans shared/credentials.json

export type Runtime = {
  ts: number;
  connected: boolean;
  account: { login: number; server: string; equity: number; balance: number } | null;
  positions: {
    ticket: number; symbol: string; side: string;
    lot: number; profit: number; price_open: number;
  }[];
  pnl_today_pct: number;
  kill_switch: boolean;
  config_version: number | null;
  config_enabled: boolean;
  strategy: Record<string, unknown> | null;
  last_error: string | null;
};

async function j<T>(url: string, init?: RequestInit): Promise<T> {
  const r = await fetch(url, init);
  if (!r.ok) throw new Error(`${url} -> ${r.status}`);
  return r.json() as Promise<T>;
}

export const getRuntime = () => j<Runtime>(`${BOT}/runtime`);
export const health = () => j<{ ok: boolean }>(`${BOT}/health`);

export const pushConfig = (raw: string) =>
  fetch(`${BOT}/config/raw`, {
    method: "POST",
    headers: { "Content-Type": "text/plain", "X-Bot-Token": TOKEN },
    body: raw,
  });

export const closeAll = () =>
  fetch(`${BOT}/close-all`, { method: "POST", headers: { "X-Bot-Token": TOKEN } });

export const sendOrder = (body: {
  symbol: string; side: string; lot: number; sl_pips: number; tp_pips: number;
}) =>
  fetch(`${BOT}/order`, {
    method: "POST",
    headers: { "Content-Type": "application/json", "X-Bot-Token": TOKEN },
    body: JSON.stringify(body),
  });
