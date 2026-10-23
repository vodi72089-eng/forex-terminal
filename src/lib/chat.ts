/*
Chat avec l'agent OpenCode.

Deux agents :
  - market-analyst : analyse le marche et propose la config du bot (lecture seule)
  - dev-agent      : modifie le code de l'app, cree des strategies

La session est conservee : le chat est un vrai dialogue, pas une analyse a
la demande. Chaque reponse peut contenir :
  - du texte
  - des appels d'outils (market-data, write, edit, bash...)
  - une proposition de bot_config.set (detectee et applicable en un clic)
*/
import { BOT, botBase, j, pushConfig } from "./bot";

export const OC_MODEL =
  process.env.NEXT_PUBLIC_OPENCODE_MODEL || "opencode/grok-4.7";

export type AgentId = "market-analyst" | "dev-agent";

export const AGENTS: { id: AgentId; label: string; hint: string }[] = [
  {
    id: "market-analyst",
    label: "Analyste de marche",
    hint: "Analyse le marche, propose la config du bot. Ne modifie aucun fichier.",
  },
  {
    id: "dev-agent",
    label: "Developpeur",
    hint: "Modifie le code, cree des strategies, lance les tests.",
  },
];

export type ToolCall = { name: string; status: string; output?: string };
export type ChatMessage = {
  role: "user" | "assistant";
  text: string;
  tools?: ToolCall[];
  config?: string;
  error?: string;
};

/* ── Port opencode ────────────────────────────────────────────────────── */
let OC_PORT: number | null = null;

export async function opencodePort(): Promise<number> {
  if (OC_PORT !== null) return OC_PORT;
  try {
    const r = await fetch(`${BOT}/opencode/port`);
    const jd = (await r.json()) as { port?: number };
    if (jd.port) OC_PORT = jd.port;
  } catch { /* le bot n'est pas pret -> defaut */ }
  return OC_PORT ?? 4096;
}

async function ocBase(): Promise<string> {
  return `http://127.0.0.1:${await opencodePort()}`;
}

/* ── Session ──────────────────────────────────────────────────────────── */
export async function createSession(title = "chat"): Promise<string> {
  const base = await ocBase();
  const r = await fetch(`${base}/session`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ title }),
  });
  if (!r.ok) throw new Error(`opencode /session -> ${r.status}`);
  const s = (await r.json()) as { id?: string };
  if (!s.id) throw new Error("session opencode indisponible");
  return s.id;
}

/* ── Envoi d'un message ───────────────────────────────────────────────── */
export type AgentReply = {
  text: string;
  tools: ToolCall[];
  config?: string;
};

function extractConfig(text: string): string | undefined {
  const fence = text.match(/```(?:json)?\s*([\s\S]*?)```/i);
  const src = fence ? fence[1] : text;
  const start = src.indexOf("{");
  const end = src.lastIndexOf("}");
  if (start === -1 || end <= start) return undefined;
  const chunk = src.slice(start, end + 1);
  try {
    const o = JSON.parse(chunk) as Record<string, unknown>;
    // une proposition de config a "version" + "strategy" + "risk"
    if (o.version !== undefined && o.strategy && o.risk) return chunk;
  } catch { /* pas du JSON */ }
  return undefined;
}

export async function sendChat(
  sessionId: string,
  text: string,
  agent: AgentId,
): Promise<AgentReply> {
  const base = await ocBase();
  const model = {
    providerID: OC_MODEL.split("/")[0],
    modelID: OC_MODEL.split("/").slice(1).join("/"),
  };
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), 600000); // 10 min (le LLM peut reflechir)
  try {
    const r = await fetch(`${base}/session/${sessionId}/message`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      signal: ctrl.signal,
      body: JSON.stringify({
        agent,
        model,
        parts: [{ type: "text", text }],
      }),
    });
    if (!r.ok) throw new Error(`opencode /message -> ${r.status}`);
    const body = (await r.json()) as {
      info?: { error?: { name?: string; data?: { message?: string } } };
      parts?: {
        type: string;
        text?: string;
        tool?: string;
        state?: { status?: string; output?: string; title?: string };
      }[];
    };

    const err = body.info?.error;
    if (err) {
      throw new Error(`LLM : ${err.data?.message ?? err.name ?? "erreur inconnue"}`);
    }

    const parts = body.parts ?? [];
    const out = parts
      .filter((p) => p.type === "text" && p.text)
      .map((p) => p.text as string)
      .join("\n")
      .trim();

    const tools: ToolCall[] = parts
      .filter((p) => p.type === "tool")
      .map((p) => ({
        name: p.tool ?? "outil",
        status: p.state?.status ?? "",
        output: String(p.state?.output ?? p.state?.title ?? "").slice(0, 400),
      }));

    return { text: out, tools, config: extractConfig(out) };
  } catch (e) {
    if ((e as Error).name === "AbortError") throw new Error("LLM : delai depasse (10 min)");
    throw e;
  } finally {
    clearTimeout(timer);
  }
}

/* ── Actions disponibles dans le chat ──────────────────────────────────── */
export const applyProposedConfig = (raw: string) => pushConfig(raw);

export const reloadStrategies = async () => {
  const base = await botBase();
  return j<{ ok: boolean; available: string[] }>(
    `${base}/strategies/reload`,
    { method: "POST", headers: { "X-Bot-Token": process.env.NEXT_PUBLIC_BOT_TOKEN || "dev-token-local" } },
  );
};

export type AppInfo = {
  root: string;
  writable: boolean;
  shared_dir: string;
  user_strategies_dir: string;
};

export const getAppInfo = async () => {
  const base = await botBase();
  return j<AppInfo>(`${base}/app/info`);
};
