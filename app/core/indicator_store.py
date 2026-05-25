from __future__ import annotations

from dataclasses import dataclass
from time import perf_counter

from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from app.config.settings import settings
from app.core.indicators import calculate_indicators
from app.db.models import Candle, IndicatorValue, Symbol
from app.db.repository import SessionLocal

MIN_REQUIRED_CANDLES = 30
INDICATOR_NAMES = (
    "atr_pct",
    "rsi",
    "adx",
    "vwap_deviation_pct",
    "bb_width_pct",
)


@dataclass
class IndicatorSymbolResult:
    symbol: str
    interval: str
    market_type: str
    status: str
    open_time: str | None = None
    indicators_saved: int = 0
    candles_count: int = 0
    reason: str | None = None
    error: str | None = None
    values: dict[str, float] | None = None


@dataclass
class IndicatorStoreResult:
    symbols_requested: int
    symbols_processed: int
    symbols_skipped: int
    symbols_failed: int
    indicators_saved_total: int
    elapsed_time_sec: float
    rows: list[IndicatorSymbolResult]


class IndicatorStore:
    def __init__(self, session_factory: sessionmaker = SessionLocal) -> None:
        self._session_factory = session_factory

    def resolve_symbols(self, symbols: list[str], market_type: str) -> list[str]:
        if len(symbols) == 1 and symbols[0].upper() == "ALL":
            with self._session_factory() as db:
                return [
                    s
                    for (s,) in db.execute(
                        select(Symbol.symbol).where(
                            Symbol.market_type == market_type,
                            Symbol.quote_coin == "USDT",
                            Symbol.status.in_(["Trading", "TRADING", "tradable", "Tradable"]),
                        )
                    )
                ]
        return [s.upper() for s in symbols]

    def calculate_and_store(
        self,
        symbols: list[str],
        interval: str,
        market_type: str = settings.default_market_type,
        limit: int = 300,
        calc_version: str = "v1",
    ) -> IndicatorStoreResult:
        started = perf_counter()
        resolved = self.resolve_symbols(symbols, market_type)
        rows: list[IndicatorSymbolResult] = []

        for symbol in resolved:
            try:
                with self._session_factory() as db:
                    candles = list(
                        db.execute(
                            select(Candle)
                            .where(
                                Candle.symbol == symbol,
                                Candle.market_type == market_type,
                                Candle.interval == interval,
                            )
                            .order_by(Candle.open_time.desc())
                            .limit(limit)
                        ).scalars()
                    )
                    candles = list(reversed(candles))

                    if len(candles) < MIN_REQUIRED_CANDLES:
                        rows.append(
                            IndicatorSymbolResult(
                                symbol=symbol,
                                interval=interval,
                                market_type=market_type,
                                status="skipped",
                                reason="insufficient_history",
                                candles_count=len(candles),
                            )
                        )
                        continue

                    indicators = calculate_indicators(
                        highs=[c.high for c in candles],
                        lows=[c.low for c in candles],
                        closes=[c.close for c in candles],
                        volumes=[c.volume for c in candles],
                    )
                    open_time = candles[-1].open_time
                    values = {
                        "atr_pct": indicators.atr_pct,
                        "rsi": indicators.rsi,
                        "adx": indicators.adx,
                        "vwap_deviation_pct": indicators.vwap_deviation_pct,
                        "bb_width_pct": indicators.bb_width_pct,
                    }
                    saved = 0
                    for name, val in values.items():
                        existing = db.execute(
                            select(IndicatorValue).where(
                                IndicatorValue.symbol == symbol,
                                IndicatorValue.market_type == market_type,
                                IndicatorValue.interval == interval,
                                IndicatorValue.open_time == open_time,
                                IndicatorValue.indicator_name == name,
                                IndicatorValue.calc_version == calc_version,
                            )
                        ).scalar_one_or_none()
                        if existing is None:
                            db.add(
                                IndicatorValue(
                                    symbol=symbol,
                                    market_type=market_type,
                                    interval=interval,
                                    open_time=open_time,
                                    indicator_name=name,
                                    value=val,
                                    calc_version=calc_version,
                                )
                            )
                        else:
                            existing.value = val
                        saved += 1
                    db.commit()
                    rows.append(
                        IndicatorSymbolResult(
                            symbol=symbol,
                            interval=interval,
                            market_type=market_type,
                            status="ok",
                            open_time=open_time.isoformat(),
                            indicators_saved=saved,
                            candles_count=len(candles),
                            values=values,
                        )
                    )
            except Exception as exc:  # noqa: BLE001
                rows.append(
                    IndicatorSymbolResult(
                        symbol=symbol,
                        interval=interval,
                        market_type=market_type,
                        status="failed",
                        error=f"{type(exc).__name__}: {exc}",
                    )
                )

        elapsed = perf_counter() - started
        processed = sum(1 for r in rows if r.status == "ok")
        skipped = sum(1 for r in rows if r.status == "skipped")
        failed = sum(1 for r in rows if r.status == "failed")
        total = sum(r.indicators_saved for r in rows)

        return IndicatorStoreResult(
            symbols_requested=len(resolved),
            symbols_processed=processed,
            symbols_skipped=skipped,
            symbols_failed=failed,
            indicators_saved_total=total,
            elapsed_time_sec=elapsed,
            rows=rows,
        )
