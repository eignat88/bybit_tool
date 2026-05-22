"""align db objects for levels/symbols/scan_results"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260522_0004"
down_revision = "20260521_0003"
branch_labels = None
depends_on = None


def _index_exists(inspector: sa.Inspector, table: str, name: str) -> bool:
    return any(idx.get("name") == name for idx in inspector.get_indexes(table))


def _unique_exists(inspector: sa.Inspector, table: str, name: str) -> bool:
    return any(uq.get("name") == name for uq in inspector.get_unique_constraints(table))


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if not _index_exists(inspector, "levels", "ix_levels_market_type"):
        op.create_index("ix_levels_market_type", "levels", ["market_type"])

    if not _index_exists(inspector, "levels", "ix_levels_symbol_market_type_interval"):
        op.create_index("ix_levels_symbol_market_type_interval", "levels", ["symbol", "market_type", "interval"])

    if not _index_exists(inspector, "scan_results", "ix_scan_results_run_id_grid_score"):
        op.create_index("ix_scan_results_run_id_grid_score", "scan_results", ["run_id", "grid_score"])

    duplicate_cleanup_sql = sa.text(
        """
        DELETE FROM symbols
        WHERE id IN (
            SELECT s1.id
            FROM symbols s1
            JOIN symbols s2
              ON s1.symbol = s2.symbol
             AND s1.market_type = s2.market_type
             AND s1.id > s2.id
        )
        """
    )
    bind.execute(duplicate_cleanup_sql)

    for uq in inspector.get_unique_constraints("symbols"):
        cols = tuple(uq.get("column_names") or [])
        name = uq.get("name")
        if cols == ("symbol", "market_type") and name and name != "uq_symbol_market_type":
            with op.batch_alter_table("symbols") as batch_op:
                batch_op.drop_constraint(name, type_="unique")

    inspector = sa.inspect(bind)
    if not _unique_exists(inspector, "symbols", "uq_symbol_market_type"):
        with op.batch_alter_table("symbols") as batch_op:
            batch_op.create_unique_constraint("uq_symbol_market_type", ["symbol", "market_type"])


def downgrade() -> None:
    # Keep data-safe unique constraint and indexes in place on downgrade.
    pass
