# Bybit Market Decision System (MVP bootstrap)

Initial scaffold for unified Bybit analytics platform with PostgreSQL as data core.

## Implemented now
- Unified CLI entrypoint (`main.py`) with commands:
  - `init-db` — инициализация схемы БД через миграции Alembic.
  - `load` — загрузка исторических свечей по выбранным символам/таймфреймам в БД.
  - `sync-symbols` — синхронизация справочника торговых инструментов с Bybit.
  - `db-stats` — агрегированная статистика по свечам в БД (объёмы, диапазон дат, последние значения).
  - `candles` — вывод последних N свечей по конкретному инструменту и интервалу.
  - `scheduler` — периодический запуск загрузки свечей по расписанию (15m/1h/4h/1d).
  - `scan` — ранжирование инструментов по стратегии (например, grid) для поиска торговых кандидатов.
  - `levels` — расчёт уровней поддержки/сопротивления с опциональным экспортом в CSV для TradingView.
  - `analyze` — построение сводного аналитического отчёта по инструменту и нескольким таймфреймам.
  - `db-check` — валидация целостности и консистентности данных/объектов в БД.
  - `self-test` — запуск встроенного smoke/self-test набора проверок проекта.
  - `seed-dev-data` — быстрая загрузка тестовых dev-данных (BTC/ETH, 15m/1h) для локальной разработки.
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
python main.py sync-symbols --market-type linear
python main.py load --symbols ALL --intervals 60
python main.py scan --strategy grid --top 30
python main.py levels --symbol BTCUSDT --interval 120
python main.py analyze --symbol BTCUSDT --intervals 60 240
```

`load --symbols ALL` берёт список инструментов из таблицы `symbols`, поэтому перед первой загрузкой обязательно выполните `sync-symbols` (иначе данные могут не загрузиться).
