#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use tauri::Manager;
use tauri_plugin_shell::ShellExt;

fn main() {
    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .setup(|app| {
            // Repertoire runtime : bot/, shared/, opencode.json, AGENTS.md, .opencode/
            // (resources declares dans tauri.conf.json, copies ici au build)
            let res = app.path().resource_dir()?;
            let cwd = if res.join("bot").join("main.py").exists() {
                res
            } else {
                std::env::current_dir()?
            };
            println!("forex-terminal runtime cwd = {}", cwd.display());

            // 1. Sidecar OpenCode en mode serveur (port 4096)
            app.shell()
                .command("opencode")
                .args(["serve", "--port", "4096"])
                .current_dir(&cwd)
                .spawn()?;

            // 2. Bot MT5 embarque (module Python du projet)
            app.shell()
                .command("python")
                .args(["-u", "bot/main.py"])
                .current_dir(&cwd)
                .spawn()?;

            Ok(())
        })
        .run(tauri::generate_context!())
        .expect("erreur au lancement de forex-terminal");
}
