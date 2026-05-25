from __future__ import annotations

import logging
import json
import time
from pathlib import Path

import typer
import sqlalchemy as sa
from sqlalchemy import func, select

from app.config.settings import settings
from app.core.bybit_client import BybitAPIError, BybitClient
from app.core.levels_calculator import LevelsCalculator
from app.core.indicator_store import IndicatorStore
from app.core.intervals import normalize_intervals, validate_intervals_csv
from app.core.scheduler_runner import get_scheduler_intervals
from app.core.market_loader import MarketLoader
from app.core.value_scanner import ValueScanner
from app.core.report_builder import build_analysis_report, find_nearest_levels
from app.core.recommendation_builder import RecommendationBuilder, build_recommendation
from app.core.trade_scenarios import build_trade_scenarios
from app.core.domain_errors import AnalysisReportNotFoundError, DataNotFoundWarning, RecommendationInputError
from app.db.models import Candle, Symbol, Level
from app.db.models import AnalysisReport, BotRecommendation, ScanResult
from app.db.repository import SessionLocal, init_db, migrate_db

from app.testing.db_validation import get_missing_levels_columns, validate_db_objects
from app.testing.report import render_lines
from app.testing.smoke_tests import run_self_test

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s - %(message)s")
LOGGER = logging.getLogger(__name__)

app = typer.Typer(help="Bybit Market Decision System CLI")


def _normalize_timeframes(value: object) -> tuple[str, ...]:
    if isinstance(value, str):
        raw = [item.strip().upper() for item in value.split(",") if item.strip()]
    elif isinstance(value, list):
        raw = [str(item).strip().upper() for item in value if str(item).strip()]
    else:
        raw = []
    return tuple(sorted(set(raw)))


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


@app.command("load-all")
def load_all(
    intervals: str = typer.Option("60", "--intervals"),
    market_type: str = typer.Option(settings.default_market_type, "--market-type"),
) -> None:
    """Sync symbols from Bybit, then load candles for all available USDT pairs."""
    started = time.perf_counter()
    with SessionLocal() as db:
        loader = MarketLoader(client=BybitClient(), db=db)
        summary = loader.sync_symbols(market_type=market_type)
    typer.echo(f"symbols_total={summary.symbols_total}")
    typer.echo(f"symbols_inserted={summary.symbols_inserted}")
    typer.echo(f"symbols_updated={summary.symbols_updated}")
    typer.echo(f"symbols_skipped={summary.symbols_skipped}")
    typer.echo(f"market_type={summary.market_type}")

    run_load(symbols="ALL", intervals=intervals, market_type=market_type)
    elapsed = time.perf_counter() - started
    typer.echo(f"load_all_elapsed_time_sec={elapsed:.2f}")


def run_load(symbols: str, intervals: str, market_type: str) -> None:
    started = time.perf_counter()
    try:
        interval_list, _ = normalize_intervals(intervals)
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


@app.command("indicators")
def indicators(
    symbols: str = typer.Option("ALL", "--symbols"),
    interval: str = typer.Option("60", "--interval"),
    market_type: str = typer.Option(settings.default_market_type, "--market-type"),
    limit: int = typer.Option(300, "--limit"),
    calc_version: str = typer.Option("v1", "--calc-version"),
) -> None:
    store = IndicatorStore()
    symbols_list = [s.strip().upper() for s in symbols.split(",") if s.strip()] or ["ALL"]
    result = store.calculate_and_store(
        symbols=symbols_list,
        interval=interval,
        market_type=market_type,
        limit=limit,
        calc_version=calc_version,
    )

    for row in result.rows:
        if row.status == "ok":
            typer.echo(
                f"symbol={row.symbol} interval={row.interval} market_type={row.market_type} "
                f"open_time={row.open_time} indicators_saved={row.indicators_saved} status=ok"
            )
            for name in ("atr_pct", "rsi", "adx", "vwap_deviation_pct", "bb_width_pct"):
                typer.echo(f"  {name}={row.values[name]:.6f}")
            typer.echo("")
        elif row.status == "skipped":
            typer.echo(
                f"symbol={row.symbol} interval={row.interval} market_type={row.market_type} "
                f"status=skipped reason={row.reason} candles={row.candles_count}"
            )
        else:
            typer.echo(
                f"symbol={row.symbol} interval={row.interval} market_type={row.market_type} "
                f"status=failed error={row.error}"
            )

    typer.echo(f"symbols_requested={result.symbols_requested}")
    typer.echo(f"symbols_processed={result.symbols_processed}")
    typer.echo(f"symbols_skipped={result.symbols_skipped}")
    typer.echo(f"symbols_failed={result.symbols_failed}")
    typer.echo(f"indicators_saved_total={result.indicators_saved_total}")
    typer.echo(f"elapsed_time_sec={result.elapsed_time_sec:.2f}")


