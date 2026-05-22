from __future__ import annotations

import logging
import time
from pathlib import Path

import typer
from sqlalchemy import func, select

from app.config.settings import settings
from app.core.bybit_client import BybitClient
from app.core.levels_calculator import LevelsCalculator
from app.core.intervals import validate_intervals_csv
from app.core.scheduler_runner import get_scheduler_intervals
from app.core.market_loader import MarketLoader
from app.core.value_scanner import ValueScanner
from app.core.report_builder import build_analysis_report
from app.db.models import Candle, Symbol
from app.db.repository import SessionLocal, init_db, migrate_db

from app.testing.db_validation import get_missing_levels_columns, validate_db_objects
from app.testing.report import render_lines
from app.testing.smoke_tests import run_self_test

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s - %(message)s")
LOGGER = logging.getLogger(__name__)

app = typer.Typer(help="Bybit Market Decision System CLI")


@app.command("init-db")
def init_db_command() -> None:
    """Apply Alembic migrations up to head."""
    try:
        init_db()
    except Exception as exc:  # noqa: BLE001
        typer.echo(f"init-db failed: {type(exc).__name__}: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    typer.echo("Database schema initialized via alembic upgrade head")


@app.command("migrate-db")
def migrate_db_command() -> None:
    """Apply Alembic migrations up to head."""
    try:
        migrate_db()
    except Exception as exc:  # noqa: BLE001
        typer.echo(f"migrate-db failed: {type(exc).__name__}: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    typer.echo("Database migrations applied via alembic upgrade head")


@app.command("load")
def load(
    symbols: str = typer.Option("ALL", "--symbols"),
    intervals: str = typer.Option("60", "--intervals"),
    market_type: str = typer.Option(settings.default_market_type, "--market-type"),
) -> None:
    run_load(symbols=symbols, intervals=intervals, market_type=market_type)


def run_load(symbols: str, intervals: str, market_type: str) -> None:
    started = time.perf_counter()
    try:
        interval_list = validate_intervals_csv(intervals)
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc

    client = BybitClient()
    with SessionLocal() as db:
        if symbols.strip().upper() == "ALL":
            symbols_list = [
                s
                for (s,) in db.execute(
                    select(Symbol.symbol).where(Symbol.quote_coin == "USDT", Symbol.market_type == market_type)
                )
            ]
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
                    summary = loader.load_candles(symbol=symbol, interval=interval, market_type=market_type)
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
                    LOGGER.error("Load failed for symbol=%s interval=%s error=%s", symbol, interval, exc)

    elapsed = time.perf_counter() - started
    typer.echo(f"symbols_processed={len(symbols_processed)}")
    typer.echo(f"intervals_processed={len(intervals_processed)}")
    typer.echo(f"rows_requested_total={rows_requested_total}")
    typer.echo(f"rows_inserted_total={rows_inserted_total}")
    typer.echo(f"duplicates_skipped_total={duplicates_total}")
    typer.echo(f"elapsed_time_sec={elapsed:.2f}")


@app.command("sync-symbols")
def sync_symbols(market_type: str = settings.default_market_type) -> None:
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
                Candle.market_type,
                Candle.interval,
                func.count().label("cnt"),
                func.min(Candle.open_time).label("min_ot"),
                func.max(Candle.open_time).label("max_ot"),
            )
            .group_by(Candle.symbol, Candle.market_type, Candle.interval)
            .order_by(Candle.symbol.asc(), Candle.market_type.asc(), Candle.interval.asc())
        )
        for symbol, market_type, interval, cnt, min_ot, max_ot in db.execute(grouped_stmt):
            last = db.execute(
                select(Candle.close, Candle.volume).where(
                    Candle.symbol == symbol,
                    Candle.market_type == market_type,
                    Candle.interval == interval,
                    Candle.open_time == max_ot,
                )
            ).first()
            last_close = last[0] if last else None
            last_volume = last[1] if last else None
            typer.echo(
                f"symbol={symbol} market_type={market_type} interval={interval} candles={cnt} "
                f"min_open_time={min_ot.isoformat()} max_open_time={max_ot.isoformat()} "
                f"last_close={last_close} last_volume={last_volume}"
            )


@app.command("candles")
def candles(
    symbol: str,
    interval: str,
    tail: int = 10,
    market_type: str = typer.Option(settings.default_market_type, "--market-type"),
) -> None:
    with SessionLocal() as db:
        stmt = (
            select(Candle)
            .where(Candle.symbol == symbol.upper(), Candle.market_type == market_type, Candle.interval == interval)
            .order_by(Candle.open_time.desc())
            .limit(tail)
        )
        rows = list(db.execute(stmt).scalars())
        if not rows:
            typer.echo(f"No candles found for symbol={symbol.upper()} market_type={market_type} interval={interval}")
            return
        for candle in reversed(rows):
            typer.echo(
                f"{candle.open_time.isoformat()} "
                f"o={candle.open} h={candle.high} l={candle.low} c={candle.close} v={candle.volume}"
            )


