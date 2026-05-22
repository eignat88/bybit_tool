from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Symbol(Base):
    __tablename__ = "symbols"
    __table_args__ = (UniqueConstraint("symbol", "market_type", name="uq_symbol_market_type"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    symbol: Mapped[str] = mapped_column(String(30), index=True)
    market_type: Mapped[str] = mapped_column(String(10), default="linear", nullable=False, index=True)
    base_coin: Mapped[str] = mapped_column(String(20), default="")
    quote_coin: Mapped[str] = mapped_column(String(20), default="")
    status: Mapped[str] = mapped_column(String(20), default="")
    tick_size: Mapped[float] = mapped_column(Float, default=0.0)
    qty_step: Mapped[float] = mapped_column(Float, default=0.0)
    min_order_qty: Mapped[float] = mapped_column(Float, default=0.0)
    launch_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)


class Candle(Base):
    __tablename__ = "candles"
    __table_args__ = (
        UniqueConstraint("symbol", "market_type", "interval", "open_time", name="uq_candle_key"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    symbol: Mapped[str] = mapped_column(String(30), index=True)
    market_type: Mapped[str] = mapped_column(String(10), index=True)
    interval: Mapped[str] = mapped_column(String(10), index=True)
    open_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    open: Mapped[float] = mapped_column(Float)
    high: Mapped[float] = mapped_column(Float)
    low: Mapped[float] = mapped_column(Float)
    close: Mapped[float] = mapped_column(Float)
    volume: Mapped[float] = mapped_column(Float)
    turnover: Mapped[float] = mapped_column(Float)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)


class ScanRun(Base):
    __tablename__ = "scan_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    strategy: Mapped[str] = mapped_column(String(32), index=True)
    scoring_version: Mapped[str] = mapped_column(String(16), default="v1")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)


class ScanResult(Base):
    __tablename__ = "scan_results"
    __table_args__ = (Index("ix_scan_results_run_id_grid_score", "run_id", "grid_score"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("scan_runs.id"), index=True)
    symbol: Mapped[str] = mapped_column(String(30), index=True)
    price: Mapped[float] = mapped_column(Float)
    atr_pct: Mapped[float] = mapped_column(Float)
    rsi: Mapped[float] = mapped_column(Float)
    adx: Mapped[float] = mapped_column(Float)
    vwap_deviation_pct: Mapped[float] = mapped_column(Float)
    bb_width_pct: Mapped[float] = mapped_column(Float)
    grid_score: Mapped[float] = mapped_column(Float, index=True)
    tier: Mapped[str] = mapped_column(String(2), index=True)


class Level(Base):
    __tablename__ = "levels"
    __table_args__ = (Index("ix_levels_symbol_market_type_interval", "symbol", "market_type", "interval"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    symbol: Mapped[str] = mapped_column(String(30), index=True)
    market_type: Mapped[str] = mapped_column(String(10), default="linear", nullable=False, index=True)
    interval: Mapped[str] = mapped_column(String(10), index=True)
    level_price: Mapped[float] = mapped_column(Float)
    level_type: Mapped[str] = mapped_column(String(30), index=True)
    source_type: Mapped[str] = mapped_column(String(30), index=True)
    description: Mapped[str] = mapped_column(String(250), default="")
    strength_score: Mapped[float] = mapped_column(Float, default=0.0)
    cluster_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    normalized_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    cluster_strength: Mapped[float] = mapped_column(Float, default=0.0)
    merged_from_count: Mapped[int] = mapped_column(Integer, default=1)
    is_cluster_primary: Mapped[bool] = mapped_column(Boolean, default=True)


class AnalysisReport(Base):
    __tablename__ = "analysis_reports"

    id: Mapped[int] = mapped_column(primary_key=True)
    symbol: Mapped[str] = mapped_column(String(30), index=True)
    timeframe_set: Mapped[str] = mapped_column(String(64))
    report_json: Mapped[str] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)


class IndicatorValue(Base):
    __tablename__ = "indicator_values"
    __table_args__ = (
        UniqueConstraint(
            "symbol",
            "interval",
            "open_time",
            "indicator_name",
            "calc_version",
            name="uq_indicator_values_key",
        ),
        Index("ix_indicator_values_symbol_interval_open_time", "symbol", "interval", "open_time"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    symbol: Mapped[str] = mapped_column(String(30), index=True)
    interval: Mapped[str] = mapped_column(String(10), index=True)
    open_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    indicator_name: Mapped[str] = mapped_column(String(64), index=True)
    value: Mapped[float] = mapped_column(Float)
    calc_version: Mapped[str] = mapped_column(String(24), default="v1", index=True)


class BotRecommendation(Base):
    __tablename__ = "bot_recommendations"

    id: Mapped[int] = mapped_column(primary_key=True)
    symbol: Mapped[str] = mapped_column(String(30), index=True)
    strategy_type: Mapped[str] = mapped_column(String(32), index=True)
    params_json: Mapped[str] = mapped_column(Text)
    confidence: Mapped[float] = mapped_column(Float, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, index=True)
    source_report_id: Mapped[int | None] = mapped_column(ForeignKey("analysis_reports.id"), nullable=True, index=True)


class ApiRequestLog(Base):
    __tablename__ = "api_request_log"

    id: Mapped[int] = mapped_column(primary_key=True)
    endpoint: Mapped[str] = mapped_column(String(255), index=True)
    params_json: Mapped[str] = mapped_column(Text)
    status_code: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    ret_code: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    latency_ms: Mapped[float] = mapped_column(Float, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, index=True)
    error_text: Mapped[str] = mapped_column(Text, default="")
