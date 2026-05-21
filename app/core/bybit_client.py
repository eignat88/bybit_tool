from typing import Any


class BybitClient:
    """Stub Bybit client.

    TODO: implement HTTP integration and retry/backoff.
    """

    def fetch_candles(self, symbol: str, interval: str, limit: int = 200) -> list[dict[str, Any]]:
        raise NotImplementedError("Bybit HTTP integration is not implemented yet")
