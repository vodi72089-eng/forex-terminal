"""
Connexion MT5 stable : mt5forge/MetaTrader5 + reconnexion automatique
en backoff exponentiel (1s -> 60s plafonne).

Expose aussi :
  - last_error   : dernier message d'erreur lisible
  - status()     : etat complet pour le dashboard
  - update_credentials() : change les identifiants et force la reconnexion
"""
from __future__ import annotations

import logging
import time

import MetaTrader5 as mt5

try:
    import mt5forge  # pip install mt5forge — couche session du repo soham-stack/mt5forge
    HAS_MT5FORGE = True
except ImportError:
    HAS_MT5FORGE = False

log = logging.getLogger("bot.connector")


class MT5Connector:
    """Connexion MT5 stable : mt5forge/MetaTrader5 + reconnexion automatique
    en backoff exponentiel (1s -> 60s plafonne)."""

    def __init__(self, login: int, password: str, server: str):
        self.login = login
        self.password = password
        self.server = server
        self.connected = False
        self.last_error: str | None = None
        self.attempts = 0
        self._backoff = 1.0
        self._want_reconnect = False

    # ── Identifiants ────────────────────────────────────────────────────────
    def update_credentials(self, login: int, password: str, server: str) -> None:
        """Nouveaux identifiants + reconnexion forcee au prochain cycle."""
        self.login = login
        self.password = password
        self.server = server
        self.connected = False
        self.last_error = None
        self.attempts = 0
        self._backoff = 1.0
        self._want_reconnect = True
        log.info("identifiants mis a jour : %s / %s", login, server)

    def request_reconnect(self) -> None:
        """Force une reconnexion (sans changer les identifiants)."""
        self.connected = False
        self._want_reconnect = True
        self._backoff = 1.0
        self.attempts = 0

    # ── Connexion ───────────────────────────────────────────────────────────
    def connect(self) -> bool:
        while True:
            if self._want_reconnect:
                self._want_reconnect = False
                self.connected = False
                self._backoff = 1.0
                try:
                    mt5.shutdown()
                except Exception:
                    pass
            self.attempts += 1
            try:
                ok = mt5.initialize(login=self.login, password=self.password, server=self.server)
            except Exception as e:
                self.last_error = f"exception MT5 : {e}"
                log.warning("MT5 init exception : %s", e)
                ok = False
            if ok:
                acc = mt5.account_info()
                if acc is not None:
                    self.connected = True
                    self.last_error = None
                    self._backoff = 1.0
                    log.info("MT5 connecte : %s #%s (mt5forge=%s)",
                             acc.server, acc.login, HAS_MT5FORGE)
                    return True
                self.last_error = f"MT5 initialise mais account_info vide : {mt5.last_error()}"
                log.warning(self.last_error)
            else:
                err = mt5.last_error()
                self.last_error = f"MT5 init refuse : {err} (login={self.login} server={self.server})"
                log.warning(self.last_error)
            try:
                mt5.shutdown()
            except Exception:
                pass
            log.warning("Reconnexion MT5 dans %.0fs", self._backoff)
            time.sleep(self._backoff)
            self._backoff = min(self._backoff * 2, 60)

    def ensure(self) -> bool:
        """Health-check de session : reconnexion auto si le terminal est tombe."""
        if not self.connected:
            return self.connect()
        try:
            info = mt5.terminal_info()
        except Exception as e:
            self.last_error = f"terminal_info a echoue : {e}"
            info = None
        if info is None or not getattr(info, "connected", False):
            log.warning("Terminal MT5 deconnecte — reconnexion auto")
            self.last_error = "terminal MT5 deconnecte"
            try:
                mt5.shutdown()
            except Exception:
                pass
            self.connected = False
            return self.connect()
        return True

    def shutdown(self):
        try:
            mt5.shutdown()
        except Exception:
            pass
        self.connected = False

    def status(self) -> dict:
        """Etat de la connexion, pour le dashboard."""
        acc = None
        if self.connected:
            try:
                a = mt5.account_info()
                if a is not None:
                    acc = {"login": a.login, "server": a.server, "name": a.name,
                           "currency": a.currency}
            except Exception:
                acc = None
        return {
            "connected": self.connected,
            "login": self.login,
            "server": self.server,
            "has_password": bool(self.password),
            "attempts": self.attempts,
            "last_error": self.last_error,
            "account": acc,
            "mt5forge": HAS_MT5FORGE,
        }
