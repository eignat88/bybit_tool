from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import Select, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.core.bybit_client import BybitClient
from app.db.models import Candle

LOGGER = logging.getLogger(__name__)
INTERVAL_TO_MS = {
    "1": 60_000,
    "3": 180_000,
    "5": 300_000,
    "15": 900_000,
    "30": 1_800_000,
    "60": 3_600_000,
    "120": 7_200_000,
    "240": 14_400_000,
    "360": 21_600_000,
    "720": 43_200_000,
    "D": 86_400_000,
    "W": 604_800_000,
}


@dataclass(slots=True)
class LoadSummary:
    symbol: str
    interval: str
    rows_inserted: int
    duplicates_skipped: int


class MarketLoader:
    def __init__(self, client: BybitClient, db: Session) -> None:
        self.client = client
        self.db = db

    def _latest_open_time(self, symbol: str, interval: str, market_type: str) -> datetime | None:
        stmt: Select[tuple[datetime | None]] = select(func.max(Candle.open_time)).where(
            Candle.symbol == symbol,
            Candle.interval == interval,
            Candle.market_type == market_type,
        )
        return self.db.execute(stmt).scalar_one_or_none()

    def _parse_klines(self, data: list[list[str]], symbol: str, interval: str, market_type: str) -> list[dict]:
        rows: list[dict] = []
        for item in data:
            # [startTime,open,high,low,close,volume,turnover]
            open_time = datetime.fromtimestamp(int(item[0]) / 1000, tz=UTC)
            rows.append(
                {
                    "symbol": symbol,
                    "market_type": market_type,
                    "interval": interval,
                    "open_time": open_time,
                    "open": float(item[1]),
                    "high": float(item[2]),
                    "low": float(item[3]),
                    "close": float(item[4]),
                    "volume": float(item[5]),
                    "turnover": float(item[6]),
                    "created_at": datetime.now(UTC),
                }
            )
        return sorted(rows, key=lambda x: x["open_time"])

    def load_candles(self, symbol: str, interval: str, market_type: str = "linear", limit: int = 1000) -> LoadSummary:
        latest = self._latest_open_time(symbol=symbol, interval=interval, market_type=market_type)
        start_ms = None
        if latest is not None:
            step_ms = INTERVAL_TO_MS.get(interval)
            if step_ms is None:
                raise ValueError(f"Unsupported interval: {interval}")
            start_ms = int(latest.timestamp() * 1000) + step_ms

        raw = self.client.get_klines(
            symbol=symbol,
            interval=interval,
            market_type=market_type,
            limit=limit,
            start_ms=start_ms,
        )
        kline_rows = raw.get("result", {}).get("list", [])
        parsed = self._parse_klines(kline_rows, symbol, interval, market_type)

        if not parsed:
            return LoadSummary(symbol=symbol, interval=interval, rows_inserted=0, duplicates_skipped=0)

        stmt = insert(Candle).values(parsed)
        stmt = stmt.on_conflict_do_nothing(
            index_elements=["symbol", "market_type", "interval", "open_time"]
        )
        result = self.db.execute(stmt)
        self.db.commit()

        inserted = result.rowcount or 0
        duplicates = len(parsed) - inserted
        LOGGER.info(
            "Inserted candles",
            extra={"symbol": symbol, "interval": interval, "inserted": inserted, "duplicates": duplicates},
        )
        return LoadSummary(symbol=symbol, interval=interval, rows_inserted=inserted, duplicates_skipped=duplicates)