@app.command("levels")
def levels(
    symbol: str,
    interval: str = "120",
    market_type: str = typer.Option(settings.default_market_type, "--market-type"),
    show: bool = typer.Option(
        False,
        "--show",
        help="Show full support/resistance lists (ignored by --nearest and --json).",
    ),
    nearest: bool = typer.Option(
        False,
        "--nearest",
        help="Show only nearest support/resistance in text format (ignored by --json).",
    ),
    json_output: bool = typer.Option(
        False,
        "--json",
        help="Print JSON output (highest priority: --json > --nearest > --show > default).",
    ),
    export_csv: str = typer.Option("", "--export-csv", help="Path to save TradingView CSV."),
) -> None:
    calc = LevelsCalculator()
    normalized_symbol = symbol.upper()
    result = calc.calculate(symbol=normalized_symbol, interval=interval, market_type=market_type)

    with SessionLocal() as db:
        latest_candle = db.execute(
            select(Candle.close)
            .where(Candle.symbol == normalized_symbol, Candle.market_type == market_type, Candle.interval == interval)
            .order_by(Candle.open_time.desc())
            .limit(1)
        ).first()
    current_price = float(latest_candle[0]) if latest_candle else 0.0

    def _round(value: float | None) -> float | None:
        return None if value is None else round(float(value), 4)

    def _signed_pct(value: float | None) -> str:
        if value is None:
            return "n/a"
        return f"{value:+.2f}%"

    def _enrich(level: object) -> dict[str, float | str | None]:
        level_price = float(level.level_price)
        distance_abs = level_price - current_price
        distance_pct = (distance_abs / current_price * 100.0) if current_price else None
        return {
            "level_price": _round(level_price),
            "level_type": str(level.level_type),
            "source_type": str(level.source_type),
            "strength_score": _round(float(level.strength_score)),
            "distance_abs": _round(distance_abs),
            "distance_pct": _round(distance_pct),
        }

    enriched_levels = [_enrich(level) for level in result]

    supports = sorted(
        [lvl for lvl in enriched_levels if lvl["level_type"].lower() == "support" and lvl["level_price"] <= current_price],
        key=lambda lvl: lvl["level_price"],
        reverse=True,
    )
    resistances = sorted(
        [lvl for lvl in enriched_levels if lvl["level_type"].lower() == "resistance" and lvl["level_price"] >= current_price],
        key=lambda lvl: lvl["level_price"],
    )
    nearest_support = supports[0] if supports else None
    nearest_resistance = resistances[0] if resistances else None

    if json_output:
        payload: dict[str, object] = {
            "symbol": normalized_symbol,
            "interval": interval,
            "current_price": current_price,
            "nearest_support": nearest_support,
            "nearest_resistance": nearest_resistance,
        }
        if show:
            payload["supports"] = supports
            payload["resistances"] = resistances
        typer.echo(json.dumps(payload, ensure_ascii=False, indent=2))
    elif nearest:
        nearest_support_price = f"{nearest_support['level_price']:.6f}" if nearest_support else "n/a"
        nearest_resistance_price = f"{nearest_resistance['level_price']:.6f}" if nearest_resistance else "n/a"
        typer.echo(
            f"{normalized_symbol} @ {interval} ({market_type}) current_price={current_price:.6f} "
            f"nearest_support={nearest_support_price} "
            f"nearest_resistance={nearest_resistance_price}"
        )
        if nearest_support:
            typer.echo(
                f"  support: price={nearest_support['level_price']:.6f} "
                f"distance={nearest_support['distance_abs']:+.6f} ({_signed_pct(nearest_support['distance_pct'])}) "
                f"strength={nearest_support['strength_score']:.3f} source={nearest_support['source_type']}"
            )
        if nearest_resistance:
            typer.echo(
                f"  resistance: price={nearest_resistance['level_price']:.6f} "
                f"distance={nearest_resistance['distance_abs']:+.6f} ({_signed_pct(nearest_resistance['distance_pct'])}) "
                f"strength={nearest_resistance['strength_score']:.3f} source={nearest_resistance['source_type']}"
            )
    elif show:
        typer.echo(f"Levels calculated: {len(result)} for {normalized_symbol} @ {interval} ({market_type})")
        typer.echo(f"current_price={current_price:.6f}")
        typer.echo("Support levels:")
        for lvl in supports:
            typer.echo(
                f"  price={lvl['level_price']:.6f} distance={lvl['distance_abs']:+.6f} "
                f"({_signed_pct(lvl['distance_pct'])}) strength={lvl['strength_score']:.3f} "
                f"source={lvl['source_type']}"
            )
        typer.echo("Resistance levels:")
        for lvl in resistances:
            typer.echo(
                f"  price={lvl['level_price']:.6f} distance={lvl['distance_abs']:+.6f} "
                f"({_signed_pct(lvl['distance_pct'])}) strength={lvl['strength_score']:.3f} "
                f"source={lvl['source_type']}"
            )
    else:
        typer.echo(f"Levels calculated: {len(result)} for {normalized_symbol} @ {interval} ({market_type})")

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
    recommend: bool = typer.Option(False, "--recommend"),
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
    except BybitAPIError:
        typer.echo(f"Cannot analyze {normalized_symbol}: no candles found or symbol is invalid.", err=True)
        raise typer.Exit(code=1)
    except ValueError as exc:
        message = str(exc).lower()
        if "недостаточно свечей" in message or "not enough candles" in message:
            typer.echo(f"Cannot analyze {normalized_symbol}: no candles found or symbol is invalid.", err=True)
            raise typer.Exit(code=1)
        typer.echo(f"analyze failed for symbol={normalized_symbol} intervals={intervals}: {exc}", err=True)
        raise typer.Exit(code=2)

    typer.echo(markdown)
    typer.echo("")
    typer.echo(f"report_id={report.id}")
    if not payload or not payload.get("timeframes"):
        typer.echo(f"Cannot analyze {normalized_symbol}: analysis report is empty.", err=True)
        raise typer.Exit(code=1)
    _, timeframe_set = normalize_intervals(payload["timeframes"])
    typer.echo(f"timeframes={timeframe_set}")

    if recommend:
        intervals_list, _ = normalize_intervals(payload["timeframes"])
        try:
            with SessionLocal() as db:
                rec = build_recommendation(
                    db=db,
                    symbol=normalized_symbol,
                    market_type=market_type,
                    intervals=intervals_list,
                    source_report_id=report.id,
                )
        except AnalysisReportNotFoundError:
            typer.echo(f"No analysis report found for {normalized_symbol}. Run analyze first.", err=True)
            raise typer.Exit(code=1)
        except (DataNotFoundWarning, RecommendationInputError):
            typer.echo(f"No candles found for {normalized_symbol} {market_type}.", err=True)
            typer.echo("Cannot build recommendation.", err=True)
            raise typer.Exit(code=1)
        typer.echo(f"Recommendation saved: id={rec.id}")
        typer.echo(f"market_type={rec.market_type}")
        typer.echo(f"source_report_id={rec.source_report_id}")
        typer.echo(f"symbol={rec.symbol}")
        typer.echo(f"strategy_type={rec.strategy_type}")
        typer.echo(f"confidence={rec.confidence:.2f}")


