from app.core.bybit_client import BybitClient


class MarketLoader:
    def __init__(self, client: BybitClient) -> None:
        self.client = client

    def load_candles(self, symbol: str, interval: str) -> int:
        """Load candles into storage. Returns amount of inserted rows."""
        _ = self.client.fetch_candles(symbol=symbol, interval=interval)
        return 0
