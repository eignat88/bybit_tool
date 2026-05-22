"""postgres type/nullability alignment for audited core tables"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260522_0005"
down_revision = "20260522_0004"
branch_labels = None
depends_on = None


def _has_column(inspector: sa.Inspector, table: str, column: str) -> bool:
    return any(c.get("name") == column for c in inspector.get_columns(table))


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    inspector = sa.inspect(bind)

    if not _has_column(inspector, "levels", "market_type"):
        op.add_column("levels", sa.Column("market_type", sa.String(length=10), nullable=False, server_default="linear"))
        op.create_index("ix_levels_market_type", "levels", ["market_type"])
        op.create_index("ix_levels_symbol_market_type_interval", "levels", ["symbol", "market_type", "interval"])
        op.alter_column("levels", "market_type", server_default=None)

    op.execute(sa.text("UPDATE candles SET created_at = NOW() WHERE created_at IS NULL"))
    op.alter_column(
        "candles",
        "created_at",
        existing_type=sa.DateTime(timezone=True),
        nullable=False,
        postgresql_using="created_at AT TIME ZONE 'UTC'",
    )


def downgrade() -> None:
    # preserve stricter schema on downgrade
    pass