@app.command("recommend")
def recommend(
    symbol: str,
    intervals: str = typer.Option("D,H4,H1", "--intervals"),
    market_type: str = typer.Option(settings.default_market_type, "--market-type"),
) -> None:
    normalized_symbol = symbol.upper()
    interval_list, _ = normalize_intervals(intervals)
    try:
        with SessionLocal() as db:
            rec = build_recommendation(
                db=db,
                symbol=normalized_symbol,
                market_type=market_type,
                intervals=interval_list,
            )
    except AnalysisReportNotFoundError:
        typer.echo(f"No analysis report found for {normalized_symbol}. Run analyze first.", err=True)
        raise typer.Exit(code=1)
    except (DataNotFoundWarning, RecommendationInputError):
        typer.echo(f"No candles found for {normalized_symbol} {market_type}.", err=True)
        typer.echo("Cannot build recommendation.", err=True)
        raise typer.Exit(code=1)

    typer.echo(f"Recommendation saved: id={rec.id}")
    typer.echo(f"market_type={rec.market_type}")
    typer.echo(f"source_report_id={rec.source_report_id}")
    typer.echo(f"symbol={rec.symbol}")
    typer.echo(f"strategy_type={rec.strategy_type}")
    typer.echo(f"confidence={rec.confidence:.2f}")


