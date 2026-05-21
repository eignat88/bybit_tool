from __future__ import annotations

import logging
import time
from datetime import UTC, datetime
from pathlib import Path

import typer
from sqlalchemy import func, select

from app.core.bybit_client import BybitClient
from app.core.levels_calculator import LevelsCalculator
from app.core.market_loader import MarketLoader
from app.core.value_scanner import ValueScanner
from app.db.models import Candle, Symbol
from app.db.repository import SessionLocal, init_db

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s - %(message)s")
LOGGER = logging.getLogger(__name__)

app = typer.Typer(help="Bybit Market Decision System CLI")


@app.command("init-db")
def init_db_command() -> None:
    """Create MVP tables."""
    init_db()
    typer.echo("Database schema initialized")


@app.command("load")
def load(symbols: str = "ALL", intervals: str = "60") -> None:
    started = time.perf_counter()
    allowed_intervals = {"15", "60", "240", "D"}
    interval_list = [i.strip().upper() for i in intervals.split(",") if i.strip()]
    if not interval_list:
        raise typer.BadParameter("intervals must not be empty")
    unsupported = [x for x in interval_list if x not in allowed_intervals]
    if unsupported:
        raise typer.BadParameter(f"Unsupported intervals: {','.join(unsupported)}")

    client = BybitClient()
    with SessionLocal() as db:
        if symbols.strip().upper() == "ALL":
            symbols_list = [s for (s,) in db.execute(select(Symbol.symbol).where(Symbol.quote_coin == "USDT"))]
        else:
            symbols_list = [s.strip().upper() for s in symbols.split(",") if s.strip()]
        loader = MarketLoader(client=client, db=db)
        rows_requested_total = 0
        rows_inserted_total = 0
        duplicates_total = 0
        symbols_processed: set[str] = set()
        intervals_processed: set[str] = set()
        for symbol in symbols_list:
            for interval in interval_list:
                try:
                    summary = loader.load_candles(symbol=symbol, interval=interval)
                    rows_requested_total += summary.rows_requested
                    rows_inserted_total += summary.rows_inserted
                    duplicates_total += summary.duplicates_skipped
                    symbols_processed.add(summary.symbol)
                    intervals_processed.add(summary.interval)
                    typer.echo(
                        f"symbol={summary.symbol} interval={summary.interval} "
                        f"rows_requested={summary.rows_requested} rows_inserted={summary.rows_inserted} "
                        f"duplicates_skipped={summary.duplicates_skipped}"
                    )
                except Exception as exc:  # noqa: BLE001
                    typer.echo(
                        f"symbol={symbol} interval={interval} "
                        f"rows_requested=0 rows_inserted=0 error={type(exc).__name__}: {exc}",
                        err=True,
                    )
                    LOGGER.exception("Load failed for symbol=%s interval=%s", symbol, interval)

    elapsed = time.perf_counter() - started
    typer.echo(f"symbols_processed={len(symbols_processed)}")
    typer.echo(f"intervals_processed={len(intervals_processed)}")
    typer.echo(f"rows_requested_total={rows_requested_total}")
    typer.echo(f"rows_inserted_total={rows_inserted_total}")
    typer.echo(f"duplicates_skipped_total={duplicates_total}")
    typer.echo(f"elapsed_time_sec={elapsed:.2f}")


@app.command("sync-symbols")
def sync_symbols(market_type: str = "linear") -> None:
    started = time.perf_counter()
    with SessionLocal() as db:
        loader = MarketLoader(client=BybitClient(), db=db)
        summary = loader.sync_symbols(market_type=market_type)
    elapsed = time.perf_counter() - started
    typer.echo(f"symbols_total={summary.symbols_total}")
    typer.echo(f"symbols_inserted={summary.symbols_inserted}")
    typer.echo(f"symbols_updated={summary.symbols_updated}")
    typer.echo(f"symbols_skipped={summary.symbols_skipped}")
    typer.echo(f"market_type={summary.market_type}")
    typer.echo(f"elapsed_time_sec={elapsed:.2f}")


@app.command("db-stats")
def db_stats() -> None:
    with SessionLocal() as db:
        total_stmt = select(func.count()).select_from(Candle)
        total = db.execute(total_stmt).scalar_one()
        typer.echo(f"candles_total={total}")

        grouped_stmt = (
            select(
                Candle.symbol,
                Candle.interval,
                func.count().label("cnt"),
                func.min(Candle.open_time).label("min_ot"),
                func.max(Candle.open_time).label("max_ot"),
            )
            .group_by(Candle.symbol, Candle.interval)
            .order_by(Candle.symbol.asc(), Candle.interval.asc())
        )
        for symbol, interval, cnt, min_ot, max_ot in db.execute(grouped_stmt):
            last = db.execute(
                select(Candle.close, Candle.volume).where(
                    Candle.symbol == symbol, Candle.interval == interval, Candle.open_time == max_ot
                )
            ).first()
            last_close = last[0] if last else None
            last_volume = last[1] if last else None
            typer.echo(
                f"symbol={symbol} interval={interval} candles={cnt} "
                f"min_open_time={min_ot.isoformat()} max_open_time={max_ot.isoformat()} "
                f"last_close={last_close} last_volume={last_volume}"
            )


@app.command("candles")
def candles(symbol: str, interval: str, tail: int = 10) -> None:
    with SessionLocal() as db:
        stmt = (
            select(Candle)
            .where(Candle.symbol == symbol.upper(), Candle.interval == interval)
            .order_by(Candle.open_time.desc())
            .limit(tail)
        )
        rows = list(db.execute(stmt).scalars())
        if not rows:
            typer.echo(f"No candles found for symbol={symbol.upper()} interval={interval}")
            return
        for candle in reversed(rows):
            typer.echo(
                f"{candle.open_time.isoformat()} "
                f"o={candle.open} h={candle.high} l={candle.low} c={candle.close} v={candle.volume}"
            )


@app.command("scheduler")
def scheduler(symbols: str = "ALL") -> None:
    Path("logs").mkdir(parents=True, exist_ok=True)
    file_handler = logging.FileHandler("logs/scheduler.log")
    file_handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s - %(message)s"))
    logging.getLogger().addHandler(file_handler)
    typer.echo("Scheduler started")
    while True:
        now = datetime.now(UTC)
        intervals: list[str] = ["15"]
        if now.minute == 0:
            intervals.append("60")
        if now.minute == 0 and now.hour % 4 == 0:
            intervals.append("240")
        if now.minute == 0 and now.hour == 0:
            intervals.append("D")
        load(symbols=symbols, intervals=",".join(intervals))
        sleep_sec = 900 - (int(time.time()) % 900)
        time.sleep(max(sleep_sec, 1))


@app.command("scan")
def scan(strategy: str = "grid", top: int = 30) -> None:
    scanner = ValueScanner()
    rows = scanner.scan(strategy=strategy, top=top)
    for row in rows:
        typer.echo(f"{row.symbol}: score={row.grid_score:.1f} tier={row.tier}")


@app.command("levels")
def levels(symbol: str, interval: str = "120") -> None:
    calc = LevelsCalculator()
    result = calc.calculate(symbol=symbol, interval=interval)
    typer.echo(f"Levels calculated: {len(result)} for {symbol} @ {interval}")


@app.command("analyze")
def analyze(symbol: str, intervals: str = "D,H4,H1") -> None:
    typer.echo(f"TODO deep analysis for {symbol} intervals={intervals}")
