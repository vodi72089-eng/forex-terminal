"use client";

import { useCallback, useEffect, useState } from "react";
import { getRuntime, health, closeAll, type Runtime } from "@/lib/bot";
import { ocHealth, analyzeAndPropose } from "@/lib/opencode";

export default function Page() {
  const [rt, setRt] = useState<Runtime | null>(null);
  const [botOk, setBotOk] = useState(false);
  const [ocOk, setOcOk] = useState(false);
  const [busy, setBusy] = useState(false);
  const [log, setLog] = useState<string[]>([]);
  const [err, setErr] = useState<string | null>(null);

  const addLog = (m: string) =>
    setLog((l) => [`${new Date().toLocaleTimeString()} — ${m}`, ...l].slice(0, 30));

  const refresh = useCallback(async () => {
    try {
      setBotOk((await health()).ok);
    } catch { setBotOk(false); }
    try {
      setOcOk(Boolean((await ocHealth() as { healthy?: boolean }).healthy));
    } catch { setOcOk(false); }
    try {
      setRt(await getRuntime());
      setErr(null);
    } catch (e) { setErr(String(e)); }
  }, []);

  useEffect(() => {
    refresh();
    const t = setInterval(refresh, 2000);
    return () => clearInterval(t);
  }, [refresh]);

  const runAnalysis = async () => {
    setBusy(true); setErr(null);
    addLog("Analyse OpenCode lancee (market-analyst)...");
    try {
      const r = await analyzeAndPropose(
        "Analyse le marche actuel et propose une configuration adaptée. " +
          "Resserre les risques si la volatilite est elevee.",
      );
      addLog(r.applied
        ? "bot_config.set valide et applique par le bot."
        : "bot_config.set REJETE par la validation (fichier entier).");
    } catch (e) {
      addLog(`Erreur analyse : ${String(e)}`);
      setErr(String(e));
    } finally { setBusy(false); }
  };

  const emergencyClose = async () => {
    if (!confirm("Fermer TOUTES les positions maintenant ?")) return;
    await closeAll();
    addLog("CLOSE-ALL envoye (action humaine).");
  };

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
          Config : v{rt?.config_version ?? "—"} ({rt?.config_enabled ? "ACTIVEE" : "desactivee"})
        </span>
        {rt?.kill_switch && <span style={{ color: "var(--danger)", fontWeight: 700 }}>KILL SWITCH</span>}
      </div>

      <div className="grid">
        <div className="card"><div className="label">Equity</div>
          <div className="value">{rt?.account ? rt.account.equity.toFixed(2) : "—"} $</div></div>
        <div className="card"><div className="label">Balance</div>
          <div className="value">{rt?.account ? rt.account.balance.toFixed(2) : "—"} $</div></div>
        <div className="card"><div className="label">PnL flottant</div>
          <div className="value" style={{ color: (rt?.pnl_today_pct ?? 0) < 0 ? "var(--danger)" : "var(--accent)" }}>
            {(rt?.pnl_today_pct ?? 0).toFixed(2)} %
          </div></div>
        <div className="card"><div className="label">Positions</div>
          <div className="value">{rt?.positions.length ?? 0}</div></div>
      </div>

      <section>
        <h2>Actions</h2>
        <div className="row">
          <button onClick={runAnalysis} disabled={busy || !ocOk}>
            {busy ? "Analyse en cours..." : "Analyse OpenCode -> bot_config.set"}
          </button>
          <button className="danger" onClick={emergencyClose}>CLOSE ALL (urgence)</button>
          <button className="secondary" onClick={refresh}>Rafraichir</button>
        </div>
        {err && <div className="err">{err}</div>}
      </section>

      <section>
        <h2>Positions ouvertes</h2>
        <div className="card">
          {rt && rt.positions.length > 0 ? (
            <table>
              <thead><tr><th>Ticket</th><th>Symbole</th><th>Sens</th><th>Lot</th><th>Ouverture</th><th>PnL</th></tr></thead>
              <tbody>
                {rt.positions.map((p) => (
                  <tr key={p.ticket}>
                    <td>{p.ticket}</td><td>{p.symbol}</td><td>{p.side}</td>
                    <td>{p.lot}</td><td>{p.price_open}</td>
                    <td style={{ color: p.profit < 0 ? "var(--danger)" : "var(--accent)" }}>{p.profit}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : <div className="muted">Aucune position ouverte.</div>}
        </div>
      </section>

      <section>
        <h2>Journal</h2>
        <div className="card muted" style={{ maxHeight: 220, overflowY: "auto", fontSize: 12 }}>
          {log.length === 0 ? "— vide —" : log.map((l, i) => <div key={i}>{l}</div>)}
        </div>
      </section>
    </main>
  );
}
