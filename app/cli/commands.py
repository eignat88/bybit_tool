import typer

from app.core.levels_calculator import LevelsCalculator
from app.core.value_scanner import ValueScanner
from app.db.repository import init_db

app = typer.Typer(help="Bybit Market Decision System CLI")


@app.command("init-db")
def init_db_command() -> None:
    """Create MVP tables."""
    init_db()
    typer.echo("Database schema initialized")


@app.command("load")
def load(symbols: str = "ALL", interval: str = "60") -> None:
    typer.echo(f"TODO load candles: symbols={symbols}, interval={interval}")


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
