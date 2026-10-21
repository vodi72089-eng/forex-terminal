import MetaTrader5 as mt5

try:
    import mt5forge  # pip install mt5forge — couche session du repo soham-stack/mt5forge
    HAS_MT5FORGE = True
except ImportError:
    HAS_MT5FORGE = False

import time
import logging

log = logging.getLogger("bot.connector")


class MT5Connector:
    """Connexion MT5 stable : mt5forge/MetaTrader5 + reconnexion automatique
    en backoff exponentiel (1s -> 60s plafonne)."""

    def __init__(self, login: int, password: str, server: str):
        self.login = login
        self.password = password
        self.server = server
        self.connected = False
        self._backoff = 1.0

    def connect(self) -> bool:
        while True:
            if mt5.initialize(login=self.login, password=self.password, server=self.server):
                acc = mt5.account_info()
                if acc is not None:
                    self.connected = True
                    self._backoff = 1.0
                    log.info("MT5 connecte : %s #%s (mt5forge=%s)", acc.server, acc.login, HAS_MT5FORGE)
                    return True
                log.warning("MT5 initialize OK mais account_info None : %s", mt5.last_error())
            else:
                log.warning("MT5 init echoue : %s", mt5.last_error())
            mt5.shutdown()
            log.warning("Reconnexion MT5 dans %.0fs", self._backoff)
            time.sleep(self._backoff)
            self._backoff = min(self._backoff * 2, 60)

    def ensure(self) -> bool:
        """Health-check de session : reconnexion auto si le terminal est tombe."""
        if not self.connected:
            return self.connect()
        info = mt5.terminal_info()
        if info is None or not info.connected:
            log.warning("Terminal MT5 deconnecte — reconnexion auto")
            mt5.shutdown()
            self.connected = False
            return self.connect()
        return True

    def shutdown(self):
        mt5.shutdown()
        self.connected = False
