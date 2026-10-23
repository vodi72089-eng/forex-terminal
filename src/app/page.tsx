"use client";

import { useCallback, useEffect, useState } from "react";
import {
  BOT, BOT_PORTS, applyStrategy, botUnreachable, closeAll, connectMt5, getConfig,
  getMt5Status, getSnapshot, getRuntime, getStrategies, health, saveMt5Credentials,
  setEnabled,
  type CalendarEvent, type LogLine, type Mt5Status, type NewsItem, type Quote,
  type Runtime, type StrategyDef, type StrategiesPayload,
} from "@/lib/bot";
import { analyzeAndPropose, ocHealth, opencodePortLabel } from "@/lib/opencode";
import Chat from "./chat";

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
  const [mt5Ok, setMt5Ok] = useState(false);
  const [ocOk, setOcOk] = useState(false);
  const [busy, setBusy] = useState(false);
  const [toggleBusy, setToggleBusy] = useState(false);
  const [log, setLog] = useState<string[]>([]);
  const [err, setErr] = useState<string | null>(null);
  const [quotes, setQuotes] = useState<Quote[]>([]);
  const [calendar, setCalendar] = useState<CalendarEvent[]>([]);
  const [news, setNews] = useState<NewsItem[]>([]);
  const [cfg, setCfg] = useState<Record<string, unknown> | null>(null);
  const [mt5, setMt5] = useState<Mt5Status | null>(null);
  const [mt5Busy, setMt5Busy] = useState(false);
  const [creds, setCreds] = useState({ login: "", password: "", server: "" });
  const [strategies, setStrategies] = useState<StrategiesPayload | null>(null);
  const [stratName, setStratName] = useState("");
  const [stratParams, setStratParams] = useState<Record<string, string>>({});
  const [stratTf, setStratTf] = useState("M5");
  const [stratBusy, setStratBusy] = useState(false);

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
    // "bot vivant" = le bot repond (HTTP 200). "MT5 connecte" = health().ok.
    // Ces deux notions sont differentes : sans identifiants MT5, le bot
    // repond parfaitement mais health().ok vaut false.
    setBotOk(h.status === "fulfilled");
    setMt5Ok(h.status === "fulfilled" && Boolean(h.value?.ok));
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

  useEffect(() => {
    getMt5Status().then((s) => {
      setMt5(s);
      setCreds((c) => (c.login ? c : { ...c, login: String(s.login || ""), server: s.server || "" }));
    }).catch(() => {});
  }, [rt?.ts]);

  useEffect(() => {
    getStrategies().then((s) => {
      setStrategies(s);
      const cur = (s.current?.name as string) || s.available[0]?.name || "";
      setStratName(cur);
      setStratTf((s.current?.timeframe as string) || "M5");
      const def = s.available.find((d) => d.name === cur);
      const p: Record<string, string> = {};
      for (const [k, v] of Object.entries(def?.params ?? {})) {
        const cur2 = (s.current as Record<string, unknown> | null)?.[k];
        p[k] = String(cur2 ?? v.default);
      }
      setStratParams(p);
    }).catch(() => {});
  }, [rt?.config_version]);

  const doConnectMt5 = async () => {
    setMt5Busy(true);
    try {
      const r = await connectMt5();
      setMt5(r.status);
      addLog("Reconnexion MT5 demandee.");
    } catch (e) {
      addLog(`Erreur connexion MT5 : ${String(e)}`);
    } finally { setMt5Busy(false); }
  };

  const doSaveCreds = async () => {
    setMt5Busy(true);
    try {
      const r = await saveMt5Credentials({
        login: Number(creds.login) || 0,
        password: creds.password,
        server: creds.server,
      });
      setMt5(r.status);
      setCreds((c) => ({ ...c, password: "" }));
      addLog("Identifiants MT5 enregistres, reconnexion en cours...");
    } catch (e) {
      addLog(`Erreur identifiants : ${String(e)}`);
      setErr(String(e));
    } finally { setMt5Busy(false); }
  };

  const doApplyStrategy = async () => {
    setStratBusy(true);
    try {
      const params: Record<string, unknown> = {};
      for (const [k, v] of Object.entries(stratParams)) {
        const def = strategies?.available.find((d) => d.name === stratName)?.params[k];
        if (def?.type === "bool") params[k] = v === "true";
        else if (def?.type === "int") params[k] = parseInt(v, 10);
        else params[k] = parseFloat(v);
      }
      const r = await applyStrategy({ name: stratName, timeframe: stratTf, params });
      addLog(`Strategie appliquee : ${r.strategy?.name} (v${r.version})`);
      await refresh();
    } catch (e) {
      addLog(`Erreur strategie : ${String(e)}`);
      setErr(String(e));
    } finally { setStratBusy(false); }
  };

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
  const stale = rt !== null && !botOk;

  return (
    <main className="wrap">
      <div className="row" style={{ justifyContent: "space-between" }}>
        <h1>Forex Terminal</h1>
        <div className="row muted">
          <span title={`ports testes : ${BOT_PORTS.join(", ")}`}>
            <span className={`dot ${botOk ? "ok" : "ko"}`} /> Bot MT5
          </span>
          <span>
            <span className={`dot ${ocOk ? "ok" : "ko"}`} /> OpenCode
          </span>
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
        {botOk && !mt5Ok && <span className="badge warn">MT5 NON CONNECTE</span>}
        {stale && <span className="badge dead">BOT ARRETE</span>}
      </div>

      {rt?.last_error && (
        <div className="err" style={{ marginTop: 0, marginBottom: 12 }}>
          <b>Config rejetee :</b> {rt.last_error}
        </div>
      )}

      {botOk && !mt5Ok && (
        <div className="warnbox">
          <b>MT5 non connecte.</b>{" "}
          Le bot fonctionne, mais MetaTrader 5 n&apos;est pas connecte au compte.
          Verifie <code>shared\\credentials.json</code> (login / password / server d&apos;un compte{" "}
          <b>DEMO</b>) et que le terminal MetaTrader 5 est lance et connecte.
        </div>
      )}

      {!botOk && (
        <div className="warnbox">
          <b>{stale ? "Bot arrete — donnees figees." : "Le bot ne repond pas."}</b>{" "}
          {botUnreachable()
            ? `Aucun bot trouve sur les ports ${BOT_PORTS.join(", ")}. Verifie les logs : %APPDATA%\\com.forex.terminal\\bot.log.err`
            : `Tentative sur ${BOT} (${BOT_PORTS.join(", ")}). Le bot met quelques secondes a demarrer.`}
          {" "}Relance l'application (ou le bot : <code>python -u bot\\main.py</code>).
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

      <Chat onApplied={refresh} onStrategiesChanged={refresh} />

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
        <div className="muted" style={{ marginTop: 8, fontSize: 11 }}>
          Bot : {BOT} (ports {BOT_PORTS.join(", ")}) · OpenCode : {opencodePortLabel()} ·
          Logs : %APPDATA%\com.forex.terminal\
        </div>
      </section>

      <section>
        <h2>Connexion MetaTrader 5</h2>
        <div className="card">
          <div className="row" style={{ justifyContent: "space-between" }}>
            <div>
              <span className={`dot ${mt5?.connected ? "ok" : "ko"}`} />{" "}
              <b>{mt5?.connected ? "Connecte" : "Non connecte"}</b>
              {mt5?.account && (
                <span className="muted">
                  {" "}— {mt5.account.name} (#{mt5.account.login}) chez {mt5.account.server}
                  {" "}[{mt5.account.currency}]
                </span>
              )}
            </div>
            <button className="secondary" onClick={doConnectMt5} disabled={mt5Busy}>
              {mt5Busy ? "Connexion..." : "Connecter MT5"}
            </button>
          </div>
          {mt5?.last_error && (
            <div className="muted" style={{ marginTop: 8, fontSize: 12 }}>
              {mt5.last_error} — {mt5.attempts} tentative(s)
            </div>
          )}
          <div className="row" style={{ marginTop: 12 }}>
            <input
              className="inp" placeholder="Login (numero de compte)"
              value={creds.login}
              onChange={(e) => setCreds({ ...creds, login: e.target.value })}
            />
            <input
              className="inp" type="password" placeholder="Mot de passe"
              value={creds.password}
              onChange={(e) => setCreds({ ...creds, password: e.target.value })}
            />
            <input
              className="inp" placeholder="Server (ex: Broker-Demo)"
              value={creds.server}
              onChange={(e) => setCreds({ ...creds, server: e.target.value })}
            />
            <button onClick={doSaveCreds} disabled={mt5Busy || !creds.server}>
              Enregistrer + connecter
            </button>
          </div>
          <div className="muted" style={{ marginTop: 8, fontSize: 11 }}>
            Utilise un compte <b>DEMO</b>. Fichier : {mt5?.credentials_path ?? "shared/credentials.json"}
          </div>
        </div>
      </section>

      <section>
        <h2>Strategie</h2>
        <div className="card">
          {strategies && strategies.available.length === 0 && (
            <div className="muted">Aucune strategie chargee.</div>
          )}
          <div className="row">
            <select
              className="inp" value={stratName}
              onChange={(e) => {
                setStratName(e.target.value);
                const def = strategies?.available.find((d) => d.name === e.target.value);
                const p: Record<string, string> = {};
                for (const [k, v] of Object.entries(def?.params ?? {})) {
                  p[k] = String(v.default);
                }
                setStratParams(p);
              }}
            >
              {strategies?.available.map((d) => (
                <option key={d.name} value={d.name}>
                  {d.name}{d.builtin ? "" : " (perso)"}
                </option>
              ))}
            </select>
            <select className="inp" value={stratTf} onChange={(e) => setStratTf(e.target.value)}>
              {strategies?.timeframes.map((t) => <option key={t} value={t}>{t}</option>)}
            </select>
            {Object.entries(stratParams).map(([k, v]) => {
              const def = strategies?.available.find((d) => d.name === stratName)?.params[k];
              if (def?.type === "bool") {
                return (
                  <label key={k} className="muted" style={{ fontSize: 12 }}>
                    <input
                      type="checkbox" checked={v === "true"}
                      onChange={(e) => setStratParams({ ...stratParams, [k]: String(e.target.checked) })}
                    />{" "}{def.label}
                  </label>
                );
              }
              return (
                <input
                  key={k} className="inp short" type="number" placeholder={def?.label ?? k}
                  value={v}
                  onChange={(e) => setStratParams({ ...stratParams, [k]: e.target.value })}
                />
              );
            })}
            <button onClick={doApplyStrategy} disabled={stratBusy || !stratName}>
              {stratBusy ? "Application..." : "Appliquer"}
            </button>
          </div>
          <div className="muted" style={{ marginTop: 8, fontSize: 12 }}>
            {strategies?.available.find((d) => d.name === stratName)?.description}
          </div>
          <div className="muted" style={{ marginTop: 6, fontSize: 11 }}>
            Tes strategies : depose un fichier <code>.py</code> dans{" "}
            <code>{strategies?.user_dir}</code> puis redemarre le bot — elle
            apparait ici automatiquement.
          </div>
        </div>
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
