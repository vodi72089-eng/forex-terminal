import { getRuntime, pushConfig } from "./bot";

const OC = "http://127.0.0.1:4096";

export const ocHealth = () =>
  fetch(`${OC}/global/health`).then((r) => r.json());

export async function createSession(title = "market-analysis") {
  const r = await fetch(`${OC}/session`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ title }),
  });
  return r.json();
}

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
      ...(model ? { model } : {}),
    }),
  });
  const { parts } = await r.json();
  return (parts as { type: string; text?: string }[])
    .filter((p) => p.type === "text" && p.text)
    .map((p) => p.text)
    .join("\n");
}

/** Cycle complet : etat runtime -> analyse OpenCode -> push bot_config.set (valide par le bot). */
export async function analyzeAndPropose(instruction: string) {
  const s = (await createSession()) as { id?: string };
  if (!s.id) throw new Error("session opencode indisponible");
  const runtime = await getRuntime();
  const out = await prompt(
    s.id,
    `Etat runtime du bot : ${JSON.stringify(runtime)}.\n` +
      `Tache : ${instruction}\n` +
      `Reponds UNIQUEMENT par le contenu JSON complet de shared/bot_config.set.`,
  );
  const res = await pushConfig(out); // le bot valide le FICHIER ENTIER avant d'appliquer
  return { analysis: out, applied: res.ok };
}
