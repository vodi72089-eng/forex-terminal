#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use std::fs::{File, OpenOptions};
use std::io::{BufRead, BufReader, Read, Write};
use std::path::{Path, PathBuf};
use std::process::{Command, Stdio};

use tauri::Manager;

/// Dossier ou sont ecrits les logs des sidecars (dossier utilisateur inscriptible).
fn log_dir() -> Option<PathBuf> {
    let base = std::env::var("APPDATA")
        .or_else(|_| std::env::var("HOME"))
        .ok()?;
    let dir = PathBuf::from(base).join("com.forex.terminal");
    std::fs::create_dir_all(&dir).ok()?;
    Some(dir)
}

fn log_file(name: &str) -> Option<File> {
    let dir = log_dir()?;
    OpenOptions::new().create(true).append(true).open(dir.join(name)).ok()
}

/// Cherche un executable dans le PATH (et dans les emplacements usuels).
/// `exts` : liste d'extensions a tester ("" = nom nu).
fn find_in_path(name: &str, exts: &[&str], extra: &[&str]) -> Option<PathBuf> {
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
        for e in exts {
            let cand = d.join(format!("{}{}", name, e));
            if cand.is_file() {
                return Some(cand);
            }
        }
    }
    None
}

/// Programme a lancer + comment le lancer.
///
/// Windows : les CLI installes par npm sont des shims .cmd/.bat, que
/// CreateProcess ne peut PAS executer directement (ERROR_BAD_EXE_FORMAT).
/// -> on passe par cmd.exe /C dans ce cas.
struct Program {
    path: PathBuf,
    via_cmd: bool,
}

fn resolve_program(name: &str, extra: &[&str]) -> Option<Program> {
    if cfg!(windows) {
        // 1. un vrai .exe (ex python.exe) -> execution directe
        if let Some(p) = find_in_path(name, &["exe"], extra) {
            return Some(Program { path: p, via_cmd: false });
        }
        // 2. un shim npm .cmd/.bat (ex opencode.cmd) -> via cmd.exe /C
        //    (CreateProcess ne peut pas executer un batch directement)
        if let Some(p) = find_in_path(name, &["cmd", "bat"], extra) {
            return Some(Program { path: p, via_cmd: true });
        }
        None
    } else {
        find_in_path(name, &[""], extra).map(|p| Program { path: p, via_cmd: false })
    }
}

/// Copie le flux stdout/stderr du process dans le fichier de log.
fn pump<R: Read + Send + 'static>(reader: R, logpath: &Path, tag: &'static str) {
    let path = logpath.to_path_buf();
    std::thread::spawn(move || {
        let mut file = OpenOptions::new().create(true).append(true).open(path).ok();
        let buf = BufReader::new(reader);
        for line in buf.lines().map_while(Result::ok) {
            if let Some(f) = file.as_mut() {
                let _ = writeln!(f, "[{}] {}", tag, line);
                let _ = f.flush();
            }
        }
    });
}

/// Demarre un sidecar (opencode / bot python) et redirige ses sorties vers un log.
fn spawn_sidecar(logname: &str, prog: &Program, args: &[&str], cwd: &Path) -> Result<(), String> {
    let mut cmd = if prog.via_cmd {
        let mut c = Command::new("cmd.exe");
        c.arg("/C");
        c.arg(&prog.path);
        c.args(args);
        c
    } else {
        let mut c = Command::new(&prog.path);
        c.args(args);
        c
    };
    cmd.current_dir(cwd);
    cmd.stdin(Stdio::null());
    cmd.stdout(Stdio::piped());
    cmd.stderr(Stdio::piped());

    let mut child = cmd
        .spawn()
        .map_err(|e| format!("spawn {:?} : {}", prog.path, e))?;

    let dir = log_dir();
    if let Some(d) = dir {
        let out = d.join(logname);
        let err = d.join(format!("{}.err", logname));
        if let Some(so) = child.stdout.take() {
            pump(so, &out, "out");
        }
        if let Some(se) = child.stderr.take() {
            pump(se, &err, "err");
        }
    }
    // Le handle est volontairement laisse : dropping un std::process::Child
    // NE tue PAS le process, il ferme juste le handle. Le sidecar doit
    // continuer a tourner avec l'application.
    Ok(())
}

fn main() {
    tauri::Builder::default()
        .setup(|app| {
            // Repertoire runtime : bot/, shared/, opencode.json, AGENTS.md, mcp/
            let res = app.path().resource_dir()?;
            let cwd = if res.join("bot").join("main.py").exists() {
                res
            } else {
                std::env::current_dir()?
            };

            // 1. Sidecar OpenCode en mode serveur (port 4096)
            match resolve_program("opencode", &[]) {
                Some(p) => {
                    if let Err(e) = spawn_sidecar(
                        "opencode.log",
                        &p,
                        &["serve", "--port", "4096"],
                        &cwd,
                    ) {
                        eprintln!("opencode: {}", e);
                        if let Some(mut f) = log_file("opencode.log") {
                            let _ = writeln!(f, "ERREUR: {}", e);
                        }
                    }
                }
                None => {
                    let msg = "opencode INTROUVABLE dans le PATH (npm i -g opencode-ai)";
                    eprintln!("{}", msg);
                    if let Some(mut f) = log_file("opencode.log") {
                        let _ = writeln!(f, "{}", msg);
                    }
                }
            }

            // 2. Bot MT5 embarque (module Python du projet)
            match resolve_program("python", &["C:\\Python312", "C:\\Python313"]) {
                Some(p) => {
                    if let Err(e) = spawn_sidecar("bot.log", &p, &["-u", "bot/main.py"], &cwd) {
                        eprintln!("bot: {}", e);
                        if let Some(mut f) = log_file("bot.log") {
                            let _ = writeln!(f, "ERREUR: {}", e);
                        }
                    }
                }
                None => {
                    let msg = "python INTROUVABLE dans le PATH (winget install Python.Python.3.12)";
                    eprintln!("{}", msg);
                    if let Some(mut f) = log_file("bot.log") {
                        let _ = writeln!(f, "{}", msg);
                    }
                }
            }

            Ok(())
        })
        .run(tauri::generate_context!())
        .expect("erreur au lancement de forex-terminal");
}
