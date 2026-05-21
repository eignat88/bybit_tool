from dataclasses import dataclass


@dataclass
class LevelResult:
    price: float
    level_type: str
    source_type: str
    strength_score: float


class LevelsCalculator:
    def calculate(self, symbol: str, interval: str) -> list[LevelResult]:
        # TODO: plug VPVR/FVG/BOS/CHOCH logic.
        _ = (symbol, interval)
        return []
