"""Eccezioni di dominio, tradotte in risposte HTTP da app.main."""


class StoreError(Exception):
    """Base per tutti gli errori legati all'upstream."""


class StoreNotFound(StoreError):
    """La risorsa non esiste su apps.odoo.com (404 a monte)."""

    def __init__(self, message: str = "Resource not found on the Odoo Apps Store"):
        super().__init__(message)
        self.message = message


class UpstreamError(StoreError):
    """apps.odoo.com non raggiungibile, in errore o troppo lento."""

    def __init__(self, message: str, retry_after: int = 30):
        super().__init__(message)
        self.message = message
        self.retry_after = retry_after


class SourceUnavailable(StoreError):
    """Il codice del modulo non è prelevabile.

    Modulo a pagamento, nessun repository dichiarato nella scheda, repository non
    supportato, oppure archivio che non supera i controlli di sicurezza.
    """

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


class ParseError(StoreError):
    """L'HTML è arrivato ma non ha la struttura attesa: probabile cambio di markup."""

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message
