"""add market_type to bot_recommendations (nullable MVP)"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260522_0009"
down_revision = "20260522_0008"
branch_labels = None
depends_on = None


def _has_column(inspector: sa.Inspector, table_name: str, column_name: str) -> bool:
    return any(c["name"] == column_name for c in inspector.get_columns(table_name))


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not _has_column(inspector, "bot_recommendations", "market_type"):
        op.add_column("bot_recommendations", sa.Column("market_type", sa.String(length=10), nullable=True))

    indexes = {idx.get("name") for idx in inspector.get_indexes("bot_recommendations") if idx.get("name")}
    if "ix_bot_recommendations_market_type" not in indexes:
        op.create_index("ix_bot_recommendations_market_type", "bot_recommendations", ["market_type"])


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if _has_column(inspector, "bot_recommendations", "market_type"):
        op.drop_index("ix_bot_recommendations_market_type", table_name="bot_recommendations")
        op.drop_column("bot_recommendations", "market_type")
