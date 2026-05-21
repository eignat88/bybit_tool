"""replace symbols unique key with (symbol, market_type)"""

from __future__ import annotations

from alembic import op


revision = "20260521_0002"
down_revision = "20260521_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_index("ix_symbols_symbol", table_name="symbols")
    op.create_index("ix_symbols_symbol", "symbols", ["symbol"], unique=False)
    op.create_unique_constraint("uq_symbol_market_type", "symbols", ["symbol", "market_type"])


def downgrade() -> None:
    op.drop_constraint("uq_symbol_market_type", "symbols", type_="unique")
    op.drop_index("ix_symbols_symbol", table_name="symbols")
    op.create_index("ix_symbols_symbol", "symbols", ["symbol"], unique=True)
