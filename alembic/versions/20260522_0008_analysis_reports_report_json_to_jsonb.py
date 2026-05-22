"""convert analysis_reports.report_json to jsonb safely

Revision ID: 20260522_0008
Revises: 20260522_0007
Create Date: 2026-05-22 00:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260522_0008"
down_revision = "20260522_0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    op.execute(
        sa.text(
            """
            CREATE OR REPLACE FUNCTION _tmp_is_valid_jsonb(payload text)
            RETURNS boolean
            LANGUAGE plpgsql
            AS $$
            BEGIN
                PERFORM payload::jsonb;
                RETURN true;
            EXCEPTION
                WHEN others THEN
                    RETURN false;
            END;
            $$;
            """
        )
    )

    try:
        op.execute(
            sa.text(
                """
                DO $$
                DECLARE
                    invalid_ids text;
                BEGIN
                    SELECT string_agg(id::text, ', ' ORDER BY id)
                    INTO invalid_ids
                    FROM analysis_reports
                    WHERE NOT _tmp_is_valid_jsonb(report_json);

                    IF invalid_ids IS NOT NULL THEN
                        RAISE EXCEPTION
                            'Migration aborted: analysis_reports.report_json contains invalid JSON for id(s): %',
                            invalid_ids;
                    END IF;
                END
                $$;
                """
            )
        )

        op.execute(
            sa.text(
                """
                ALTER TABLE analysis_reports
                ALTER COLUMN report_json TYPE jsonb USING report_json::jsonb;
                """
            )
        )

        op.execute(
            sa.text(
                """
                CREATE INDEX IF NOT EXISTS ix_analysis_reports_report_json_gin
                ON analysis_reports USING gin (report_json);
                """
            )
        )

        op.execute(
            sa.text(
                """
                CREATE INDEX IF NOT EXISTS ix_analysis_reports_json_market_type
                ON analysis_reports ((report_json ->> 'market_type'));
                """
            )
        )

        op.execute(
            sa.text(
                """
                CREATE INDEX IF NOT EXISTS ix_analysis_reports_json_overall_risk
                ON analysis_reports ((report_json -> 'risk_summary' ->> 'overall_risk'));
                """
            )
        )

        op.execute(
            sa.text(
                """
                CREATE INDEX IF NOT EXISTS ix_analysis_reports_json_candidate_strategy
                ON analysis_reports ((report_json -> 'recommendation_basis' ->> 'candidate_strategy'));
                """
            )
        )

        op.execute(
            sa.text(
                """
                CREATE INDEX IF NOT EXISTS ix_analysis_reports_json_eligible
                ON analysis_reports ((report_json -> 'recommendation_basis' ->> 'eligible_for_recommendation'));
                """
            )
        )
    finally:
        op.execute(sa.text("DROP FUNCTION IF EXISTS _tmp_is_valid_jsonb(text);"))


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    op.execute(
        sa.text(
            """
            DROP INDEX IF EXISTS ix_analysis_reports_json_eligible;
            DROP INDEX IF EXISTS ix_analysis_reports_json_candidate_strategy;
            DROP INDEX IF EXISTS ix_analysis_reports_json_overall_risk;
            DROP INDEX IF EXISTS ix_analysis_reports_json_market_type;
            DROP INDEX IF EXISTS ix_analysis_reports_report_json_gin;

            ALTER TABLE analysis_reports
            ALTER COLUMN report_json TYPE text USING report_json::text;
            """
        )
    )
