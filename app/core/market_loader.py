from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from time import perf_counter

from sqlalchemy import Select, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.config.settings import settings
from app.core.bybit_client import BybitClient
from app.core.intervals import INTERVAL_TO_MS
from app.db.models import Candle, Symbol

LOGGER = logging.getLogger(__name__)

@dataclass(slots=True)
class LoadSummary:
    symbol: str
    interval: str
    rows_requested: int
    rows_inserted: int
    duplicates_skipped: int


@dataclass(slots=True)
class SyncSummary:
    symbols_total: int
    symbols_inserted: int
    symbols_updated: int
    symbols_skipped: int
    market_type: str


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

    def _count_candles(self, symbol: str, interval: str, market_type: str) -> int:
        stmt: Select[tuple[int]] = select(func.count()).select_from(Candle).where(
            Candle.symbol == symbol,
            Candle.interval == interval,
            Candle.market_type == market_type,
        )
        return self.db.execute(stmt).scalar_one()

    def load_candles(
        self,
        symbol: str,
        interval: str,
        market_type: str = settings.default_market_type,
        limit: int = 1000,
    ) -> LoadSummary:
        before_count = self._count_candles(symbol=symbol, interval=interval, market_type=market_type)
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
        rows_requested = len(parsed)

        if not parsed:
            return LoadSummary(
                symbol=symbol,
                interval=interval,
                rows_requested=0,
                rows_inserted=0,
                duplicates_skipped=0,
            )

        stmt = insert(Candle).values(parsed)
        stmt = stmt.on_conflict_do_nothing(
            index_elements=["symbol", "market_type", "interval", "open_time"]
        )
        result = self.db.execute(stmt)
        self.db.commit()

        inserted = result.rowcount or 0
        after_count = self._count_candles(symbol=symbol, interval=interval, market_type=market_type)
        inserted_actual = max(after_count - before_count, 0)
        duplicates = max(rows_requested - inserted_actual, 0)
        LOGGER.info(
            "Inserted candles",
            extra={
                "symbol": symbol,
                "interval": interval,
                "rows_requested": rows_requested,
                "inserted_rowcount": inserted,
                "inserted_actual": inserted_actual,
                "duplicates": duplicates,
                "rows_total": after_count,
            },
        )
        return LoadSummary(
            symbol=symbol,
            interval=interval,
            rows_requested=rows_requested,
            rows_inserted=inserted_actual,
            duplicates_skipped=duplicates,
        )

    def sync_symbols(self, market_type: str = settings.default_market_type) -> SyncSummary:
        started_at = perf_counter()
        instruments: list[dict] = []
        next_cursor: str | None = None

        while True:
            raw = self.client.get_symbols(market_type=market_type, cursor=next_cursor)
            result = raw.get("result", {})
            instruments.extend(result.get("list", []))
            next_cursor = result.get("nextPageCursor") or None
            if not next_cursor:
                break

        usdt_only = [row for row in instruments if row.get("quoteCoin") == "USDT"]
        symbols_total = len(usdt_only)
        inserted = 0
        updated = 0
        skipped = 0
        existing_symbols = {
            symbol.symbol: symbol
            for symbol in self.db.execute(select(Symbol).where(Symbol.market_type == market_type)).scalars().all()
        }

        for row in usdt_only:
            symbol_name = row.get("symbol", "")
            existing = existing_symbols.get(symbol_name)
            launch_time = row.get("launchTime")
            launch_dt = datetime.fromtimestamp(int(launch_time) / 1000, tz=UTC) if launch_time else None
            payload = {
                "market_type": market_type,
                "base_coin": row.get("baseCoin", ""),
                "quote_coin": row.get("quoteCoin", ""),
                "status": row.get("status", ""),
                "tick_size": float(row.get("priceFilter", {}).get("tickSize", 0.0)),
                "qty_step": float(row.get("lotSizeFilter", {}).get("qtyStep", 0.0)),
                "min_order_qty": float(row.get("lotSizeFilter", {}).get("minOrderQty", 0.0)),
                "launch_time": launch_dt,
            }
            if existing is None:
                self.db.add(Symbol(symbol=symbol_name, updated_at=datetime.now(UTC), **payload))
                inserted += 1
                continue

            changed = False
            for field, value in payload.items():
                if getattr(existing, field) != value:
                    setattr(existing, field, value)
                    changed = True
            if changed:
                existing.updated_at = datetime.now(UTC)
                updated += 1
            else:
                skipped += 1

        self.db.commit()
        duration_ms = (perf_counter() - started_at) * 1000
        LOGGER.info(
            "Symbols sync completed",
            extra={"symbols_total": symbols_total, "duration_ms": round(duration_ms, 2), "market_type": market_type},
        )
        return SyncSummary(
            symbols_total=symbols_total,
            symbols_inserted=inserted,
            symbols_updated=updated,
            symbols_skipped=skipped,
            market_type=market_type,
        )
