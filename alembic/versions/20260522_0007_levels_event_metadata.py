"""add levels event metadata

Revision ID: 20260522_0007
Revises: 20260522_0006
Create Date: 2026-05-22 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "20260522_0007"
down_revision = "20260522_0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("levels", sa.Column("event_open_time", sa.DateTime(timezone=True), nullable=True))
    op.add_column("levels", sa.Column("event_age_candles", sa.Float(), nullable=True))
    op.create_index("ix_levels_event_open_time", "levels", ["event_open_time"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_levels_event_open_time", table_name="levels")
    op.drop_column("levels", "event_age_candles")
    op.drop_column("levels", "event_open_time")
