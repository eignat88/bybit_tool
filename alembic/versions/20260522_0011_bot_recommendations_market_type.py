"""add market_type to bot_recommendations

Revision ID: 20260522_0011
Revises: 20260522_0010
Create Date: 2026-05-22
"""

from alembic import op
import sqlalchemy as sa


revision = "20260522_0011"
down_revision = "20260522_0010"
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
            sa.Column(
                "market_type",
                sa.String(length=20),
                nullable=False,
                server_default="linear",
            ),
        )

    inspector = sa.inspect(bind)
    if not _has_index(inspector, "bot_recommendations", "ix_bot_recommendations_market_type"):
        op.create_index(
            "ix_bot_recommendations_market_type",
            "bot_recommendations",
            ["market_type"],
            unique=False,
        )

    if not _has_index(inspector, "bot_recommendations", "ix_bot_recommendations_symbol_market_type"):
        op.create_index(
            "ix_bot_recommendations_symbol_market_type",
            "bot_recommendations",
            ["symbol", "market_type"],
            unique=False,
        )

    if _has_column(sa.inspect(bind), "bot_recommendations", "market_type"):
        op.alter_column(
            "bot_recommendations",
            "market_type",
            server_default=None,
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if _has_index(inspector, "bot_recommendations", "ix_bot_recommendations_symbol_market_type"):
        op.drop_index(
            "ix_bot_recommendations_symbol_market_type",
            table_name="bot_recommendations",
        )

    if _has_index(inspector, "bot_recommendations", "ix_bot_recommendations_market_type"):
        op.drop_index(
            "ix_bot_recommendations_market_type",
            table_name="bot_recommendations",
        )

    if _has_column(inspector, "bot_recommendations", "market_type"):
        op.drop_column("bot_recommendations", "market_type")
