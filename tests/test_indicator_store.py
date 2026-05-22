from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker

from app.core.indicator_store import IndicatorStore
from app.db.models import Base, Candle, IndicatorValue, Symbol


def _session_factory():
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, autoflush=False, autocommit=False, class_=Session)


def _seed_symbol(sf, symbol: str = "BTCUSDT"):
    with sf() as db:
        db.add(Symbol(symbol=symbol, market_type="linear", quote_coin="USDT", status="Trading", base_coin="BTC"))
        db.commit()


def _seed_candles(sf, symbol: str, n: int, interval: str = "60"):
    start = datetime(2026, 1, 1, tzinfo=UTC)
    with sf() as db:
        for i in range(n):
            close = 100 + i * 0.5
            db.add(
                Candle(
                    symbol=symbol,
                    market_type="linear",
                    interval=interval,
                    open_time=start + timedelta(hours=i),
                    open=close - 0.1,
                    high=close + 1,
                    low=close - 1,
                    close=close,
                    volume=1000 + i,
                    turnover=100000 + i,
                )
            )
        db.commit()


def test_indicator_store_successful_save():
    sf = _session_factory()
    _seed_symbol(sf)
    _seed_candles(sf, "BTCUSDT", 40)

    result = IndicatorStore(session_factory=sf).calculate_and_store(["BTCUSDT"], interval="60")

    assert result.symbols_processed == 1
    assert result.indicators_saved_total == 5
    with sf() as db:
        rows = list(db.execute(select(IndicatorValue)).scalars())
    assert len(rows) == 5
    assert {r.indicator_name for r in rows} == {"atr_pct", "rsi", "adx", "vwap_deviation_pct", "bb_width_pct"}
    assert all(r.calc_version == "v1" for r in rows)
    assert all(r.value is not None for r in rows)


def test_indicator_store_second_run_no_duplicates():
    sf = _session_factory()
    _seed_symbol(sf)
    _seed_candles(sf, "BTCUSDT", 40)
    store = IndicatorStore(session_factory=sf)

    store.calculate_and_store(["BTCUSDT"], interval="60")
    store.calculate_and_store(["BTCUSDT"], interval="60")

    with sf() as db:
        total = db.execute(select(func.count()).select_from(IndicatorValue)).scalar_one()
    assert total == 5


def test_indicator_store_insufficient_history():
    sf = _session_factory()
    _seed_symbol(sf)
    _seed_candles(sf, "BTCUSDT", 10)

    result = IndicatorStore(session_factory=sf).calculate_and_store(["BTCUSDT"], interval="60")

    assert result.symbols_skipped == 1
    assert result.rows[0].reason == "insufficient_history"
    with sf() as db:
        total = db.execute(select(func.count()).select_from(IndicatorValue)).scalar_one()
    assert total == 0


def test_indicator_store_missing_symbol_does_not_break_others():
    sf = _session_factory()
    _seed_symbol(sf, "BTCUSDT")
    _seed_candles(sf, "BTCUSDT", 40)

    result = IndicatorStore(session_factory=sf).calculate_and_store(["BTCUSDT", "BADUSDT"], interval="60")

    assert result.symbols_processed == 1
    assert result.symbols_skipped == 1
    statuses = {row.symbol: row.status for row in result.rows}
    assert statuses["BTCUSDT"] == "ok"
    assert statuses["BADUSDT"] == "skipped"


def test_indicators_cli_smoke():
    import subprocess

    proc = subprocess.run(
        ["python", "main.py", "indicators", "--symbols", "BTCUSDT", "--interval", "60", "--market-type", "linear"],
        capture_output=True,
        text=True,
    )
    output = f"{proc.stdout}\n{proc.stderr}"
    assert proc.returncode == 0, output
    assert "indicators_saved_total=" in output
