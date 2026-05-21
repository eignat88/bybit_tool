# Bybit Market Decision System (MVP bootstrap)

Initial scaffold for unified Bybit analytics platform with PostgreSQL as data core.

## Implemented now
- Unified CLI entrypoint (`main.py`) with commands:
  - `init-db`
  - `load`
  - `scan`
  - `levels`
  - `analyze`
- SQLAlchemy data model for MVP entities:
  - `symbols`, `candles`, `scan_runs`, `scan_results`, `levels`, `analysis_reports`
- Stub core services:
  - `BybitClient`, `MarketLoader`, `ValueScanner`, `LevelsCalculator`, `scoring`

## Migrations
- `init-db` now runs Alembic migrations (`alembic upgrade head`).
- Migration files are stored in `alembic/versions`.

## Quick start
```bash
python main.py init-db
python main.py scan --strategy grid --top 30
python main.py levels --symbol BTCUSDT --interval 120
```
