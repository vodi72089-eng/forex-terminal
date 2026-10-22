import { BOT, botBase, getRuntime, j, pushConfig, type Runtime } from "./bot";

/** Port du serveur opencode. Il n'est PAS fixe : Tauri choisit un port libre
 *  (4096 peut etre occupe par un processus etranger) et le publie via le bot
 *  (GET /opencode/port). On met en cache le resultat. */
let OC_PORT: number | null = null;
let OC_PORT_SOURCE = "defaut 4096";

export async function opencodePort(): Promise<number> {
  if (OC_PORT !== null) return OC_PORT;
  try {
    const r = await fetch(`${BOT}/opencode/port`);
    const j = (await r.json()) as { port?: number };
    if (j.port) {
      OC_PORT = j.port;
      OC_PORT_SOURCE = `choisi par l'app (${j.port})`;
    }
  } catch { /* le bot n'est pas encore pret -> port par defaut */ }
  return OC_PORT ?? 4096;
}

/** Libelle du port opencode (pour l'affichage dans le dashboard). */
export const opencodePortLabel = () => OC_PORT_SOURCE;

async function ocBase(): Promise<string> {
  const p = await opencodePort();
  return `http://127.0.0.1:${p}`;
}

/** Modele par defaut. Doit exister dans `opencode models`.
 *  Surchargeable : NEXT_PUBLIC_OPENCODE_MODEL=opencode/grok-4.7 */
export const MODEL = process.env.NEXT_PUBLIC_OPENCODE_MODEL || "opencode/grok-4.7";

export const ocHealth = async () => {
  const base = await ocBase();
  try {
    const r = await fetch(`${base}/global/health`, { signal: AbortSignal.timeout(3000) });
    return await r.json();
  } catch (e) {
    return { healthy: false, error: String(e) };
  }
};

export async function createSession(title = "market-analysis") {
  const base = await ocBase();
  const r = await fetch(`${base}/session`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ title }),
  });
  if (!r.ok) throw new Error(`opencode /session -> ${r.status}`);
  return (await r.json()) as { id?: string };
}

export type MessageResponse = {
  info?: { error?: { name?: string; data?: { message?: string } } };
  parts?: { type: string; text?: string }[];
};

/** Envoie un message a l'agent. Le serveur OpenCode renvoie HTTP 200 meme
 *  quand le LLM echoue : l'erreur est dans `info.error`. Si on ne la lit pas,
 *  `parts` est vide et l'echec passe totalement inaperçu. */
export async function prompt(
  sessionId: string,
  text: string,
  model?: { providerID: string; modelID: string },
) {
  const base = await ocBase();
  const r = await fetch(`${base}/session/${sessionId}/message`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      agent: "market-analyst",
      parts: [{ type: "text", text }],
      model: model ?? { providerID: MODEL.split("/")[0], modelID: MODEL.split("/").slice(1).join("/") },
    }),
  });
  if (!r.ok) throw new Error(`opencode /message -> ${r.status}`);
  const body = (await r.json()) as MessageResponse;

  const err = body.info?.error;
  if (err) {
    const msg = err.data?.message ?? err.name ?? "erreur inconnue";
    throw new Error(`LLM : ${msg}`);
  }

  const out = (body.parts ?? [])
    .filter((p) => p.type === "text" && p.text)
    .map((p) => p.text)
    .join("\n")
    .trim();

  if (!out) throw new Error("LLM : reponse vide (parts[] sans texte)");
  return out;
}

/** Retire les fences markdown et extrait l'objet JSON. */
export function extractJson(raw: string): string {
  let s = raw.trim();
  const fence = s.match(/```(?:json)?\s*([\s\S]*?)```/i);
  if (fence) s = fence[1].trim();
  const start = s.indexOf("{");
  const end = s.lastIndexOf("}");
  if (start === -1 || end === -1 || end <= start) {
    throw new Error("la reponse ne contient aucun objet JSON");
  }
  return s.slice(start, end + 1);
}

/** Resume le marche pour l'agent : quotes, taux, calendrier, actus, candles.
 *  Le bot les recupere via les APIs publiques : l'agent voit donc TOUJOURS
 *  le marche, meme si le MCP market-data n'est pas installe. */
