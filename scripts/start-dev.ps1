# Forex Terminal — lancement en mode DEV (1 commande, 3 processus)
# Usage : powershell -ExecutionPolicy Bypass -File scripts\start-dev.ps1
$ErrorActionPreference = "Continue"
Set-Location (Split-Path $PSScriptRoot -Parent)

Write-Host "=== Forex Terminal — DEV ===" -ForegroundColor Cyan

# 1. Choisir un port libre pour opencode (un port fixe peut etre occupe)
$ocPort = 4096
foreach ($p in @(4096, 4097, 4098, 4099, 4100, 4180, 5280)) {
    $busy = Get-NetTCPConnection -LocalPort $p -State Listen -ErrorAction SilentlyContinue
    if (-not $busy) { $ocPort = $p; break }
}
$botPort = 8100
foreach ($p in @(8100, 8101, 8102, 8110, 8180)) {
    $busy = Get-NetTCPConnection -LocalPort $p -State Listen -ErrorAction SilentlyContinue
    if (-not $busy) { $botPort = $p; break }
}

# 2. Publier les ports pour le bot et le dashboard
$shared = if ($env:FOREX_TERMINAL_SHARED) { $env:FOREX_TERMINAL_SHARED } else { Join-Path (Get-Location) "shared" }
New-Item -ItemType Directory -Force -Path $shared | Out-Null
Set-Content -Path (Join-Path $shared "opencode.port") -Value $ocPort -NoNewline
Set-Content -Path (Join-Path $shared "bot.port") -Value $botPort -NoNewline
Write-Host "  opencode :$ocPort | bot :$botPort | shared :$shared" -ForegroundColor DarkGray

# 3. Dependances
if (-not (Test-Path node_modules)) { Write-Host "  npm install..." -ForegroundColor Yellow; npm install }
if (-not (Test-Path .venv)) { Write-Host "  creation du venv..." -ForegroundColor Yellow; python -m venv .venv }
& .\.venv\Scripts\python.exe -m pip install -q -r bot\requirements.txt 2>&1 | Out-Null

# 4. Demarrer
$env:FOREX_TERMINAL_SHARED = $shared
Write-Host "  demarrage du bot..." -ForegroundColor Cyan
Start-Process -FilePath ".\.venv\Scripts\python.exe" -ArgumentList "-u", "bot\main.py" -WindowStyle Hidden

Write-Host "  demarrage d'opencode..." -ForegroundColor Cyan
Start-Process -FilePath "opencode.cmd" -ArgumentList "serve", "--port", "$ocPort" -WindowStyle Hidden

Write-Host "  demarrage du dashboard..." -ForegroundColor Cyan
Start-Process -FilePath "npm.cmd" -ArgumentList "run", "dev" -WindowStyle Hidden

Start-Sleep -Seconds 12
Write-Host ""
Write-Host "  Dashboard : http://localhost:3000" -ForegroundColor Green
Write-Host "  Bot API   : http://127.0.0.1:$botPort" -ForegroundColor Green
Write-Host "  OpenCode  : http://127.0.0.1:$ocPort" -ForegroundColor Green
Write-Host "  Logs      : $shared\bot.log" -ForegroundColor DarkGray
Write-Host ""
Write-Host "  Arret : arrete les 3 processus (ou ferme cette fenetre)" -ForegroundColor DarkGray
