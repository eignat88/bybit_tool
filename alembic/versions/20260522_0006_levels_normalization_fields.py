"""add levels normalization fields

Revision ID: 20260522_0006
Revises: 20260522_0005
Create Date: 2026-05-22 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "20260522_0006"
down_revision = "20260522_0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("levels", sa.Column("cluster_id", sa.String(length=64), nullable=True))
    op.add_column("levels", sa.Column("normalized_price", sa.Float(), nullable=True))
    op.add_column("levels", sa.Column("cluster_strength", sa.Float(), nullable=False, server_default="0"))
    op.add_column("levels", sa.Column("merged_from_count", sa.Integer(), nullable=False, server_default="1"))
    op.add_column("levels", sa.Column("is_cluster_primary", sa.Boolean(), nullable=False, server_default=sa.true()))

    op.create_index("ix_levels_cluster_id", "levels", ["cluster_id"], unique=False)

    op.execute("UPDATE levels SET normalized_price = level_price WHERE normalized_price IS NULL")
    op.execute("UPDATE levels SET cluster_strength = strength_score WHERE cluster_strength = 0")

    op.alter_column("levels", "cluster_strength", server_default=None)
    op.alter_column("levels", "merged_from_count", server_default=None)
    op.alter_column("levels", "is_cluster_primary", server_default=None)


def downgrade() -> None:
    op.drop_index("ix_levels_cluster_id", table_name="levels")
    op.drop_column("levels", "is_cluster_primary")
    op.drop_column("levels", "merged_from_count")
    op.drop_column("levels", "cluster_strength")
    op.drop_column("levels", "normalized_price")
    op.drop_column("levels", "cluster_id")
