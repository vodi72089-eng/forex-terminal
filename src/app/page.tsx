"use client";

import { useCallback, useEffect, useState } from "react";
import {
  closeAll, getConfig, getSnapshot, getRuntime, health, setEnabled,
  type CalendarEvent, type LogLine, type NewsItem, type Quote, type Runtime,
} from "@/lib/bot";
import { analyzeAndPropose, ocHealth } from "@/lib/opencode";

const fmt = (n: number | null | undefined, d = 2) =>
  n === null || n === undefined || Number.isNaN(n) ? "—" : n.toFixed(d);

/** Le calendrier peut arriver en ISO ("2026-10-18T10:15:00-04:00") ou en
 *  date + heure ("2026-10-18" + "2:15pm") selon la source. */
const fmtEventDate = (e: { date?: string; time?: string }) => {
  const d = e.date ?? "";
  if (!d) return "";
  if (d.includes("T")) return d.slice(5, 16).replace("T", " ");
  return e.time ? `${d.slice(5)} ${e.time}` : d;
};

export default function Page() {
  const [rt, setRt] = useState<Runtime | null>(null);
  const [botOk, setBotOk] = useState(false);
  const [ocOk, setOcOk] = useState(false);
  const [busy, setBusy] = useState(false);
  const [toggleBusy, setToggleBusy] = useState(false);
  const [log, setLog] = useState<string[]>([]);
  const [err, setErr] = useState<string | null>(null);
  const [quotes, setQuotes] = useState<Quote[]>([]);
  const [calendar, setCalendar] = useState<CalendarEvent[]>([]);
  const [news, setNews] = useState<NewsItem[]>([]);
  const [cfg, setCfg] = useState<Record<string, unknown> | null>(null);

  const addLog = (m: string) =>
    setLog((l) => [`${new Date().toLocaleTimeString()} — ${m}`, ...l].slice(0, 30));

  const refresh = useCallback(async () => {
    // Les 3 appels sont INDEPENDANTS : un endpoint qui ne repond pas (serveur
    // opencode plante, port occupe...) ne doit pas figer les autres.
    const [h, o, r] = await Promise.allSettled([
      health(),
      ocHealth() as Promise<{ healthy?: boolean }>,
      getRuntime(),
    ]);
    setBotOk(h.status === "fulfilled" && Boolean(h.value?.ok));
    setOcOk(o.status === "fulfilled" && Boolean(o.value?.healthy));
    if (r.status === "fulfilled") {
      setRt(r.value);
      setErr(null);
    } else {
      setErr(String(r.reason));
    }
  }, []);

  const refreshMarket = useCallback(async () => {
    try {
      const s = await getSnapshot();
      setQuotes(s.quotes ?? []);
      setCalendar(s.calendar ?? []);
      setNews(s.news ?? []);
    } catch { /* le marche est optionnel */ }
  }, []);

  useEffect(() => {
    refresh();
    refreshMarket();
    const t = setInterval(refresh, 2000);
    const m = setInterval(refreshMarket, 60000);
    return () => { clearInterval(t); clearInterval(m); };
  }, [refresh, refreshMarket]);

  useEffect(() => {
    getConfig().then(setCfg).catch(() => {});
  }, [rt?.config_version]);

  const runAnalysis = async () => {
    setBusy(true); setErr(null);
    addLog("Analyse OpenCode lancee (market-analyst + MCP market-data)...");
    try {
      const r = await analyzeAndPropose(
        "Analyse le marche actuel (taux, calendrier economique, actualites, " +
        "chandeliers) et propose une configuration de bot adaptee. " +
        "Resserre les risques si la volatilite est elevee ou si un evenement " +
        "economique High impact est imminent. Ne propose que des valeurs " +
        "strictement inferieures aux limites actuelles.",
      );
      addLog(r.applied
        ? "bot_config.set valide et applique par le bot."
        : "bot_config.set REJETE par la validation (fichier entier).");
    } catch (e) {
      addLog(`Erreur analyse : ${String(e)}`);
      setErr(String(e));
    } finally { setBusy(false); }
  };

  const toggleEnabled = async () => {
    setToggleBusy(true);
    try {
      const next = !(rt?.config_enabled ?? false);
      await setEnabled(next);
      addLog(`Bot ${next ? "ACTIVE" : "DESACTIVE"} par l'utilisateur.`);
      await refresh();
    } catch (e) {
      addLog(`Erreur bascule : ${String(e)}`);
      setErr(String(e));
    } finally { setToggleBusy(false); }
  };

  const emergencyClose = async () => {
    if (!confirm("Fermer TOUTES les positions maintenant ?")) return;
    try {
      const r = await closeAll();
      addLog(`CLOSE-ALL envoye (action humaine) : ${r.closed} position(s) fermee(s).`);
      await refresh();
    } catch (e) { setErr(String(e)); }
  };

  const strategy = rt?.strategy as { name?: string; fast?: number; slow?: number; timeframe?: string } | null;
  const enabled = rt?.config_enabled ?? false;
  const botLogs: LogLine[] = rt?.log ?? [];

  return (
    <main className="wrap">
      <div className="row" style={{ justifyContent: "space-between" }}>
        <h1>Forex Terminal</h1>
        <div className="row muted">
          <span><span className={`dot ${botOk ? "ok" : "ko"}`} /> Bot MT5 :8100</span>
          <span><span className={`dot ${ocOk ? "ok" : "ko"}`} /> OpenCode :4096</span>
        </div>
      </div>

      <div className="statusbar">
        <span className="muted">
          Compte : {rt?.account ? `#${rt.account.login} — ${rt.account.server}` : "en attente"}
        </span>
        <span className="muted">
          Config : v{rt?.config_version ?? "—"} ({enabled ? "ACTIVEE" : "desactivee"})
        </span>
        {strategy && (
          <span className="muted">
            Strategie : {strategy.name}
            {strategy.name === "ema_cross" && strategy.fast ? ` ${strategy.fast}/${strategy.slow}` : ""}
            {strategy.timeframe ? ` · ${strategy.timeframe}` : ""}
          </span>
        )}
        {rt?.kill_switch && <span style={{ color: "var(--danger)", fontWeight: 700 }}>KILL SWITCH</span>}
        {enabled && <span className="badge live">BOT ACTIF</span>}
      </div>

      {rt?.last_error && (
        <div className="err" style={{ marginTop: 0, marginBottom: 12 }}>
          <b>Config rejetee :</b> {rt.last_error}
        </div>
      )}

      <div className="grid">
        <div className="card"><div className="label">Equity</div>
          <div className="value">{rt?.account ? fmt(rt.account.equity) : "—"} {rt?.account?.currency ?? "$"}</div>
          <div className="sub">Balance {rt?.account ? fmt(rt.account.balance) : "—"}</div></div>
        <div className="card"><div className="label">PnL jour</div>
          <div className="value" style={{ color: (rt?.pnl_today_pct ?? 0) < 0 ? "var(--danger)" : "var(--accent)" }}>
            {fmt(rt?.pnl_today_pct)} %
          </div>
          <div className="sub">Realise + flottant</div></div>
        <div className="card"><div className="label">Positions</div>
          <div className="value">{rt?.positions.length ?? 0}</div>
          <div className="sub">Max {rt?.limits?.max_open_trades ?? 3}</div></div>
        <div className="card"><div className="label">Lot max</div>
          <div className="value">{fmt(rt?.limits?.max_lot, 3)}</div>
          <div className="sub">Perte max/jour {fmt(rt?.limits?.max_daily_loss_pct, 1)} %</div></div>
      </div>

      <section>
        <h2>Actions</h2>
        <div className="row">
          <button onClick={runAnalysis} disabled={busy || !ocOk}>
            {busy ? "Analyse en cours..." : "Analyse OpenCode -> bot_config.set"}
          </button>
          <button
            className={enabled ? "danger" : "secondary"}
            onClick={toggleEnabled}
            disabled={toggleBusy || !rt?.config_version}
          >
            {enabled ? "Desactiver le bot" : "Activer le bot"}
          </button>
          <button className="danger" onClick={emergencyClose}>CLOSE ALL (urgence)</button>
          <button className="secondary" onClick={() => { refresh(); refreshMarket(); }}>Rafraichir</button>
        </div>
        {err && <div className="err">{err}</div>}
      </section>

      <section>
        <h2>Marche (APIs publiques)</h2>
        <div className="grid">
          {quotes.map((q) => (
            <div className="card" key={q.symbol}>
              <div className="label">{q.symbol}</div>
              <div className="value">{q.price ? q.price.toFixed(5) : "—"}</div>
              <div className="sub" style={{ color: (q.change_pct ?? 0) < 0 ? "var(--danger)" : "var(--accent)" }}>
                {q.change_pct === null ? "—" : `${q.change_pct > 0 ? "+" : ""}${q.change_pct.toFixed(2)} %`}
              </div>
            </div>
          ))}
          {quotes.length === 0 && <div className="card muted">Chargement du marche...</div>}
        </div>
      </section>

      <div className="cols">
        <section>
          <h2>Calendrier economique</h2>
          <div className="card" style={{ maxHeight: 260, overflowY: "auto" }}>
            {calendar.length === 0 ? <div className="muted">Aucun evenement.</div> : calendar.map((e, i) => (
              <div className="line" key={i}>
                <span className={`impact ${(e.impact || "").toLowerCase()}`}>{e.impact || "-"}</span>
                <span className="grow">{e.title}</span>
                <span className="muted">{e.country}</span>
                <span className="muted">{e.date ? fmtEventDate(e) : ""}</span>
              </div>
            ))}
          </div>
        </section>

        <section>
          <h2>Actualites</h2>
          <div className="card" style={{ maxHeight: 260, overflowY: "auto" }}>
            {news.length === 0 ? <div className="muted">Aucune actualite.</div> : news.map((n, i) => (
              <div className="line" key={i}>
                <span className="grow">{n.title}</span>
                <span className="muted">{n.source}</span>
              </div>
            ))}
          </div>
        </section>
      </div>

      <section>
        <h2>Positions ouvertes</h2>
        <div className="card">
          {rt && rt.positions.length > 0 ? (
            <table>
              <thead><tr><th>Ticket</th><th>Symbole</th><th>Sens</th><th>Lot</th><th>Ouverture</th><th>SL</th><th>TP</th><th>PnL</th></tr></thead>
              <tbody>
                {rt.positions.map((p) => (
                  <tr key={p.ticket}>
                    <td>{p.ticket}</td><td>{p.symbol}</td><td>{p.side}</td>
                    <td>{p.lot}</td><td>{p.price_open}</td><td>{p.sl ?? "—"}</td><td>{p.tp ?? "—"}</td>
                    <td style={{ color: p.profit < 0 ? "var(--danger)" : "var(--accent)" }}>{p.profit}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : <div className="muted">Aucune position ouverte.</div>}
        </div>
      </section>

      <section>
        <h2>Journal du bot</h2>
        <div className="card" style={{ maxHeight: 240, overflowY: "auto", fontSize: 12 }}>
          {botLogs.length === 0 && log.length === 0 ? <div className="muted">— vide —</div> : null}
          {botLogs.slice().reverse().map((l, i) => (
            <div className="logline" key={`b${i}`}>
              <span className="muted">{l.ts}</span>{" "}
              <span className={`lvl ${l.level.toLowerCase()}`}>{l.level}</span>{" "}
              <span className="muted">[{l.source}]</span> {l.msg}
            </div>
          ))}
          {log.map((l, i) => (<div className="logline" key={`u${i}`}>{l}</div>))}
        </div>
      </section>
    </main>
  );
}
