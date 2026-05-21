"""initial schema with indicator/recommendation/api log tables"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260521_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "symbols",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("symbol", sa.String(length=30), nullable=False),
        sa.Column("market_type", sa.String(length=10), nullable=False),
        sa.Column("base_coin", sa.String(length=20), nullable=False),
        sa.Column("quote_coin", sa.String(length=20), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("tick_size", sa.Float(), nullable=False),
        sa.Column("qty_step", sa.Float(), nullable=False),
        sa.Column("min_order_qty", sa.Float(), nullable=False),
        sa.Column("launch_time", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_symbols_symbol", "symbols", ["symbol"], unique=True)
    op.create_index("ix_symbols_market_type", "symbols", ["market_type"])

    op.create_table(
        "candles",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("symbol", sa.String(length=30), nullable=False),
        sa.Column("market_type", sa.String(length=10), nullable=False),
        sa.Column("interval", sa.String(length=10), nullable=False),
        sa.Column("open_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("open", sa.Float(), nullable=False),
        sa.Column("high", sa.Float(), nullable=False),
        sa.Column("low", sa.Float(), nullable=False),
        sa.Column("close", sa.Float(), nullable=False),
        sa.Column("volume", sa.Float(), nullable=False),
        sa.Column("turnover", sa.Float(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("symbol", "market_type", "interval", "open_time", name="uq_candle_key"),
    )
    op.create_index("ix_candles_symbol", "candles", ["symbol"])
    op.create_index("ix_candles_market_type", "candles", ["market_type"])
    op.create_index("ix_candles_interval", "candles", ["interval"])
    op.create_index("ix_candles_open_time", "candles", ["open_time"])

    op.create_table("scan_runs", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("strategy", sa.String(length=32), nullable=False), sa.Column("scoring_version", sa.String(length=16), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False))
    op.create_index("ix_scan_runs_strategy", "scan_runs", ["strategy"])

    op.create_table(
        "scan_results",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("run_id", sa.Integer(), sa.ForeignKey("scan_runs.id"), nullable=False),
        sa.Column("symbol", sa.String(length=30), nullable=False),
        sa.Column("price", sa.Float(), nullable=False),
        sa.Column("atr_pct", sa.Float(), nullable=False),
        sa.Column("rsi", sa.Float(), nullable=False),
        sa.Column("adx", sa.Float(), nullable=False),
        sa.Column("vwap_deviation_pct", sa.Float(), nullable=False),
        sa.Column("bb_width_pct", sa.Float(), nullable=False),
        sa.Column("grid_score", sa.Float(), nullable=False),
        sa.Column("tier", sa.String(length=2), nullable=False),
    )
    op.create_index("ix_scan_results_run_id", "scan_results", ["run_id"])
    op.create_index("ix_scan_results_symbol", "scan_results", ["symbol"])
    op.create_index("ix_scan_results_grid_score", "scan_results", ["grid_score"])
    op.create_index("ix_scan_results_tier", "scan_results", ["tier"])
    op.create_index("ix_scan_results_run_id_grid_score", "scan_results", ["run_id", "grid_score"])

    op.create_table("levels", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("symbol", sa.String(length=30), nullable=False), sa.Column("interval", sa.String(length=10), nullable=False), sa.Column("level_price", sa.Float(), nullable=False), sa.Column("level_type", sa.String(length=30), nullable=False), sa.Column("source_type", sa.String(length=30), nullable=False), sa.Column("description", sa.String(length=250), nullable=False), sa.Column("strength_score", sa.Float(), nullable=False))
    op.create_index("ix_levels_symbol", "levels", ["symbol"])
    op.create_index("ix_levels_interval", "levels", ["interval"])
    op.create_index("ix_levels_level_type", "levels", ["level_type"])
    op.create_index("ix_levels_source_type", "levels", ["source_type"])

    op.create_table("analysis_reports", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("symbol", sa.String(length=30), nullable=False), sa.Column("timeframe_set", sa.String(length=64), nullable=False), sa.Column("report_json", sa.String(), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False))
    op.create_index("ix_analysis_reports_symbol", "analysis_reports", ["symbol"])

    op.create_table(
        "indicator_values",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("symbol", sa.String(length=30), nullable=False),
        sa.Column("interval", sa.String(length=10), nullable=False),
        sa.Column("open_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("indicator_name", sa.String(length=64), nullable=False),
        sa.Column("value", sa.Float(), nullable=False),
        sa.Column("calc_version", sa.String(length=24), nullable=False),
        sa.UniqueConstraint("symbol", "interval", "open_time", "indicator_name", "calc_version", name="uq_indicator_values_key"),
    )
    op.create_index("ix_indicator_values_symbol", "indicator_values", ["symbol"])
    op.create_index("ix_indicator_values_interval", "indicator_values", ["interval"])
    op.create_index("ix_indicator_values_open_time", "indicator_values", ["open_time"])
    op.create_index("ix_indicator_values_indicator_name", "indicator_values", ["indicator_name"])
    op.create_index("ix_indicator_values_calc_version", "indicator_values", ["calc_version"])
    op.create_index("ix_indicator_values_symbol_interval_open_time", "indicator_values", ["symbol", "interval", "open_time"])

    op.create_table(
        "bot_recommendations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("symbol", sa.String(length=30), nullable=False),
        sa.Column("strategy_type", sa.String(length=32), nullable=False),
        sa.Column("params_json", sa.Text(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source_report_id", sa.Integer(), sa.ForeignKey("analysis_reports.id"), nullable=True),
    )
    op.create_index("ix_bot_recommendations_symbol", "bot_recommendations", ["symbol"])
    op.create_index("ix_bot_recommendations_strategy_type", "bot_recommendations", ["strategy_type"])
    op.create_index("ix_bot_recommendations_confidence", "bot_recommendations", ["confidence"])
    op.create_index("ix_bot_recommendations_created_at", "bot_recommendations", ["created_at"])
    op.create_index("ix_bot_recommendations_source_report_id", "bot_recommendations", ["source_report_id"])

    op.create_table(
        "api_request_log",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("endpoint", sa.String(length=255), nullable=False),
        sa.Column("params_json", sa.Text(), nullable=False),
        sa.Column("status_code", sa.Integer(), nullable=True),
        sa.Column("ret_code", sa.Integer(), nullable=True),
        sa.Column("latency_ms", sa.Float(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("error_text", sa.Text(), nullable=False),
    )
    op.create_index("ix_api_request_log_endpoint", "api_request_log", ["endpoint"])
    op.create_index("ix_api_request_log_status_code", "api_request_log", ["status_code"])
    op.create_index("ix_api_request_log_ret_code", "api_request_log", ["ret_code"])
    op.create_index("ix_api_request_log_latency_ms", "api_request_log", ["latency_ms"])
    op.create_index("ix_api_request_log_created_at", "api_request_log", ["created_at"])


def downgrade() -> None:
    for table in [
        "api_request_log",
        "bot_recommendations",
        "indicator_values",
        "analysis_reports",
        "levels",
        "scan_results",
        "scan_runs",
        "candles",
        "symbols",
    ]:
        op.drop_table(table)
