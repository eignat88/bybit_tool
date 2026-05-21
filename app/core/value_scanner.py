from dataclasses import dataclass

from app.core.scoring import tier_from_score


@dataclass
class ScanRow:
    symbol: str
    price: float
    grid_score: float

    @property
    def tier(self) -> str:
        return tier_from_score(self.grid_score)


class ValueScanner:
    """MVP scanner service placeholder."""

    def scan(self, strategy: str, top: int = 30) -> list[ScanRow]:
        # TODO: implement real indicator-based scoring against DB candles.
        return [ScanRow(symbol="BTCUSDT", price=0.0, grid_score=55.0)][:top]
