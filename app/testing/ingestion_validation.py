from __future__ import annotations

from sqlalchemy import func, select

from app.core.bybit_client import BybitClient
from app.core.market_loader import MarketLoader
from app.db.models import Candle
from app.db.repository import SessionLocal
from app.testing.models import CheckResult


def validate_ingestion(symbol: str = "BTCUSDT", intervals: tuple[str, ...] = ("15", "60")) -> list[CheckResult]:
    results: list[CheckResult] = []
    with SessionLocal() as db:
        loader = MarketLoader(client=BybitClient(), db=db)
        for interval in intervals:
            first = loader.load_candles(symbol=symbol, interval=interval)
            second = loader.load_candles(symbol=symbol, interval=interval)
            ok = first.rows_requested >= first.rows_inserted and second.rows_inserted == 0
            msg = f"{symbol} {interval} first_inserted={first.rows_inserted} second_inserted={second.rows_inserted}"
            results.append(CheckResult(name=f"ingestion {symbol} {interval}", ok=ok, message=msg))
    return results


def validate_duplicates() -> CheckResult:
    with SessionLocal() as db:
        stmt = (
            select(Candle.symbol, Candle.interval, Candle.open_time, func.count().label("cnt"))
            .group_by(Candle.symbol, Candle.interval, Candle.open_time)
            .having(func.count() > 1)
        )
        dupes = list(db.execute(stmt))
    details = [f"{s} {i} {ot.isoformat()} count={cnt}" for s, i, ot, cnt in dupes[:20]]
    return CheckResult(name="duplicate validation", ok=len(dupes) == 0, message="no duplicates" if not dupes else "duplicate candles detected", details=details)
