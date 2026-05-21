from __future__ import annotations

import logging
import time

import typer

from app.core.bybit_client import BybitClient
from app.core.levels_calculator import LevelsCalculator
from app.core.market_loader import MarketLoader
from app.core.value_scanner import ValueScanner
from app.db.repository import SessionLocal, init_db

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s - %(message)s")

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
            summary = loader.load_candles(symbol=symbol, interval=interval)
            typer.echo(
                f"symbol={summary.symbol} interval={summary.interval} "
                f"rows_inserted={summary.rows_inserted} duplicates_skipped={summary.duplicates_skipped}"
            )

    elapsed = time.perf_counter() - started
    typer.echo(f"elapsed_time_sec={elapsed:.2f}")


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
