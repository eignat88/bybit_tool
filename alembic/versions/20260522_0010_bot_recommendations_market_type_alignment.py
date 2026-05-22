"""align bot_recommendations.market_type constraints and type"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260522_0010"
down_revision = "20260522_0009"
branch_labels = None
depends_on = None


def _has_column(inspector: sa.Inspector, table_name: str, column_name: str) -> bool:
    return any(c["name"] == column_name for c in inspector.get_columns(table_name))


def _has_index(inspector: sa.Inspector, table_name: str, index_name: str) -> bool:
    return any(idx.get("name") == index_name for idx in inspector.get_indexes(table_name))


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if not _has_column(inspector, "bot_recommendations", "market_type"):
        op.add_column(
            "bot_recommendations",
            sa.Column("market_type", sa.String(length=20), nullable=False, server_default="linear"),
        )
    else:
        op.alter_column(
            "bot_recommendations",
            "market_type",
            existing_type=sa.String(length=10),
            type_=sa.String(length=20),
            existing_nullable=True,
            nullable=False,
            server_default="linear",
        )

    op.execute("UPDATE bot_recommendations SET market_type = 'linear' WHERE market_type IS NULL")

    op.alter_column(
        "bot_recommendations",
        "market_type",
        existing_type=sa.String(length=20),
        existing_nullable=False,
        server_default=None,
    )

    inspector = sa.inspect(bind)
    if not _has_index(inspector, "bot_recommendations", "ix_bot_recommendations_market_type"):
        op.create_index("ix_bot_recommendations_market_type", "bot_recommendations", ["market_type"])


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if _has_index(inspector, "bot_recommendations", "ix_bot_recommendations_market_type"):
        op.drop_index("ix_bot_recommendations_market_type", table_name="bot_recommendations")

    if _has_column(inspector, "bot_recommendations", "market_type"):
        op.drop_column("bot_recommendations", "market_type")
