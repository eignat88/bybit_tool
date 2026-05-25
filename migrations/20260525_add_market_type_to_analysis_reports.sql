ALTER TABLE analysis_reports
ADD COLUMN IF NOT EXISTS market_type VARCHAR(32);

UPDATE analysis_reports
SET market_type = 'linear'
WHERE market_type IS NULL;

CREATE INDEX IF NOT EXISTS ix_analysis_reports_symbol_market_created
ON analysis_reports (
    symbol,
    market_type,
    created_at
);
