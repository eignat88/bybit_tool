from __future__ import annotations

import logging
import statistics
import time
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.bybit_client import BybitAPIError
from app.core.indicators import calculate_bollinger_bands, calculate_rsi
from app.core.market_loader import MarketLoader
from app.db.models import Symbol

LOGGER = logging.getLogger(__name__)

_TIMEFRAME_TO_INTERVAL = {"15m": "15", "30m": "30", "1h": "60", "2h": "120", "4h": "240", "1d": "D"}
_INTERVAL_TO_TIMEFRAME = {v: k for k, v in _TIMEFRAME_TO_INTERVAL.items()}


@dataclass(slots=True)
class SpotScanRow:
    symbol: str
    timeframe: str
    close: float
    volume: float
    volume_24h: float
    rsi: float
    bb_mid: float
    bb_upper: float
    bb_lower: float
    bb_percent_b: float | None
    bb_bandwidth: float | None
    long_signal: bool
    short_signal: bool
    trend_up: bool
    trend_down: bool
    signal_type: str
    signal_rank: int
    candles_count: int
    volume_24h_candles_used: int


@dataclass(slots=True)
class SpotScanSummary:
    symbols_total: int
    symbols_processed: int
    symbols_skipped: int
    elapsed_time_sec: float


class SpotScreener:
    def __init__(self, db: Session, loader: MarketLoader) -> None:
        self.db = db
        self.loader = loader

    def scan(self, timeframe: str = "2h", limit: int = 200, bb_period: int = 20, bb_mult: float = 2.0, rsi_period: int = 14, max_symbols: int = 0, auto_sync_symbols: bool = True) -> tuple[list[SpotScanRow], SpotScanSummary]:
        started = time.perf_counter()
        interval, normalized_tf = normalize_spot_timeframe(timeframe)
        symbols = self._get_spot_symbols(auto_sync_symbols=auto_sync_symbols)
        if max_symbols > 0:
            symbols = symbols[:max_symbols]
        rows: list[SpotScanRow] = []
        skipped = 0
        required = max(bb_period, rsi_period + 1)

        for symbol in symbols:
            try:
                payload = self.loader.client.get_klines(symbol=symbol, interval=interval, market_type="spot", limit=limit)
                raw = payload.get("result", {}).get("list", [])
                if not raw:
                    raise ValueError("empty_ohlcv")
                parsed = self.loader._parse_klines(raw, symbol=symbol, interval=interval, market_type="spot")
                closes = [x["close"] for x in parsed]
                volumes = [x["volume"] for x in parsed]
                open_times = [x["open_time"] for x in parsed]
                if len(closes) < required:
                    raise ValueError(f"insufficient_history candles={len(closes)} required={required}")

                bb = calculate_bollinger_bands(closes, period=bb_period, mult=bb_mult)
                rsi = calculate_rsi(closes, period=rsi_period)
                close = closes[-1]
                volume = volumes[-1]
                volume_24h, used = calculate_volume_24h(volumes, open_times)
                long_signal = close < bb.lower and rsi < 30
                short_signal = close > bb.upper and rsi > 70
                trend_up = close > bb.mid and rsi > 50
                trend_down = close < bb.mid and rsi < 50
                signal_type, signal_rank = resolve_signal(long_signal, short_signal, trend_up, trend_down)
                rows.append(SpotScanRow(symbol=symbol, timeframe=normalized_tf, close=close, volume=volume, volume_24h=volume_24h, rsi=rsi, bb_mid=bb.mid, bb_upper=bb.upper, bb_lower=bb.lower, bb_percent_b=bb.percent_b, bb_bandwidth=bb.bandwidth, long_signal=long_signal, short_signal=short_signal, trend_up=trend_up, trend_down=trend_down, signal_type=signal_type, signal_rank=signal_rank, candles_count=len(closes), volume_24h_candles_used=used))
            except (BybitAPIError, ValueError, ZeroDivisionError) as exc:
                skipped += 1
                LOGGER.warning("Skip symbol=%s reason=%s", symbol, exc)

        rows.sort(key=lambda r: (-r.signal_rank, r.rsi, -r.volume_24h))
        elapsed = time.perf_counter() - started
        return rows, SpotScanSummary(len(symbols), len(rows), skipped, elapsed)

    def _get_spot_symbols(self, *, auto_sync_symbols: bool) -> list[str]:
        stmt = select(Symbol.symbol).where(Symbol.market_type == "spot", Symbol.quote_coin == "USDT", Symbol.status.in_(["Trading", "TRADING", "tradable", "Tradable"]))
        symbols = [s for (s,) in self.db.execute(stmt)]
        if symbols:
            return symbols
        if auto_sync_symbols:
            self.loader.sync_symbols(market_type="spot")
            symbols = [s for (s,) in self.db.execute(stmt)]
        return symbols


def normalize_spot_timeframe(timeframe: str) -> tuple[str, str]:
    value = timeframe.strip().lower()
    if value in _TIMEFRAME_TO_INTERVAL:
        return _TIMEFRAME_TO_INTERVAL[value], value
    upper = timeframe.strip().upper()
    if upper in _INTERVAL_TO_TIMEFRAME:
        return upper, _INTERVAL_TO_TIMEFRAME[upper]
    raise ValueError(f"Unsupported timeframe/interval: {timeframe}")


def calculate_volume_24h(volumes: list[float], open_times: list[object]) -> tuple[float, int]:
    if len(volumes) == 1:
        return volumes[0], 1
    ts = [int(t.timestamp()) for t in open_times]
    diffs = [b - a for a, b in zip(ts, ts[1:], strict=False) if b > a]
    candle_sec = statistics.median(diffs) if diffs else 86400
    candles_24h = max(1, round(1440 / (candle_sec / 60)))
    used = min(candles_24h, len(volumes))
    return float(sum(volumes[-used:])), used


def resolve_signal(long_signal: bool, short_signal: bool, trend_up: bool, trend_down: bool) -> tuple[str, int]:
    if long_signal:
        return "long", 4
    if short_signal:
        return "short", 3
    if trend_up:
        return "trend_up", 2
    if trend_down:
        return "trend_down", 1
    return "neutral", 0
