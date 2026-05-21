from dataclasses import dataclass
import logging

from sqlalchemy import select

from app.config.settings import settings
from app.core.indicators import IndicatorSet, calculate_indicators
from app.core.scoring import SCORING_VERSION, calculate_grid_score, tier_from_score
from app.db.models import Candle, ScanResult, ScanRun, Symbol
from app.db.repository import SessionLocal

LOGGER = logging.getLogger(__name__)


@dataclass
class ScanRow:
    symbol: str
    price: float
    atr_pct: float
    rsi: float
    adx: float
    vwap_deviation_pct: float
    bb_width_pct: float
    grid_score: float

    @property
    def tier(self) -> str:
        return tier_from_score(self.grid_score)


class ValueScanner:
    """Indicator-driven scanner pipeline."""

    def scan(
        self,
        strategy: str,
        top: int = 30,
        *,
        market_type: str = settings.default_market_type,
        interval: str = "60",
        candles_limit: int = 120,
    ) -> list[ScanRow]:
        rows: list[ScanRow] = []

        with SessionLocal() as db:
            run = ScanRun(strategy=strategy, scoring_version=SCORING_VERSION)
            db.add(run)
            db.flush()

            symbols = [
                s
                for (s,) in db.execute(
                    select(Symbol.symbol).where(
                        Symbol.market_type == market_type,
                        Symbol.quote_coin == "USDT",
                        Symbol.status.in_(["Trading", "TRADING", "tradable", "Tradable"]),
                    )
                )
            ]
            for symbol in symbols:
                candles = list(
                    db.execute(
                        select(Candle)
                        .where(Candle.symbol == symbol, Candle.market_type == market_type, Candle.interval == interval)
                        .order_by(Candle.open_time.desc())
                        .limit(candles_limit)
                    ).scalars()
                )
                candles = list(reversed(candles))
                min_required = 30
                if len(candles) < min_required:
                    LOGGER.info(
                        "Skip symbol=%s reason=insufficient_history interval=%s candles=%s required=%s",
                        symbol,
                        interval,
                        len(candles),
                        min_required,
                    )
                    continue

                try:
                    indicators = _calc(candles)
                    score = calculate_grid_score(indicators)
                except ValueError as exc:
                    LOGGER.info("Skip symbol=%s reason=%s", symbol, exc)
                    continue

                row = ScanRow(
                    symbol=symbol,
                    price=candles[-1].close,
                    atr_pct=indicators.atr_pct,
                    rsi=indicators.rsi,
                    adx=indicators.adx,
                    vwap_deviation_pct=indicators.vwap_deviation_pct,
                    bb_width_pct=indicators.bb_width_pct,
                    grid_score=score,
                )
                rows.append(row)
                db.add(
                    ScanResult(
                        run_id=run.id,
                        symbol=row.symbol,
                        price=row.price,
                        atr_pct=row.atr_pct,
                        rsi=row.rsi,
                        adx=row.adx,
                        vwap_deviation_pct=row.vwap_deviation_pct,
                        bb_width_pct=row.bb_width_pct,
                        grid_score=row.grid_score,
                        tier=row.tier,
                    )
                )

            db.commit()

        return sorted(rows, key=lambda r: r.grid_score, reverse=True)[:top]


def _calc(candles: list[Candle]) -> IndicatorSet:
    highs = [c.high for c in candles]
    lows = [c.low for c in candles]
    closes = [c.close for c in candles]
    volumes = [c.volume for c in candles]
    return calculate_indicators(highs=highs, lows=lows, closes=closes, volumes=volumes)
