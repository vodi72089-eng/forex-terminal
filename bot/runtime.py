import json
import os
import tempfile


def write_atomic(path: str, payload: dict):
    """Ecriture atomique : tmp + os.replace.
    L'agent OpenCode ne lit JAMAIS un fichier a moitie ecrit."""
    d = os.path.dirname(os.path.abspath(path))
    fd, tmp = tempfile.mkstemp(dir=d, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(payload, f, separators=(",", ":"))
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
