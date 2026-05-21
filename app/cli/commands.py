from __future__ import annotations

import logging
import time

import typer
from sqlalchemy import func, select

from app.core.bybit_client import BybitClient
from app.core.levels_calculator import LevelsCalculator
from app.core.market_loader import MarketLoader
from app.core.value_scanner import ValueScanner
from app.db.models import Candle
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
def load(symbols: str = "ALL", interval: str = "60") -> None:
    started = time.perf_counter()
    symbols_list = [s.strip().upper() for s in symbols.split(",") if s.strip()]
    if symbols == "ALL":
        raise typer.BadParameter("ALL is not implemented yet. Provide symbols like BTCUSDT,ETHUSDT")

    client = BybitClient()
    with SessionLocal() as db:
        loader = MarketLoader(client=client, db=db)
        for symbol in symbols_list:
            try:
                summary = loader.load_candles(symbol=symbol, interval=interval)
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
                LOGGER.error("Load failed for symbol=%s interval=%s: %s", symbol, interval, exc)

    elapsed = time.perf_counter() - started
    typer.echo(f"elapsed_time_sec={elapsed:.2f}")


@app.command("db-stats")
def db_stats() -> None:
    with SessionLocal() as db:
        total_stmt = select(func.count()).select_from(Candle)
        total = db.execute(total_stmt).scalar_one()
        typer.echo(f"candles_total={total}")

        grouped_stmt = (
            select(Candle.symbol, Candle.interval, func.count().label("cnt"))
            .group_by(Candle.symbol, Candle.interval)
            .order_by(Candle.symbol.asc(), Candle.interval.asc())
        )
        for symbol, interval, cnt in db.execute(grouped_stmt):
            typer.echo(f"symbol={symbol} interval={interval} candles={cnt}")


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
            typer.echo("No candles found")
            return
        for candle in reversed(rows):
            typer.echo(
                f"{candle.open_time.isoformat()} "
                f"o={candle.open} h={candle.high} l={candle.low} c={candle.close} v={candle.volume}"
            )


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
