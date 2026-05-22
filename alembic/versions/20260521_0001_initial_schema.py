"""initial schema with indicator/recommendation/api log tables"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260521_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    def table_exists(name: str) -> bool:
        return inspector.has_table(name)

    def index_exists(table: str, name: str) -> bool:
        return any(idx.get("name") == name for idx in inspector.get_indexes(table))

    if not table_exists("symbols"):
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
    if not index_exists("symbols", "ix_symbols_symbol"):
        op.create_index("ix_symbols_symbol", "symbols", ["symbol"], unique=True)
    if not index_exists("symbols", "ix_symbols_market_type"):
        op.create_index("ix_symbols_market_type", "symbols", ["market_type"])

    if not table_exists("candles"):
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
    if not index_exists("candles", "ix_candles_symbol"):
        op.create_index("ix_candles_symbol", "candles", ["symbol"])
    if not index_exists("candles", "ix_candles_market_type"):
        op.create_index("ix_candles_market_type", "candles", ["market_type"])
    if not index_exists("candles", "ix_candles_interval"):
        op.create_index("ix_candles_interval", "candles", ["interval"])
    if not index_exists("candles", "ix_candles_open_time"):
        op.create_index("ix_candles_open_time", "candles", ["open_time"])

    if not table_exists("scan_runs"):
        op.create_table("scan_runs", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("strategy", sa.String(length=32), nullable=False), sa.Column("scoring_version", sa.String(length=16), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False))
    if not index_exists("scan_runs", "ix_scan_runs_strategy"):
        op.create_index("ix_scan_runs_strategy", "scan_runs", ["strategy"])

    if not table_exists("scan_results"):
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
    if not index_exists("scan_results", "ix_scan_results_run_id"):
        op.create_index("ix_scan_results_run_id", "scan_results", ["run_id"])
    if not index_exists("scan_results", "ix_scan_results_symbol"):
        op.create_index("ix_scan_results_symbol", "scan_results", ["symbol"])
    if not index_exists("scan_results", "ix_scan_results_grid_score"):
        op.create_index("ix_scan_results_grid_score", "scan_results", ["grid_score"])
    if not index_exists("scan_results", "ix_scan_results_tier"):
        op.create_index("ix_scan_results_tier", "scan_results", ["tier"])
    if not index_exists("scan_results", "ix_scan_results_run_id_grid_score"):
        op.create_index("ix_scan_results_run_id_grid_score", "scan_results", ["run_id", "grid_score"])

    if not table_exists("levels"):
        op.create_table("levels", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("symbol", sa.String(length=30), nullable=False), sa.Column("interval", sa.String(length=10), nullable=False), sa.Column("level_price", sa.Float(), nullable=False), sa.Column("level_type", sa.String(length=30), nullable=False), sa.Column("source_type", sa.String(length=30), nullable=False), sa.Column("description", sa.String(length=250), nullable=False), sa.Column("strength_score", sa.Float(), nullable=False))
    if not index_exists("levels", "ix_levels_symbol"):
        op.create_index("ix_levels_symbol", "levels", ["symbol"])
    if not index_exists("levels", "ix_levels_interval"):
        op.create_index("ix_levels_interval", "levels", ["interval"])
    if not index_exists("levels", "ix_levels_level_type"):
        op.create_index("ix_levels_level_type", "levels", ["level_type"])
    if not index_exists("levels", "ix_levels_source_type"):
        op.create_index("ix_levels_source_type", "levels", ["source_type"])

    if not table_exists("analysis_reports"):
        op.create_table("analysis_reports", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("symbol", sa.String(length=30), nullable=False), sa.Column("timeframe_set", sa.String(length=64), nullable=False), sa.Column("report_json", sa.String(), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False))
    if not index_exists("analysis_reports", "ix_analysis_reports_symbol"):
        op.create_index("ix_analysis_reports_symbol", "analysis_reports", ["symbol"])

    if not table_exists("indicator_values"):
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
    if not index_exists("indicator_values", "ix_indicator_values_symbol"):
        op.create_index("ix_indicator_values_symbol", "indicator_values", ["symbol"])
    if not index_exists("indicator_values", "ix_indicator_values_interval"):
        op.create_index("ix_indicator_values_interval", "indicator_values", ["interval"])
    if not index_exists("indicator_values", "ix_indicator_values_open_time"):
        op.create_index("ix_indicator_values_open_time", "indicator_values", ["open_time"])
    if not index_exists("indicator_values", "ix_indicator_values_indicator_name"):
        op.create_index("ix_indicator_values_indicator_name", "indicator_values", ["indicator_name"])
    if not index_exists("indicator_values", "ix_indicator_values_calc_version"):
        op.create_index("ix_indicator_values_calc_version", "indicator_values", ["calc_version"])
    if not index_exists("indicator_values", "ix_indicator_values_symbol_interval_open_time"):
        op.create_index("ix_indicator_values_symbol_interval_open_time", "indicator_values", ["symbol", "interval", "open_time"])

    if not table_exists("bot_recommendations"):
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
    if not index_exists("bot_recommendations", "ix_bot_recommendations_symbol"):
        op.create_index("ix_bot_recommendations_symbol", "bot_recommendations", ["symbol"])
    if not index_exists("bot_recommendations", "ix_bot_recommendations_strategy_type"):
        op.create_index("ix_bot_recommendations_strategy_type", "bot_recommendations", ["strategy_type"])
    if not index_exists("bot_recommendations", "ix_bot_recommendations_confidence"):
        op.create_index("ix_bot_recommendations_confidence", "bot_recommendations", ["confidence"])
    if not index_exists("bot_recommendations", "ix_bot_recommendations_created_at"):
        op.create_index("ix_bot_recommendations_created_at", "bot_recommendations", ["created_at"])
    if not index_exists("bot_recommendations", "ix_bot_recommendations_source_report_id"):
        op.create_index("ix_bot_recommendations_source_report_id", "bot_recommendations", ["source_report_id"])

    if not table_exists("api_request_log"):
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
    if not index_exists("api_request_log", "ix_api_request_log_endpoint"):
        op.create_index("ix_api_request_log_endpoint", "api_request_log", ["endpoint"])
    if not index_exists("api_request_log", "ix_api_request_log_status_code"):
        op.create_index("ix_api_request_log_status_code", "api_request_log", ["status_code"])
    if not index_exists("api_request_log", "ix_api_request_log_ret_code"):
        op.create_index("ix_api_request_log_ret_code", "api_request_log", ["ret_code"])
    if not index_exists("api_request_log", "ix_api_request_log_latency_ms"):
        op.create_index("ix_api_request_log_latency_ms", "api_request_log", ["latency_ms"])
    if not index_exists("api_request_log", "ix_api_request_log_created_at"):
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
