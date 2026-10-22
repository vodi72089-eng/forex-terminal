# Push du kit vers GitHub -> les Actions GitHub compilent l'EXE automatiquement
# Usage :
#   powershell -ExecutionPolicy Bypass -File scripts\push-github.ps1 -Token ghp_xxx -RepoUrl https://github.com/TON_USER/forex-terminal.git
param(
  [Parameter(Mandatory = $true)][string]$Token,
  [Parameter(Mandatory = $true)][string]$RepoUrl
)
$ErrorActionPreference = "Stop"
Set-Location (Split-Path $PSScriptRoot -Parent)

Write-Host "=== [1/3] Commit du kit ===" -ForegroundColor Cyan
git init -b main 2>$null
git add -A
git commit -m "Forex Terminal v0.1.0 - kit complet + workflow build EXE" 2>$null
git branch -M main

Write-Host "=== [2/3] Remote + push (token injecte, jamais commite) ===" -ForegroundColor Cyan
$authUrl = $RepoUrl -replace "^https://", "https://x-access-token:$Token@"
git remote remove origin 2>$null
git remote add origin $authUrl
git push -u origin main
# securise : retire le token du remote local apres le push
git remote set-url origin $RepoUrl

Write-Host "=== [3/3] TERMINE ===" -ForegroundColor Cyan
$repo = ($RepoUrl -replace "^https://github\.com/", "") -replace "\.git$", ""
Write-Host ""
Write-Host "GitHub Actions compile maintenant l'EXE (premier build : 10-20 min) :" -ForegroundColor Yellow
Write-Host "  https://github.com/$repo/actions" -ForegroundColor Green
Write-Host ""
Write-Host "Une fois le build vert, telecharge l'EXE (aucun compte requis) :" -ForegroundColor Yellow
Write-Host "  https://github.com/$repo/releases" -ForegroundColor Green
