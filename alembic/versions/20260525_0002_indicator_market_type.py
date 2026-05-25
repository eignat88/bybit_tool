"""add market_type to indicator values and widen uniqueness key"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "20260525_0002"
down_revision = "20260521_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    columns = {c["name"] for c in inspector.get_columns("indicator_values")}
    if "market_type" not in columns:
        op.add_column(
            "indicator_values",
            sa.Column("market_type", sa.String(length=20), nullable=False, server_default="linear"),
        )
        op.alter_column("indicator_values", "market_type", server_default=None)

    indexes = {idx.get("name") for idx in inspector.get_indexes("indicator_values")}
    if "ix_indicator_values_market_type" not in indexes:
        op.create_index("ix_indicator_values_market_type", "indicator_values", ["market_type"])

    unique_constraints = {uq.get("name"): tuple(uq.get("column_names") or []) for uq in inspector.get_unique_constraints("indicator_values")}
    if unique_constraints.get("uq_indicator_values_key") == (
        "symbol",
        "interval",
        "open_time",
        "indicator_name",
        "calc_version",
    ):
        op.drop_constraint("uq_indicator_values_key", "indicator_values", type_="unique")
        op.create_unique_constraint(
            "uq_indicator_values_key",
            "indicator_values",
            ["symbol", "market_type", "interval", "open_time", "indicator_name", "calc_version"],
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    unique_constraints = {uq.get("name"): tuple(uq.get("column_names") or []) for uq in inspector.get_unique_constraints("indicator_values")}
    if unique_constraints.get("uq_indicator_values_key") == (
        "symbol",
        "market_type",
        "interval",
        "open_time",
        "indicator_name",
        "calc_version",
    ):
        op.drop_constraint("uq_indicator_values_key", "indicator_values", type_="unique")
        op.create_unique_constraint(
            "uq_indicator_values_key",
            "indicator_values",
            ["symbol", "interval", "open_time", "indicator_name", "calc_version"],
        )

    indexes = {idx.get("name") for idx in inspector.get_indexes("indicator_values")}
    if "ix_indicator_values_market_type" in indexes:
        op.drop_index("ix_indicator_values_market_type", table_name="indicator_values")

    columns = {c["name"] for c in inspector.get_columns("indicator_values")}
    if "market_type" in columns:
        op.drop_column("indicator_values", "market_type")
