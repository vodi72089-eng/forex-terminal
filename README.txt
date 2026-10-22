# Forex Terminal — passe a l'action

Terminal de trading Forex desktop : **Tauri 2 + Next.js 15 + bot Python MT5 +
agent OpenCode**. L'IA analyse le marche et propose une configuration ; le bot
est seul autorise a passer des ordres.

```
┌─ Tauri 2 (Rust) ───────────────────────────────┐
│  lance opencode serve (:4096) + bot/main.py (:8100)
├─ Next.js 15 / React 19 (export statique) ───────┤
│  dashboard : equity, PnL, positions, marche, actus
├─ OpenCode — agent "market-analyst" ─────────────┤
│  MCP market-data : APIs de marche publiques
│  AUCUN acces a MT5, AUCUN ecriture fichier
└─ Bot Python (FastAPI :8100) ────────────────────┘
   seul a parler a MetaTrader5
   bot_config.set (IA) ──> validation ──> ordres
   bot_runtime.json (bot) ──> dashboard + agent
```

## Separation des pouvoirs (le coeur du projet)

| Acteur | Peut | Ne peut PAS |
|---|---|---|
| Agent IA | proposer `bot_config.set`, lire le marche | passer un ordre, ecrire un fichier, executer du bash |
| Bot | valider + executer, ecrire le runtime | assouplir les limites |
| Humain | activer/desactiver le bot, CLOSE ALL | — |

Garde-fous dans le **code** (indepsendants de la config) :
`max_lot <= 0.10`, `max <= 3 positions`, `perte journaliere <= 3%`,
`sl_pips 5..500`, `tp_pips 5..1000`, kill-switch automatique, refus si spread
trop large, cooldown apres chaque ordre. Politique **clamp-only** : l'IA ne peut
que RESSERRER, jamais assouplir.

## APIs de marche utilisees (toutes PUBLIQUES, sans cle, gratuites)

| Source | Usage | Endpoint |
|---|---|---|
| open.er-api.com | taux de change live | `https://open.er-api.com/v6/latest/USD` |
| Frankfurter (BCE) | taux de reference | `https://api.frankfurter.app/latest` |
| BCE XML | taux officiels | `https://www.ecb.europa.eu/stats/eurofxref/eurofxref-daily.xml` |
| Yahoo Finance | chandeliers OHLC + quotes | `https://query1.finance.yahoo.com/v8/finance/chart/EURUSD=X` |
| ForexFactory | calendrier economique | `https://nfs.faireconomy.media/ff_calendar_thisweek.json` |
| Google News RSS | actualites Forex | `https://news.google.com/rss/search?q=forex+EURUSD` |

Elles alimentent le MCP `market-data` (cote agent) ET le dashboard.

---

## OPTION A — GitHub Actions compile l'EXE pour toi (recommande)

Le kit contient `.github/workflows/build-exe.yml` : GitHub compile l'EXE sur un
runner Windows officiel et le publie dans les Releases.

```powershell
powershell -ExecutionPolicy Bypass -File scripts\push-github.ps1 `
  -Token ghp_TON_TOKEN `
  -RepoUrl https://github.com/TON_USER/forex-terminal.git
```

Puis onglet **Actions** -> le build demarre tout seul (10-20 min).
Une fois vert : onglet **Releases** -> `forex-terminal.exe` +
`forex-terminal_0.1.0_x64-setup.exe`, telechargeable sans compte GitHub.

## OPTION B — Compiler en local

### Etape 1 — Prerequis Windows (une seule fois)

```powershell
winget install OpenJS.NodeJS.LTS
winget install Python.Python.3.12
winget install Git.Git
winget install Rustlang.Rustup
winget install Microsoft.VisualStudio.2022.BuildTools --override "--quiet --add Microsoft.VisualStudio.Workload.VCTools --includeRecommended"
rustup default stable-x86_64-pc-windows-msvc
```

Verifie : `node -v`, `python --version`, `cargo -V`.

### Etape 2 — Setup

```powershell
powershell -ExecutionPolicy Bypass -File scripts\setup.ps1
```

Installe : `mt5forge`, `MetaTrader5`, `FastAPI`, `uvicorn`, `mcp` (serveur MCP),
`wafle-scraper`, les deps npm, les 3 skills design, et `opencode-ai`.

Ensuite :

1. `shared\credentials.json` : `login` / `password` / `server` de ton compte
   MT5 **DEMO** (jamais reel au debut). `bot_token` : garde `dev-token-local`.
   En app installee, ce fichier est dans
   `%APPDATA%\com.forex.terminal\shared\credentials.json`.
2. `opencode auth login` puis `opencode models` pour verifier le modele.
   Le modele par defaut est `opencode/grok-4.7` (`opencode.json` -> `.model`).

### Etape 3 — Lancer

```powershell
python -u bot\main.py     # bot MT5 + API :8100
opencode serve --port 4096   # agent + MCP market-data
npm run dev               # dashboard : http://localhost:3000
```

ou `scripts\build.bat` pour l'EXE (sortie :
`src-tauri\target\release\forex-terminal.exe`).

### Installation de l'EXE : ce qu'il faut savoir

L'EXE est un **lanceur**. Au premier lancement il demarre opencode + le bot.
Il faut sur la machine cible :

- **Python 3.10+** dans le PATH (`winget install Python.Python.3.12`)
- les deps Python : `pip install -r bot\requirements.txt`
- **MetaTrader 5** installe et connecte
- `npm i -g opencode-ai` (ou `opencode` dans le PATH)

Les donnees ecrites (config, runtime, credentials, logs) vont dans
`%APPDATA%\com.forex.terminal\` — **pas** dans `Program Files` (lecture seule).
Logs : `%APPDATA%\com.forex.terminal\bot.log` et `opencode.log`.

## Contenu du kit

```
bot/        module MT5 Python (config_protocol, strategy, trader, market_data)
mcp/        serveur MCP market-data (outils pour l'agent)
src/        dashboard Next.js (export statique)
src-tauri/  coquille Tauri 2
shared/     protocole fichiers (bot_config.set / bot_runtime.json / credentials.json)
opencode.json + AGENTS.md   agent analyste + permissions
.opencode/skill/            skills design (clones via setup.ps1)
```

## Strategies disponibles

| `strategy.name` | Parametres | Logique |
|---|---|---|
| `ema_cross` | `fast`, `slow`, `timeframe` | EMA fast au-dessus de EMA slow = etat haussier |
| `rsi_reversion` | `period`, `oversold`, `overbought` | survente / surachat = retour a la moyenne |
| `breakout` | `lookback` | cloture hors du range des N barres precedentes |

Le signal est un **etat**, pas un evenement : le bot peut re-entrer apres un
SL/TP (`allow_reentry`), tout en refusant d'empiler une position sur un
symbole deja ouvert.

## Securite

- L'IA n'a AUCUN acces a MetaTrader5 : elle ne fait que proposer un JSON.
- Le bot valide le FICHIER ENTIER avant application (rejet total si partiel).
- Limites clamp-only reappliquees dans le code a chaque ordre.
- Bouton CLOSE ALL = action humaine uniquement.
- **TESTE EN COMPTE DEMO d'abord. Toujours.**
