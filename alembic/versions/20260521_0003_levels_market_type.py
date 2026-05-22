"""add market_type to levels and scoped indexes"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260521_0003"
down_revision = "20260521_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("levels", sa.Column("market_type", sa.String(length=10), nullable=False, server_default="linear"))
    op.create_index("ix_levels_market_type", "levels", ["market_type"])
    op.create_index("ix_levels_symbol_market_type_interval", "levels", ["symbol", "market_type", "interval"])
    bind = op.get_bind()
    if bind.dialect.name != "sqlite":
        op.alter_column("levels", "market_type", server_default=None)


def downgrade() -> None:
    op.drop_index("ix_levels_symbol_market_type_interval", table_name="levels")
    op.drop_index("ix_levels_market_type", table_name="levels")
    op.drop_column("levels", "market_type")
