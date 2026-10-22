"""
Forex Terminal — resolution des chemins.

Probleme resolu : dans l'EXE installe, le dossier de ressources Tauri est sous
"Program Files" (LECTURE SEULE). Le bot doit donc ecrire ses donnees
(credentials, config, runtime, logs) dans un dossier utilisateur inscriptible.

Ordre de resolution de `shared/` :
  1. $FOREX_TERMINAL_SHARED          (override explicite)
  2. <projet>/shared                 (mode dev : le dossier src/ est a cote)
  3. %APPDATA%\\com.forex.terminal\\shared   (mode installe)
"""
from __future__ import annotations

import os

APP_ID = "com.forex.terminal"


def project_root() -> str:
    """Racine du projet (= dossier contenant bot/)."""
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def is_dev() -> bool:
    """Mode dev : le dossier src/ du front est present a cote de bot/."""
    return os.path.isdir(os.path.join(project_root(), "src"))


def shared_dir() -> str:
    """Dossier de donnees INSCRIPTIBLE (config, runtime, credentials, logs)."""
    env = os.environ.get("FOREX_TERMINAL_SHARED")
    if env:
        return os.path.abspath(env)
    if is_dev():
        return os.path.join(project_root(), "shared")
    base = os.environ.get("APPDATA") or os.path.expanduser("~")
    return os.path.join(base, APP_ID, "shared")


def ensure_shared() -> str:
    d = shared_dir()
    os.makedirs(d, exist_ok=True)
    return d


def path_in_shared(name: str) -> str:
    return os.path.join(shared_dir(), name)


def seed_shared_from_resources() -> list[str]:
    """Au 1er lancement installe, copie les fichiers de seed depuis le dossier
    de ressources (read-only) vers le dossier utilisateur inscriptible.
    Retourne la liste des fichiers copies."""
    import shutil

    root = project_root()
    src_shared = os.path.join(root, "shared")
    dst_shared = shared_dir()
    if os.path.abspath(src_shared) == os.path.abspath(dst_shared):
        return []
    if not os.path.isdir(src_shared):
        return []
    copied = []
    os.makedirs(dst_shared, exist_ok=True)
    for name in ("bot_config.set", "credentials.json", "bot_runtime.json"):
        s = os.path.join(src_shared, name)
        d = os.path.join(dst_shared, name)
        if os.path.isfile(s) and not os.path.isfile(d):
            shutil.copy2(s, d)
            copied.append(name)
    return copied


def runtime_cwd() -> str:
    """Repertoire de travail des sidecars : celui qui contient opencode.json
    ET les ressources (bot/, .opencode/)."""
    return project_root()


def oc_port_file() -> str:
    """Fichier ou Tauri ecrit le portChoisi pour opencode serve.

    Un port fixe (4096) peut etre occupe par un processus etranger (Docker,
    autre session Windows) qui ne repond pas : le serveur opencode refuse
    alors de demarrer (ServeError). Le port est donc choisi dynamiquement
    et transmis au bot via ce fichier, que le bot expose au dashboard.
    """
    return os.path.join(shared_dir(), "opencode.port")


def _candidate_shared_dirs() -> list:
    """Dossiers ou le fichier de port peut se trouver :
    le dossier de l'app installee ET le dossier shared du projet (mode dev)."""
    out = [shared_dir()]
    proj = os.path.join(project_root(), "shared")
    if os.path.abspath(proj) != os.path.abspath(out[0]):
        out.append(proj)
    base = os.environ.get("APPDATA")
    if base:
        appdata = os.path.join(base, APP_ID, "shared")
        if os.path.abspath(appdata) != os.path.abspath(out[0]):
            out.append(appdata)
    return out


def read_port_file(name: str, default: int) -> int:
    """Lit un fichier de port ecrit par Tauri, ou renvoie la valeur par defaut."""
    for d in _candidate_shared_dirs():
        try:
            with open(os.path.join(d, name), "r", encoding="utf-8") as f:
                p = int(f.read().strip())
                if 1024 < p < 65536:
                    return p
        except Exception:
            continue
    return default


def read_oc_port(default: int = 4096) -> int:
    """Port opencode annonce par Tauri (default si absent/invalide)."""
    return read_port_file("opencode.port", default)
