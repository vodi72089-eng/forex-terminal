"""
Forex Terminal — ecriture atomique + journal circulaire.

Le journal est stocke dans bot_runtime.json : c'est le seul canal de
diagnostic qui fonctionne dans l'EXE installe (stdout du sidecar est
jete par Tauri). Sans lui, l'utilisateur ne voit JAMAIS pourquoi une
config a ete rejetee.
"""
from __future__ import annotations

import json
import os
import tempfile
import threading
from collections import deque
from datetime import datetime

_LOG = deque(maxlen=100)
_LOG_LOCK = threading.Lock()


def write_atomic(path: str, payload: dict):
    """Ecriture atomique : tmp + os.replace.
    L'agent OpenCode ne lit JAMAIS un fichier a moitie ecrit."""
    d = os.path.dirname(os.path.abspath(path))
    os.makedirs(d, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=d, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(payload, f, separators=(",", ":"), ensure_ascii=False)
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def log_add(level: str, message: str, source: str = "bot") -> None:
    """Ajoute une ligne au journal circulaire (expose dans le dashboard)."""
    ts = datetime.now().strftime("%H:%M:%S")
    entry = {"ts": ts, "level": level, "source": source, "msg": str(message)}
    with _LOG_LOCK:
        _LOG.append(entry)


def log_tail(n: int = 40) -> list:
    with _LOG_LOCK:
        items = list(_LOG)
    return items[-n:]
