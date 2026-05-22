"""replace symbols unique key with (symbol, market_type)"""

from __future__ import annotations

from alembic import op


revision = "20260521_0002"
down_revision = "20260521_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("symbols") as batch_op:
        batch_op.drop_index("ix_symbols_symbol")
        batch_op.create_index("ix_symbols_symbol", ["symbol"], unique=False)
        batch_op.create_unique_constraint("uq_symbol_market_type", ["symbol", "market_type"])


def downgrade() -> None:
    with op.batch_alter_table("symbols") as batch_op:
        batch_op.drop_constraint("uq_symbol_market_type", type_="unique")
        batch_op.drop_index("ix_symbols_symbol")
        batch_op.create_index("ix_symbols_symbol", ["symbol"], unique=True)
