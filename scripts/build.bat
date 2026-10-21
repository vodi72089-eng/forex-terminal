@echo off
REM Forex Terminal - build de l'EXE Windows
REM Prerequis : scripts\setup.ps1 execute avec succes
cd /d "%~dp0.."

echo === [1/3] Frontend Next.js (export statique) ===
call npm run build || goto :error

echo === [2/3] Build Tauri (compile le .exe) ===
call npx tauri build || goto :error

echo === [3/3] TERMINE ===
echo.
echo   EXE nu      : src-tauri\target\release\forex-terminal.exe
echo   Installeur  : src-tauri\target\release\bundle\nsis\forex-terminal_0.1.0_x64-setup.exe
echo.
pause
exit /b 0

:error
echo BUILD ECHOUE - consulte les messages ci-dessus.
pause
exit /b 1