@app.command("scheduler")
def scheduler(
    symbols: str = typer.Option("ALL", "--symbols"),
    once: bool = typer.Option(False, "--once"),
    market_type: str = typer.Option(settings.default_market_type, "--market-type"),
) -> None:
    Path("logs").mkdir(parents=True, exist_ok=True)
    file_handler = logging.FileHandler("logs/scheduler.log")
    file_handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s - %(message)s"))
    logging.getLogger().addHandler(file_handler)
    typer.echo("Scheduler started")
    while True:
        intervals = get_scheduler_intervals()
        run_load(symbols=symbols, intervals=",".join(intervals), market_type=market_type)
        if once:
            break
        sleep_sec = 900 - (int(time.time()) % 900)
        time.sleep(max(sleep_sec, 1))


@app.command("scan")
def scan(
    strategy: str = "grid",
    top: int = 30,
    interval: str = typer.Option("60", "--interval"),
    market_type: str = typer.Option(settings.default_market_type, "--market-type"),
    candles_limit: int = typer.Option(120, "--candles-limit"),
) -> None:
    scanner = ValueScanner()
    rows = scanner.scan(
        strategy=strategy,
        top=top,
        interval=interval,
        market_type=market_type,
        candles_limit=candles_limit,
    )
    for row in rows:
        typer.echo(
            f"{row.symbol}: price={row.price:.6f} score={row.grid_score:.2f} tier={row.tier} "
            f"atr%={row.atr_pct:.2f} rsi={row.rsi:.2f} adx={row.adx:.2f} "
            f"vwap_dev%={row.vwap_deviation_pct:.2f} bb_width%={row.bb_width_pct:.2f}"
        )


@app.command("levels")
def levels(
    symbol: str,
    interval: str = "120",
    market_type: str = typer.Option(settings.default_market_type, "--market-type"),
    export_csv: str = typer.Option("", "--export-csv", help="Path to save TradingView CSV."),
) -> None:
    calc = LevelsCalculator()
    result = calc.calculate(symbol=symbol, interval=interval, market_type=market_type)
    typer.echo(f"Levels calculated: {len(result)} for {symbol.upper()} @ {interval} ({market_type})")

    by_source: dict[str, int] = {}
    by_type: dict[str, int] = {}
    for row in result:
        by_source[row.source_type] = by_source.get(row.source_type, 0) + 1
        by_type[row.level_type] = by_type.get(row.level_type, 0) + 1

    if by_source:
        typer.echo("By source_type:")
        for key in sorted(by_source):
            typer.echo(f"  {key}: {by_source[key]}")

    if by_type:
        typer.echo("By level_type:")
        for key in sorted(by_type):
            typer.echo(f"  {key}: {by_type[key]}")

    if export_csv:
        csv_body = calc.to_tradingview_csv(result)
        export_path = Path(export_csv)
        export_path.parent.mkdir(parents=True, exist_ok=True)
        export_path.write_text(csv_body + "\n", encoding="utf-8")
        typer.echo(f"TradingView CSV exported to {export_csv}")


@app.command("analyze")
def analyze(
    symbol: str,
    intervals: str = "D,H4,H1",
    market_type: str = typer.Option(settings.default_market_type, "--market-type"),
) -> None:
    normalized_symbol = symbol.upper()
    try:
        with SessionLocal() as db:
            report, payload, markdown = build_analysis_report(
                db=db,
                client=BybitClient(),
                symbol=normalized_symbol,
                intervals=intervals,
                market_type=market_type,
            )
    except ValueError as exc:
        typer.echo(
            f"analyze failed for symbol={normalized_symbol} intervals={intervals}: {exc}",
            err=True,
        )
        raise typer.Exit(code=2) from exc

    typer.echo(markdown)
    typer.echo("")
    typer.echo(f"report_id={report.id}")
    typer.echo(f"timeframes={','.join(payload['timeframes'])}")


@app.command("db-check")
def db_check() -> None:
    missing_levels_columns = get_missing_levels_columns()
    if missing_levels_columns:
        typer.echo("DB schema is outdated.")
        typer.echo("Missing columns in levels:")
        for column_name in missing_levels_columns:
            typer.echo(f"- {column_name}")
        typer.echo("")
        typer.echo("Run:")
        typer.echo("python main.py migrate-db")
        raise typer.Exit(code=1)

    results = validate_db_objects()
    from app.testing.cli_validation import validate_market_type_consistency

    results.append(validate_market_type_consistency())
    has_fail = False
    for r in results:
        status = "OK" if r.ok else "FAIL"
        typer.echo(f"[{status}] {r.name}: {r.message}")
        for d in r.details:
            typer.echo(f"  - {d}")
        has_fail = has_fail or not r.ok
    raise typer.Exit(code=1 if has_fail else 0)


@app.command("self-test")
def self_test(
    no_artifacts: bool = typer.Option(
        False,
        "--no-artifacts",
        help="Disable report files (recommended for CI pipelines).",
    ),
    quick: bool = typer.Option(
        False,
        "--quick",
        help="Run quick checks only (skip compileall). Recommended for fast CI smoke runs.",
    ),
) -> None:
    report = run_self_test(quick=quick, write_artifacts=not no_artifacts)
    for line in render_lines(report):
        typer.echo(line)
    raise typer.Exit(code=0 if report.success else 1)


@app.command("seed-dev-data")
def seed_dev_data() -> None:
    run_load(symbols="BTCUSDT,ETHUSDT", intervals="15,60", market_type=settings.default_market_type)
