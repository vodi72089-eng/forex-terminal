"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  AGENTS, applyProposedConfig, createSession, getAppInfo, reloadStrategies,
  sendChat, type AgentId, type AppInfo, type ChatMessage,
} from "@/lib/chat";

export default function Chat({
  onApplied,
  onStrategiesChanged,
}: {
  onApplied?: () => void;
  onStrategiesChanged?: () => void;
}) {
  const [agent, setAgent] = useState<AgentId>("market-analyst");
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [session, setSession] = useState<string | null>(null);
  const [info, setInfo] = useState<AppInfo | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const endRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    getAppInfo().then(setInfo).catch(() => {});
  }, []);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, busy]);

  const send = useCallback(async () => {
    const text = input.trim();
    if (!text || busy) return;
    setInput("");
    setBusy(true);
    setNotice(null);
    setMessages((m) => [...m, { role: "user", text }]);
    try {
      let sid = session;
      if (!sid) {
        sid = await createSession("chat-" + agent);
        setSession(sid);
      }
      const r = await sendChat(sid, text, agent);
      setMessages((m) => [...m, { role: "assistant", text: r.text, tools: r.tools, config: r.config }]);
      // si l'agent a touche aux strategies, on propose de recharger
      if (r.tools.some((t) => /strateg|write|edit/i.test(t.name))) {
        setNotice("L'agent a modifie des fichiers : recharge les strategies pour les prendre en compte.");
      }
    } catch (e) {
      setMessages((m) => [...m, { role: "assistant", text: "", error: String(e) }]);
    } finally {
      setBusy(false);
    }
  }, [agent, busy, input, session]);

  const applyConfig = async (raw: string) => {
    try {
      await applyProposedConfig(raw);
      setNotice("Config appliquee par le bot.");
      onApplied?.();
    } catch (e) {
      setNotice(`Config rejetee : ${String(e)}`);
    }
  };

  const doReload = async () => {
    try {
      const r = await reloadStrategies();
      setNotice(`Strategies rechargees : ${r.available.join(", ")}`);
      onStrategiesChanged?.();
    } catch (e) {
      setNotice(`Rechargement impossible : ${String(e)}`);
    }
  };

  const current = AGENTS.find((a) => a.id === agent);

  return (
    <section id="chat">
      <h2>Chat avec l&apos;agent</h2>
      <div className="card chat">
        <div className="row" style={{ justifyContent: "space-between" }}>
          <div className="row">
            {AGENTS.map((a) => (
              <button
                key={a.id}
                className={agent === a.id ? "" : "secondary"}
                onClick={() => { setAgent(a.id); setSession(null); setMessages([]); }}
                title={a.hint}
              >
                {a.label}
              </button>
            ))}
            <span className="muted" style={{ fontSize: 12 }}>{current?.hint}</span>
          </div>
          <div className="row">
            {info && (
              <span className="muted" style={{ fontSize: 11 }}>
                {info.writable
                  ? "Dossier de l'app accessible en ecriture (l'agent peut le modifier)"
                  : "Dossier de l'app en lecture seule : lance l'app depuis les sources pour que l'agent puisse ecrire"}
              </span>
            )}
            <button className="secondary" onClick={doReload}>Recharger les strategies</button>
            <button className="secondary" onClick={() => { setMessages([]); setSession(null); }}>Effacer</button>
          </div>
        </div>

        <div className="msgs">
          {messages.length === 0 && (
            <div className="muted" style={{ fontSize: 13 }}>
              {agent === "market-analyst"
                ? "Demande une analyse du marche, un reglage de risque, ou une proposition de configuration. La config proposee pourra etre appliquee en un clic."
                : "Demande une modification de l'app ou une nouvelle strategie. Ex : « cree une strategie de moyenne mobile croisee a 20/50 »."}
            </div>
          )}
          {messages.map((m, i) => (
            <div key={i} className={`msg ${m.role}`}>
              {m.role === "user" && <div className="who">Toi</div>}
              {m.role === "assistant" && <div className="who">Agent</div>}
              {m.error && <div className="err">{m.error}</div>}
              {m.text && <div className="txt">{m.text}</div>}
              {m.tools && m.tools.length > 0 && (
                <details className="tools">
                  <summary>{m.tools.length} appel(s) d&apos;outil</summary>
                  {m.tools.map((t, j) => (
                    <div className="tool" key={j}>
                      <b>{t.name}</b> <span className="muted">{t.status}</span>
                      {t.output && <pre>{t.output}</pre>}
                    </div>
                  ))}
                </details>
              )}
              {m.config && (
                <button className="apply" onClick={() => applyConfig(m.config as string)}>
                  Appliquer cette config au bot
                </button>
              )}
            </div>
          ))}
          {busy && <div className="muted" style={{ fontSize: 12 }}>L&apos;agent reflechit...</div>}
          <div ref={endRef} />
        </div>

        {notice && <div className="muted" style={{ fontSize: 12, marginTop: 6 }}>{notice}</div>}

        <div className="row" style={{ marginTop: 10 }}>
          <input
            className="inp grow"
            placeholder={agent === "market-analyst"
              ? "Ex : analyse le marche et propose une config prudente..."
              : "Ex : cree une strategie Donchian 20/10 et ajoute-la au dashboard"}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(); } }}
          />
          <button onClick={send} disabled={busy || !input.trim()}>
            {busy ? "..." : "Envoyer"}
          </button>
        </div>
      </div>
    </section>
  );
}
