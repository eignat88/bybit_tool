"""add market_type to analysis_reports

Revision ID: 20260525_0003
Revises: 20260525_0002
Create Date: 2026-05-25
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "20260525_0003"
down_revision = "20260525_0002"
branch_labels = None
depends_on = None


def _has_column(inspector: sa.Inspector, table_name: str, column_name: str) -> bool:
    return any(c["name"] == column_name for c in inspector.get_columns(table_name))


def _has_index(inspector: sa.Inspector, table_name: str, index_name: str) -> bool:
    return any(idx.get("name") == index_name for idx in inspector.get_indexes(table_name))


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if not _has_column(inspector, "analysis_reports", "market_type"):
        op.add_column(
            "analysis_reports",
            sa.Column("market_type", sa.String(length=32), nullable=False, server_default="linear"),
        )

    inspector = sa.inspect(bind)
    if not _has_index(inspector, "analysis_reports", "ix_analysis_reports_market_type"):
        op.create_index("ix_analysis_reports_market_type", "analysis_reports", ["market_type"], unique=False)

    if _has_column(sa.inspect(bind), "analysis_reports", "market_type"):
        op.alter_column("analysis_reports", "market_type", server_default=None)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if _has_index(inspector, "analysis_reports", "ix_analysis_reports_market_type"):
        op.drop_index("ix_analysis_reports_market_type", table_name="analysis_reports")

    if _has_column(inspector, "analysis_reports", "market_type"):
        op.drop_column("analysis_reports", "market_type")