async function marketBrief(symbols = "EURUSD,GBPUSD,USDJPY,XAUUSD") {
  const base = await botBase();
  const out: string[] = [];
  try {
    const s = await j<{
      quotes: { symbol: string; price: number | null; change_pct: number | null }[];
      fx_rates: { source?: string; pairs?: Record<string, number> };
      calendar: { title: string; country: string; impact: string; forecast: string; previous: string; date: string }[];
      news: { title: string; source: string }[];
    }>(`${base}/market/snapshot?symbols=${encodeURIComponent(symbols)}`, undefined, 25000);

    if (s.quotes?.length) {
      out.push("QUOTES :");
      for (const q of s.quotes) {
        out.push(`  - ${q.symbol} = ${q.price ?? "?"} (${q.change_pct ?? "?"} %)`);
      }
    }
    if (s.fx_rates?.pairs && Object.keys(s.fx_rates.pairs).length) {
      out.push("TAUX : " + Object.entries(s.fx_rates.pairs)
        .map(([k, v]) => `${k}=${v}`).join("  ") + ` (source ${s.fx_rates.source})`);
    }
    if (s.calendar?.length) {
      out.push("CALENDRIER ECONOMIQUE :");
      for (const e of s.calendar.slice(0, 12)) {
        out.push(`  - [${e.impact}] ${e.title} (${e.country})`
          + ` prev=${e.previous || "?"} forecast=${e.forecast || "?"}`);
      }
    }
    if (s.news?.length) {
      out.push("ACTUALITES :");
      for (const n of s.news.slice(0, 10)) {
        out.push(`  - ${n.title} (${n.source})`);
      }
    }
  } catch (e) {
    out.push(`(marche indisponible : ${String(e)})`);
  }

  // Chandeliers : l'agent peut calculer lui-meme la volatilite
  try {
    const c = await j<{ candles: { t: number; o: number; h: number; l: number; c: number }[] }>(
      `${base}/market/candles?symbol=EURUSD&interval=5m&range=1d`, undefined, 20000);
    const cd = c.candles ?? [];
    if (cd.length) {
      const closes = cd.map((x) => x.c);
      const hi = Math.max(...cd.map((x) => x.h));
      const lo = Math.min(...cd.map((x) => x.l));
      const last = closes[closes.length - 1];
      const sma = (n: number) => closes.slice(-n).reduce((a, b) => a + b, 0) / n;
      const range = (hi - lo) / last * 100;
      out.push("CANDLES EURUSD M5 (5m x " + cd.length + ") :");
      out.push(`  - dernier close=${last}  plus-haut=${hi}  plus-bas=${lo}  range=${range.toFixed(3)}%`);
      out.push(`  - SMA20=${sma(20).toFixed(6)}  SMA50=${sma(Math.min(50, closes.length)).toFixed(6)}`);
      const r = Math.abs((sma(20) - sma(Math.min(50, closes.length))) / last) * 100;
      out.push(`  - ecart SMA20/SMA50 = ${r.toFixed(3)}% (volatilite)`);
    }
  } catch (e) {
    out.push(`(candeliers indisponibles : ${String(e)})`);
  }
  return out.join("\n");
}

/** Cycle complet : etat runtime + marche reel -> analyse OpenCode ->
 *  push bot_config.set (valide en TOTAL par le bot). */
export async function analyzeAndPropose(instruction: string) {
  const s = await createSession();
  if (!s.id) throw new Error("session opencode indisponible");

  const runtime: Runtime = await getRuntime();
  const market = await marketBrief();
  const model = { providerID: MODEL.split("/")[0], modelID: MODEL.split("/").slice(1).join("/") };

  const raw = await prompt(
    s.id,
    `Etat runtime du bot : ${JSON.stringify(runtime)}\n\n` +
      `DONNEES DE MARCHE REELLES (APIs publiques, recuperees a l'instant) :\n${market}\n\n` +
      `Tache : ${instruction}\n\n` +
      `Tu peux aussi appeler les outils MCP "market-data" (market_snapshot, ` +
      `market_quote, ohlc_candles, economic_calendar, market_news) pour aller ` +
      `plus loin sur le marche.\n` +
      `Reponds UNIQUEMENT par le contenu JSON complet de shared/bot_config.set, ` +
      `sans texte autour et sans blocs markdown.`,
    model,
  );

  const json = extractJson(raw);
  const applied = await pushConfig(json); // le bot valide le FICHIER ENTIER
  return { analysis: raw, json, applied };
}