@app.command("context")
def context(
    symbol: str,
    intervals: str = typer.Option("D,240,60", "--intervals"),
    market_type: str = typer.Option(settings.default_market_type, "--market-type"),
) -> None:
    normalized_symbol = symbol.strip().upper()
    normalized_market_type = market_type.strip().lower()
    interval_list, _ = normalize_intervals(intervals)

    with SessionLocal() as db:
        report_rows = db.execute(
            select(AnalysisReport)
            .where(
                AnalysisReport.symbol == normalized_symbol,
                AnalysisReport.report_json["market_type"].astext == normalized_market_type,
            )
            .order_by(AnalysisReport.created_at.desc(), AnalysisReport.id.desc())
        ).scalars().all()
        report = next(
            (
                candidate
                for candidate in report_rows
                if _normalize_timeframes((candidate.report_json or {}).get("timeframes")) == tuple(interval_list)
            ),
            None,
        )

        scan = db.execute(
            select(ScanResult)
            .where(ScanResult.symbol == normalized_symbol)
            .order_by(ScanResult.id.desc())
            .limit(1)
        ).scalar_one_or_none()
        price = float(scan.price) if scan is not None and scan.price is not None else None
        if price is None:
            candle = db.execute(
                select(Candle)
                .where(Candle.symbol == normalized_symbol, Candle.market_type == normalized_market_type)
                .order_by(Candle.open_time.desc(), Candle.id.desc())
                .limit(1)
            ).scalar_one_or_none()
            price = float(candle.close) if candle is not None else None

        nearest = find_nearest_levels(
            db=db, symbol=normalized_symbol, market_type=normalized_market_type, intervals=interval_list
        )

        primary_interval = nearest.get("primary_interval")
        level_rows = []
        if primary_interval:
            level_rows = db.execute(
                select(Level).where(
                    Level.symbol == normalized_symbol,
                    Level.market_type == normalized_market_type,
                    Level.interval == primary_interval,
                )
            ).scalars().all()
        supports = sorted(float(l.level_price) for l in level_rows if l.level_type.lower() == "support")
        resistances = sorted(float(l.level_price) for l in level_rows if l.level_type.lower() == "resistance")

        market_structure = {}
        if report is not None and isinstance(report.report_json, dict):
            market_structure = report.report_json.get("market_structure") or {}

        rec_status = "insufficient_data"
        rec_reason = "analysis_report_missing"
        if report is not None and isinstance(report.report_json, dict):
            rec_decision = RecommendationBuilder().build(report.report_json)
            rec_status = rec_decision.status
            rec_reason = rec_decision.reason or "ok"

        trade_scenarios = build_trade_scenarios(
            current_price=price,
            nearest_support=(nearest.get("nearest_support") or {}).get("level_price"),
            nearest_resistance=(nearest.get("nearest_resistance") or {}).get("level_price"),
            support_levels=supports,
            resistance_levels=resistances,
            trend_context=(market_structure.get(str(nearest.get("primary_interval"))) or {}).get("trend_regime"),
            risk_context=(report.report_json.get("risk_summary") or {}).get("overall_risk")
            if report is not None and isinstance(report.report_json, dict)
            else None,
        )

    def _signed_pct(value: float | None) -> str:
        if value is None:
            return "n/a"
        return f"{value:+.2f}%"

    typer.echo("Symbol/Price")
    if price is None:
        typer.echo(
            f"- {normalized_symbol} ({normalized_market_type}) price=n/a status=insufficient_data reason=no_price_available"
        )
    else:
        typer.echo(f"- {normalized_symbol} ({normalized_market_type}) price={price:.6f}")

    typer.echo("Trend")
    for tf in interval_list:
        trend_regime = (market_structure.get(str(tf)) or {}).get("trend_regime")
        trend_status = trend_regime or "insufficient_data"
        typer.echo(f"- {tf}: {trend_status}")

    typer.echo("Nearest levels")
    support = nearest.get("nearest_support")
    resistance = nearest.get("nearest_resistance")
    if support is None and resistance is None:
        typer.echo("- status=insufficient_data reason=no_levels_found_for_primary_interval")
    else:
        if support is None:
            typer.echo("- support: insufficient_data")
        else:
            typer.echo(f"- support: {support['level_price']:.6f} ({_signed_pct(support.get('distance_pct'))})")
        if resistance is None:
            typer.echo("- resistance: insufficient_data")
        else:
            typer.echo(f"- resistance: {resistance['level_price']:.6f} ({_signed_pct(resistance.get('distance_pct'))})")

    typer.echo("Risk")
    if scan is None:
        typer.echo("- overall: insufficient_data")
        typer.echo("- RSI: insufficient_data")
        typer.echo("- scanner_tier: insufficient_data")
    else:
        atr_pct = getattr(scan, "atr_pct", None)
        adx = getattr(scan, "adx", None)
        rsi = getattr(scan, "rsi", None)
        tier = getattr(scan, "tier", None)
        typer.echo(
            f"- overall: atr_pct={atr_pct if atr_pct is not None else 'n/a'} adx={adx if adx is not None else 'n/a'}"
        )
        typer.echo(f"- RSI: {rsi if rsi is not None else 'n/a'}")
        typer.echo(f"- scanner_tier: {tier if tier else 'n/a'}")

    typer.echo("Scenarios")
    typer.echo(f"- status: {trade_scenarios.get('status')}")
    typer.echo(
        f"- long_breakout_trigger: {trade_scenarios.get('long_breakout', {}).get('trigger_price') if trade_scenarios.get('long_breakout') else 'n/a'}"
    )
    typer.echo(f"- buy_zone: {trade_scenarios.get('buy_zone')}")
    typer.echo(
        f"- invalidation: {(trade_scenarios.get('invalidation') or {}).get('trigger_price') if trade_scenarios.get('invalidation') else 'n/a'}"
    )
    typer.echo(f"- tp_zones: {trade_scenarios.get('tp_zones')}")

    typer.echo("Decision")
    typer.echo(f"- {rec_status}")
    typer.echo("Reason")
    typer.echo(f"- {rec_reason}")


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


@app.command("precheck-report-json")
def precheck_report_json(limit: int | None = typer.Option(None, "--limit", min=1)) -> None:
    """Validate that analysis_reports.report_json values are valid JSON before jsonb migration."""
    with SessionLocal() as db:
        query = select(
            sa.text("id"),
            sa.text("symbol"),
            sa.text("report_json"),
        ).select_from(sa.text("analysis_reports")).order_by(sa.text("id DESC"))
        if limit is not None:
            query = query.limit(limit)

        invalid: list[tuple[int, str, str]] = []
        total = 0
        for row in db.execute(query):
            total += 1
            payload = row.report_json
            try:
                json.loads(payload)
            except Exception as exc:  # noqa: BLE001
                invalid.append((row.id, row.symbol, str(exc)))

        if invalid:
            typer.echo(f"FAIL invalid_json_rows={len(invalid)} checked_rows={total}")
            for row_id, symbol, error in invalid[:20]:
                typer.echo(f"- id={row_id} symbol={symbol} error={error}")
            raise typer.Exit(code=1)

    typer.echo(f"OK valid_json_rows={total}")


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
