import { getRuntime, pushConfig, type Runtime } from "./bot";

const OC = "http://127.0.0.1:4096";

/** Modele par defaut. Doit exister dans `opencode models`.
 *  Surchargeable : NEXT_PUBLIC_OPENCODE_MODEL=opencode/grok-4.7 */
export const MODEL = process.env.NEXT_PUBLIC_OPENCODE_MODEL || "opencode/grok-4.7";

export const ocHealth = () => fetch(`${OC}/global/health`).then((r) => r.json());

export async function createSession(title = "market-analysis") {
  const r = await fetch(`${OC}/session`, {
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
  const r = await fetch(`${OC}/session/${sessionId}/message`, {
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

/** Cycle complet : etat runtime -> analyse OpenCode -> push bot_config.set
 *  (valide en TOTAL par le bot). */
export async function analyzeAndPropose(instruction: string) {
  const s = await createSession();
  if (!s.id) throw new Error("session opencode indisponible");

  const runtime: Runtime = await getRuntime();
  const model = { providerID: MODEL.split("/")[0], modelID: MODEL.split("/").slice(1).join("/") };

  const raw = await prompt(
    s.id,
    `Etat runtime du bot : ${JSON.stringify(runtime)}\n\n` +
      `Tache : ${instruction}\n\n` +
      `Utilise les outils MCP "market-data" (market_snapshot, market_quote, ` +
      `ohlc_candles, economic_calendar, market_news) pour obtenir des donnees ` +
      `de marche REELLES.\n` +
      `Reponds UNIQUEMENT par le contenu JSON complet de shared/bot_config.set, ` +
      `sans texte autour et sans blocs markdown.`,
    model,
  );

  const json = extractJson(raw);
  const applied = await pushConfig(json); // le bot valide le FICHIER ENTIER
  return { analysis: raw, json, applied };
}
