from __future__ import annotations

from dataclasses import dataclass
from statistics import mean

from sqlalchemy import delete, select

from app.db.models import Candle, Level
from app.db.repository import SessionLocal


@dataclass
class LevelResult:
    level_price: float
    level_type: str
    source_type: str
    description: str
    strength_score: float


class LevelsCalculator:
    LOOKBACK = 350
    SWING_WINDOW = 2
    MAX_LEVELS_PER_SOURCE = 25

    def calculate(self, symbol: str, interval: str) -> list[LevelResult]:
        symbol_u = symbol.upper()
        with SessionLocal() as db:
            candles = list(
                db.execute(
                    select(Candle)
                    .where(Candle.symbol == symbol_u, Candle.interval == interval)
                    .order_by(Candle.open_time.desc())
                    .limit(self.LOOKBACK)
                )
                .scalars()
            )
            candles.reverse()
            if len(candles) < 20:
                db.execute(delete(Level).where(Level.symbol == symbol_u, Level.interval == interval))
                db.commit()
                return []

            results = self._detect_levels(candles)

            db.execute(delete(Level).where(Level.symbol == symbol_u, Level.interval == interval))
            db.add_all(
                [
                    Level(
                        symbol=symbol_u,
                        interval=interval,
                        level_price=row.level_price,
                        level_type=row.level_type,
                        source_type=row.source_type,
                        description=row.description,
                        strength_score=row.strength_score,
                    )
                    for row in results
                ]
            )
            db.commit()
            return results

    def _detect_levels(self, candles: list[Candle]) -> list[LevelResult]:
        avg_range = mean([(c.high - c.low) for c in candles[-100:]])
        out: list[LevelResult] = []
        out.extend(self._detect_swings(candles, avg_range))
        out.extend(self._detect_bos_choch(candles, avg_range))
        out.extend(self._detect_fvg(candles, avg_range))

        out.sort(key=lambda x: x.strength_score, reverse=True)
        return out[: self.MAX_LEVELS_PER_SOURCE * 4]

    def _detect_swings(self, candles: list[Candle], avg_range: float) -> list[LevelResult]:
        swings: list[LevelResult] = []
        w = self.SWING_WINDOW
        for i in range(w, len(candles) - w):
            center = candles[i]
            left = candles[i - w : i]
            right = candles[i + 1 : i + 1 + w]
            if all(center.high > c.high for c in left + right):
                score = min(100.0, 45.0 + (center.high - max(c.high for c in left + right)) / max(avg_range, 1e-9) * 12.0)
                swings.append(LevelResult(center.high, "resistance", "swing_high", "Liquidity swing high", round(score, 2)))
            if all(center.low < c.low for c in left + right):
                score = min(100.0, 45.0 + (min(c.low for c in left + right) - center.low) / max(avg_range, 1e-9) * 12.0)
                swings.append(LevelResult(center.low, "support", "swing_low", "Liquidity swing low", round(score, 2)))
        return swings[-self.MAX_LEVELS_PER_SOURCE :]

    def _detect_bos_choch(self, candles: list[Candle], avg_range: float) -> list[LevelResult]:
        levels: list[LevelResult] = []
        recent_high = candles[0].high
        recent_low = candles[0].low
        trend = 0
        for c in candles[1:]:
            if c.close > recent_high:
                source = "bos" if trend >= 0 else "choch"
                trend = 1
                score = min(100.0, 55.0 + (c.close - recent_high) / max(avg_range, 1e-9) * 15.0)
                levels.append(
                    LevelResult(
                        recent_high,
                        "support",
                        source,
                        f"{source.upper()} up confirmed by close breakout",
                        round(score, 2),
                    )
                )
            if c.close < recent_low:
                source = "bos" if trend <= 0 else "choch"
                trend = -1
                score = min(100.0, 55.0 + (recent_low - c.close) / max(avg_range, 1e-9) * 15.0)
                levels.append(
                    LevelResult(
                        recent_low,
                        "resistance",
                        source,
                        f"{source.upper()} down confirmed by close breakout",
                        round(score, 2),
                    )
                )
            recent_high = max(recent_high, c.high)
            recent_low = min(recent_low, c.low)
        return levels[-self.MAX_LEVELS_PER_SOURCE :]

    def _detect_fvg(self, candles: list[Candle], avg_range: float) -> list[LevelResult]:
        fvgs: list[LevelResult] = []
        for i in range(2, len(candles)):
            c0 = candles[i - 2]
            c2 = candles[i]
            if c2.low > c0.high:
                gap = c2.low - c0.high
                score = min(100.0, 50.0 + gap / max(avg_range, 1e-9) * 18.0)
                fvgs.append(LevelResult((c2.low + c0.high) / 2.0, "support", "fvg", "Bullish FVG midpoint", round(score, 2)))
            elif c2.high < c0.low:
                gap = c0.low - c2.high
                score = min(100.0, 50.0 + gap / max(avg_range, 1e-9) * 18.0)
                fvgs.append(LevelResult((c2.high + c0.low) / 2.0, "resistance", "fvg", "Bearish FVG midpoint", round(score, 2)))
        return fvgs[-self.MAX_LEVELS_PER_SOURCE :]

    def to_tradingview_csv(self, levels: list[LevelResult]) -> str:
        lines = ["price,type,source,description,strength"]
        for lvl in levels:
            safe_desc = lvl.description.replace(",", " ")
            lines.append(
                f"{lvl.level_price:.8f},{lvl.level_type},{lvl.source_type},{safe_desc},{lvl.strength_score:.2f}"
            )
        return "\n".join(lines)
