# Forex Terminal - lancement en mode DEV (1 commande, 3 processus)
# Usage : powershell -ExecutionPolicy Bypass -File scripts\start-dev.ps1
#
# NOTE : ce fichier est en ASCII + BOM UTF-8. Windows PowerShell 5.1 lit les
# .ps1 sans BOM en ANSI (CP1252) : un tiret cadratin UTF-8 (E2 80 94) devient
# alors le byte 0x94 = un guillemet double, ce qui casse le parsing.
$ErrorActionPreference = "Continue"
Set-Location (Split-Path $PSScriptRoot -Parent)

Write-Host "=== Forex Terminal - DEV ===" -ForegroundColor Cyan

# 1. Choisir un port libre pour opencode et pour le bot
#    (un port fixe peut etre occupe par un processus etranger)
function Get-FreePort([int[]]$candidates) {
    foreach ($p in $candidates) {
        $busy = Get-NetTCPConnection -LocalPort $p -State Listen -ErrorAction SilentlyContinue
        if (-not $busy) { return $p }
    }
    return $candidates[0]
}
$ocPort  = Get-FreePort @(4096, 4097, 4098, 4099, 4100, 4180, 5280)
$botPort = Get-FreePort @(8100, 8101, 8102, 8110, 8180)

# 2. Publier les ports pour le bot et le dashboard
$shared = if ($env:FOREX_TERMINAL_SHARED) { $env:FOREX_TERMINAL_SHARED } else { Join-Path (Get-Location) "shared" }
New-Item -ItemType Directory -Force -Path $shared | Out-Null
Set-Content -Path (Join-Path $shared "opencode.port") -Value $ocPort -NoNewline
Set-Content -Path (Join-Path $shared "bot.port") -Value $botPort -NoNewline
$env:FOREX_TERMINAL_SHARED = $shared
Write-Host "  opencode :$ocPort  |  bot :$botPort  |  shared :$shared" -ForegroundColor DarkGray

# 3. Dependances
if (-not (Test-Path node_modules)) {
    Write-Host "  npm install..." -ForegroundColor Yellow
    npm install
}
$py = Join-Path (Get-Location) ".venv\Scripts\python.exe"
if (-not (Test-Path $py)) {
    Write-Host "  creation du venv..." -ForegroundColor Yellow
    python -m venv .venv
    $py = Join-Path (Get-Location) ".venv\Scripts\python.exe"
}
& $py -m pip install -q -r bot\requirements.txt 2>&1 | Out-Null

# 4. Demarrer les 3 processus
Write-Host "  demarrage du bot..." -ForegroundColor Cyan
Start-Process -FilePath $py -ArgumentList "-u", "bot\main.py" -WorkingDirectory (Get-Location) -WindowStyle Hidden

Write-Host "  demarrage d opencode..." -ForegroundColor Cyan
$oc = Get-Command opencode.cmd -ErrorAction SilentlyContinue
if (-not $oc) { $oc = Get-Command opencode -ErrorAction SilentlyContinue }
if ($oc) {
    Start-Process -FilePath $oc.Source -ArgumentList "serve", "--port", "$ocPort" -WorkingDirectory (Get-Location) -WindowStyle Hidden
} else {
    Write-Host "  opencode introuvable : npm i -g opencode-ai" -ForegroundColor Yellow
}

Write-Host "  demarrage du dashboard..." -ForegroundColor Cyan
$npm = Get-Command npm.cmd -ErrorAction SilentlyContinue
if (-not $npm) { $npm = Get-Command npm -ErrorAction SilentlyContinue }
if ($npm) {
    Start-Process -FilePath $npm.Source -ArgumentList "run", "dev" -WorkingDirectory (Get-Location) -WindowStyle Hidden
}

# 5. Verifier que ca repond
Start-Sleep -Seconds 14
$botOk = $false
try { $null = Invoke-RestMethod "http://127.0.0.1:$botPort/health" -TimeoutSec 5; $botOk = $true } catch {}
$ocOk = $false
try { $null = Invoke-RestMethod "http://127.0.0.1:$ocPort/global/health" -TimeoutSec 5; $ocOk = $true } catch {}

Write-Host ""
Write-Host "  Dashboard : http://localhost:3000" -ForegroundColor Green
Write-Host "  Bot API   : http://127.0.0.1:$botPort  $(if ($botOk) { '[OK]' } else { '[KO - voir les logs]' })" -ForegroundColor $(if ($botOk) { "Green" } else { "Yellow" })
Write-Host "  OpenCode  : http://127.0.0.1:$ocPort  $(if ($ocOk) { '[OK]' } else { '[KO]' })" -ForegroundColor $(if ($ocOk) { "Green" } else { "Yellow" })
Write-Host "  Logs      : $shared\bot.log" -ForegroundColor DarkGray
Write-Host ""
Write-Host "  ATTENTION : ne lance pas 'npm run build' pendant que le serveur dev" -ForegroundColor Yellow
Write-Host "  tourne (ca ecrase .next/ et le serveur dev se corrompt)." -ForegroundColor Yellow
Write-Host ""
Write-Host "  Arret : ferme les 3 processus (ou cette fenetre)" -ForegroundColor DarkGray
