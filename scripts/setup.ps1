# Forex Terminal ? installation complete (Windows PowerShell)
# Usage : powershell -ExecutionPolicy Bypass -File scripts\setup.ps1
$ErrorActionPreference = "Continue"
Set-Location (Split-Path $PSScriptRoot -Parent)
Write-Host "=== Forex Terminal ? SETUP ===" -ForegroundColor Cyan

# 1. Controle prerequis
$need = @()
foreach ($c in @("node", "npm", "python", "git")) { if (-not (Get-Command $c -ErrorAction SilentlyContinue)) { $need += $c } }
if ($need) {
    Write-Host "Composants manquants : $($need -join ', ')" -ForegroundColor Yellow
    Write-Host "Installe-les puis relance ce script :" -ForegroundColor Yellow
    Write-Host "  winget install OpenJS.NodeJS.LTS" -ForegroundColor Green
    Write-Host "  winget install Python.Python.3.12" -ForegroundColor Green
    Write-Host "  winget install Git.Git" -ForegroundColor Green
    Write-Host "  winget install Rustlang.Rustup   # + Visual Studio Build Tools (MSVC)" -ForegroundColor Green
    Write-Host "  rustup default stable-x86_64-pc-windows-msvc" -ForegroundColor Green
}

# 2. Dependance Python du bot (mt5forge + API MetaTrader5 + FastAPI + MCP)
Write-Host "`n[2/6] Installation Python (mt5forge, MetaTrader5, FastAPI, mcp)..." -ForegroundColor Cyan
python -m pip install --upgrade pip
python -m pip install -r bot\requirements.txt
if ($LASTEXITCODE -ne 0) { Write-Host "  ATTENTION : une dependance a echoue (voir ci-dessus)." -ForegroundColor Yellow }

# 3. MCP scraping Wafle-Scraper (optionnel, utilise par OpenCode)
Write-Host "`n[3/6] Installation MCP scraping Wafle-Scraper (optionnel)..." -ForegroundColor Cyan
python -m pip install wafle-scraper
try { python -m playwright install chromium } catch { Write-Host "  playwright ignore (optionnel)" -ForegroundColor Yellow }

# 4. Dependance Node
Write-Host "`n[4/6] Installation Node (Next.js + Tauri CLI)..." -ForegroundColor Cyan
npm install

# 5. Skills design (clones, jamais recreees)
Write-Host "`n[5/6] Clonage des skills design dans .opencode\skill\..." -ForegroundColor Cyan
New-Item -ItemType Directory -Force -Path .opencode\skill | Out-Null
if (-not (Test-Path .opencode\skill\ui-skills))            { git clone --depth 1 https://github.com/ibelick/ui-skills                    .opencode\skill\ui-skills            } else { Write-Host "ui-skills deja present" }
if (-not (Test-Path .opencode\skill\agentic-ai-skills))    { git clone --depth 1 https://github.com/ismailgito/Agentic-AI-Skills        .opencode\skill\agentic-ai-skills    } else { Write-Host "agentic-ai-skills deja present" }
if (-not (Test-Path .opencode\skill\ui-ux-pro-max-skill))  { git clone --depth 1 https://github.com/nextlevelbuilder/ui-ux-pro-max-skill .opencode\skill\ui-ux-pro-max-skill } else { Write-Host "ui-ux-pro-max-skill deja present" }

# 6. OpenCode CLI
Write-Host "`n[6/6] OpenCode CLI..." -ForegroundColor Cyan
if (-not (Get-Command opencode -ErrorAction SilentlyContinue)) { npm i -g opencode-ai }

# 7. Verification du modele
Write-Host "`n[7/7] Verification du modele OpenCode..." -ForegroundColor Cyan
try {
    $models = opencode models 2>&1 | Out-String
    $used = (Get-Content opencode.json -Raw | ConvertFrom-Json).model
    if ($models -match [regex]::Escape($used)) {
        Write-Host "  modele '$used' disponible" -ForegroundColor Green
    } else {
        Write-Host "  ATTENTION : modele '$used' introuvable." -ForegroundColor Yellow
        Write-Host "  Change opencode.json -> .model avec un de : " -ForegroundColor Yellow
        ($models -split "`n" | Where-Object { $_ -match "free|grok" } | Select-Object -First 8) | ForEach-Object { Write-Host "    $_" -ForegroundColor Gray }
    }
} catch { Write-Host "  verification impossible (opencode models)" -ForegroundColor Yellow }

Write-Host "`n=== SETUP TERMINE ===" -ForegroundColor Cyan
Write-Host "Suivant :" -ForegroundColor Yellow
Write-Host "  1. Remplis shared\credentials.json (compte MT5 DEMO + serveur broker)" -ForegroundColor Gray
Write-Host "  2. opencode auth login  (modele OpenCode Zen / compte)" -ForegroundColor Gray
Write-Host "  3. Lance le bot seul  :  python -u bot\main.py   (API :8100)" -ForegroundColor Gray
Write-Host "  4. Lance le front seul :  npm run dev             (http://localhost:3000)" -ForegroundColor Gray
Write-Host "  5. build.bat  -> produit l'EXE Windows (necessite Rust + VS Build Tools)" -ForegroundColor Gray
Write-Host "  6. OU : pousse sur GitHub, les Actions compilent l'EXE tout seuls" -ForegroundColor Gray
