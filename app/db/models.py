from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Symbol(Base):
    __tablename__ = "symbols"

    id: Mapped[int] = mapped_column(primary_key=True)
    symbol: Mapped[str] = mapped_column(String(30), unique=True, index=True)
    market_type: Mapped[str] = mapped_column(String(10), default="perp", index=True)


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
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)


class ScanRun(Base):
    __tablename__ = "scan_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    strategy: Mapped[str] = mapped_column(String(32), index=True)
    scoring_version: Mapped[str] = mapped_column(String(16), default="v1")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)


class ScanResult(Base):
    __tablename__ = "scan_results"

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

    id: Mapped[int] = mapped_column(primary_key=True)
    symbol: Mapped[str] = mapped_column(String(30), index=True)
    interval: Mapped[str] = mapped_column(String(10), index=True)
    level_price: Mapped[float] = mapped_column(Float)
    level_type: Mapped[str] = mapped_column(String(30), index=True)
    source_type: Mapped[str] = mapped_column(String(30), index=True)
    description: Mapped[str] = mapped_column(String(250), default="")
    strength_score: Mapped[float] = mapped_column(Float, default=0.0)


class AnalysisReport(Base):
    __tablename__ = "analysis_reports"

    id: Mapped[int] = mapped_column(primary_key=True)
    symbol: Mapped[str] = mapped_column(String(30), index=True)
    timeframe_set: Mapped[str] = mapped_column(String(64))
    report_json: Mapped[str] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
