# Forex Terminal — installation complete (Windows PowerShell)
# Usage : powershell -ExecutionPolicy Bypass -File scripts\setup.ps1
$ErrorActionPreference = "Continue"
Write-Host "=== Forex Terminal — SETUP ===" -ForegroundColor Cyan

# 1. Controle prerequis
$need = @()
foreach ($c in @("node","npm","python","git")) { if (-not (Get-Command $c -ErrorAction SilentlyContinue)) { $need += $c } }
if ($need) {
    Write-Host "Composants manquants : $($need -join ', ')" -ForegroundColor Yellow
    Write-Host "Installe-les puis relance ce script :" -ForegroundColor Yellow
    Write-Host "  winget install OpenJS.NodeJS.LTS" -ForegroundColor Green
    Write-Host "  winget install Python.Python.3.12" -ForegroundColor Green
    Write-Host "  winget install Git.Git" -ForegroundColor Green
    Write-Host "  winget install Rustlang.Rustup   # + Visual Studio Build Tools (MSVC)" -ForegroundColor Green
    Write-Host "  rustup default stable-x86_64-pc-windows-msvc" -ForegroundColor Green
}

# 2. Dependance Python du bot (mt5forge + API MetaTrader5, Windows only)
Write-Host "`n[2/6] Installation Python (mt5forge, MetaTrader5, FastAPI)..."
pip install -r bot\requirements.txt

# 3. MCP scraping Wafle-Scraper (utilise par OpenCode)
Write-Host "`n[3/6] Installation MCP scraping Wafle-Scraper..."
pip install wafle-scraper
try { playwright install chromium } catch { python -m playwright install chromium }

# 4. Dependance Node
Write-Host "`n[4/6] Installation Node (Next.js + Tauri CLI)..."
npm install

# 5. Skills design (clones, jamais recreees)
Write-Host "`n[5/6] Clonage des skills design dans .opencode\skill\..."
New-Item -ItemType Directory -Force -Path .opencode\skill | Out-Null
if (-not (Test-Path .opencode\skill\ui-skills))              { git clone --depth 1 https://github.com/ibelick/ui-skills                    .opencode\skill\ui-skills }              else { Write-Host "ui-skills deja present" }
if (-not (Test-Path .opencode\skill\agentic-ai-skills))      { git clone --depth 1 https://github.com/ismailgito/Agentic-AI-Skills        .opencode\skill\agentic-ai-skills }      else { Write-Host "agentic-ai-skills deja present" }
if (-not (Test-Path .opencode\skill\ui-ux-pro-max-skill))    { git clone --depth 1 https://github.com/nextlevelbuilder/ui-ux-pro-max-skill .opencode\skill\ui-ux-pro-max-skill }  else { Write-Host "ui-ux-pro-max-skill deja present" }

# 6. OpenCode CLI
Write-Host "`n[6/6] OpenCode CLI..."
if (-not (Get-Command opencode -ErrorAction SilentlyContinue)) { npm i -g opencode-ai }
Write-Host "`n=== SETUP TERMINE ===" -ForegroundColor Cyan
Write-Host "Suivant :" -ForegroundColor Yellow
Write-Host "  1. Remplis shared\credentials.json (compte MT5 DEMO + serveur broker)"
Write-Host "  2. opencode auth login  (modele gratuit OpenCode Zen)"
Write-Host "  3. opencode models      -> verifie le modele gratuit, ajuste opencode.json si besoin"
Write-Host "  4. build.bat            -> produit l'EXE Windows"
