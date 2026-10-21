# Forex Terminal — passe a l'action

## OPTION A — GitHub Actions compile l'EXE pour toi (recommande, rien a installer)

Le kit contient deja `.github/workflows/build-exe.yml` : GitHub compile l'EXE
sur un runner Windows officiel et le publie dans les Releases du repo.

1. Cree un repo vide sur github.com (public), par ex. `forex-terminal`.
2. Depuis le dossier kit dezippe :
   ```
   powershell -ExecutionPolicy Bypass -File scripts\push-github.ps1 ^
     -Token ghp_TON_TOKEN ^
     -RepoUrl https://github.com/TON_USER/forex-terminal.git
   ```
   (token avec scopes `repo` + `workflow` — cree sur github.com/settings/tokens)
3. Ouvre l'onglet **Actions** du repo : le build demarre tout seul (10-20 min).
4. Une fois le build vert : onglet **Releases** ->
   `forex-terminal.exe` + `forex-terminal_0.1.0_x64-setup.exe` — telechargeable
   directement, meme sans compte GitHub.

## OPTION B — Compiler en local (3 etapes)

### Etape 1 — Prerequis Windows (une seule fois)
Ouvre PowerShell (normal, pas admin) et colle :

```
winget install OpenJS.NodeJS.LTS
winget install Python.Python.3.12
winget install Git.Git
winget install Rustlang.Rustup
winget install Microsoft.VisualStudio.2022.BuildTools --override "--quiet --add Microsoft.VisualStudio.Workload.VCTools --includeRecommended"
rustup default stable-x86_64-pc-windows-msvc
```

Redemarre le terminal. Verifie : `node -v`, `python --version`, `cargo -V`.

### Etape 2 — Unzip + setup
Dezipe ce dossier, ouvre PowerShell DANS le dossier `forex-terminal` puis :

```
powershell -ExecutionPolicy Bypass -File scripts\setup.ps1
```

Ca installe : mt5forge + MetaTrader5 (pip), Wafle-Scraper (MCP scraping),
les dependances npm, les 3 skills design (clones GitHub), et opencode-ai.

Ensuite, personnalise `shared\credentials.json` :
- `login` / `password` / `server` : ton compte MT5 **DEMO** (jamais reel au debut)
- `bot_token` : laisse `dev-token-local`

Puis : `opencode auth login` (compte OpenCode Zen gratuit) et `opencode models`
pour verifier le modele gratuit (par defaut `opencode/grok-code` dans opencode.json).

### Etape 3 — Build de l'EXE
```
scripts\build.bat
```

Resultat :
- `src-tauri\target\release\forex-terminal.exe` — l'application
- `src-tauri\target\release\bundle\nsis\forex-terminal_0.1.0_x64-setup.exe` — l'installeur

Au premier lancement, l'EXE demarre lui-meme :
- OpenCode en mode serveur (`opencode serve --port 4096`)
- le bot MT5 Python embarque (API locale 127.0.0.1:8100)

## Securite (deja implantee dans le code)
- L'IA n'a AUCUN acces a MetaTrader5 : elle ne peut que proposer `shared/bot_config.set`.
- Le bot valide le FICHIER ENTIER avant application (rejet total si partiel/corrompu).
- Limites strictes re-appliquees dans le code a chaque ordre (clamp-only) :
  max_lot 0.10, max 3 positions, perte journaliere max 3%, kill-switch automatique.
- Bouton CLOSE ALL = action humaine uniquement.
- TESTE EN COMPTE DEMO d'abord. Toujours.

## Contenu du kit
- `bot/` : module MT5 Python embarque (mt5forge, reconnexion auto, guardrails)
- `src/` : dashboard Next.js (export statique, embarque dans l'EXE)
- `src-tauri/` : coquille Tauri 2 (compile l'EXE, lance les 2 sidecars)
- `shared/` : protocole fichiers `bot_config.set` / `bot_runtime.json`
- `opencode.json` + `AGENTS.md` : agent analyste + MCP Wafle-Scraper
- `.opencode/skill/` : skills design (clones via setup.ps1)
