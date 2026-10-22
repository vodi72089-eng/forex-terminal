#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use std::fs::{File, OpenOptions};
use std::io::Write;
use std::path::{Path, PathBuf};

use tauri::Manager;
use tauri_plugin_shell::process::CommandEvent;
use tauri_plugin_shell::ShellExt;

/// Cherche un executable dans le PATH (et dans les emplacements usuels).
fn find_exe(name: &str, extra: &[&str]) -> Option<PathBuf> {
    let exts: Vec<String> = if cfg!(windows) {
        vec![".exe".into(), ".cmd".into(), ".bat".into(), String::new()]
    } else {
        vec![String::new()]
    };
    let mut dirs: Vec<PathBuf> = Vec::new();
    if let Ok(path) = std::env::var("PATH") {
        for p in path.split(';') {
            if !p.is_empty() {
                dirs.push(PathBuf::from(p));
            }
        }
    }
    for d in extra {
        dirs.push(PathBuf::from(d));
    }
    for d in dirs {
        for e in &exts {
            let cand = d.join(format!("{}{}", name, e));
            if cand.is_file() {
                return Some(cand);
            }
        }
    }
    None
}

/// Journal des sidecars : le stdout/stderr est ecrit dans un fichier
/// (impossible a afficher dans la WebView sans bridge dedicated).
fn log_file(name: &str) -> Option<File> {
    let base = std::env::var("APPDATA")
        .or_else(|_| std::env::var("HOME"))
        .ok()?;
    let dir = PathBuf::from(base).join("com.forex.terminal");
    std::fs::create_dir_all(&dir).ok()?;
    OpenOptions::new()
        .create(true)
        .append(true)
        .open(dir.join(name))
        .ok()
}

fn spawn_logged(
    app: &tauri::AppHandle,
    logname: &str,
    program: PathBuf,
    args: Vec<String>,
    cwd: &Path,
) -> Result<(), String> {
    let mut cmd = app.shell().command(program.to_string_lossy().to_string());
    cmd.args(args);
    cmd.current_dir(cwd);
    let (mut rx, _child) = cmd
        .spawn()
        .map_err(|e| format!("spawn {:?} : {}", program, e))?;
    let mut sink = log_file(logname);
    tauri::async_runtime::spawn(async move {
        while let Some(event) = rx.recv().await {
            let (level, bytes) = match event {
                CommandEvent::Stdout(b) => ("stdout", b),
                CommandEvent::Stderr(b) => ("stderr", b),
                CommandEvent::Terminated(t) => {
                    if let Some(f) = sink.as_mut() {
                        let _ = writeln!(f, "[terminated] code={:?}", t.code);
                    }
                    break;
                }
                _ => continue,
            };
            if let Some(f) = sink.as_mut() {
                let _ = f.write_all(bytes.as_bytes());
                let _ = f.flush();
            }
            let _ = level;
        }
    });
    Ok(())
}

fn main() {
    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .setup(|app| {
            // Repertoire runtime : bot/, shared/, opencode.json, AGENTS.md, mcp/
            let res = app.path().resource_dir()?;
            let cwd = if res.join("bot").join("main.py").exists() {
                res
            } else {
                std::env::current_dir()?
            };
            println!("forex-terminal runtime cwd = {}", cwd.display());

            // 1. Sidecar OpenCode en mode serveur (port 4096)
            match find_exe("opencode", &[]) {
                Some(exe) => {
                    if let Err(e) = spawn_logged(
                        app.handle(),
                        "opencode.log",
                        exe,
                        vec!["serve".into(), "--port".into(), "4096".into()],
                        &cwd,
                    ) {
                        eprintln!("opencode: {}", e);
                    }
                }
                None => eprintln!("opencode INTROUVABLE dans le PATH (npm i -g opencode-ai)"),
            }

            // 2. Bot MT5 embarque (module Python du projet)
            match find_exe("python", &["C:\\Python312", "C:\\Python313"]) {
                Some(exe) => {
                    if let Err(e) = spawn_logged(
                        app.handle(),
                        "bot.log",
                        exe,
                        vec!["-u".into(), "bot/main.py".into()],
                        &cwd,
                    ) {
                        eprintln!("bot: {}", e);
                    }
                }
                None => eprintln!("python INTROUVABLE dans le PATH (winget install Python.Python.3.12)"),
            }

            Ok(())
        })
        .run(tauri::generate_context!())
        .expect("erreur au lancement de forex-terminal");
}
