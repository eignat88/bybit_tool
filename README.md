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
- Ограничения схемы по ключам инструментов и свечей:
  - `symbols`: уникальность пары `(symbol, market_type)` (constraint `uq_symbol_market_type`), что позволяет хранить один и тот же тикер в разных типах рынка.
  - `candles`: уникальность `(symbol, market_type, interval, open_time)` (constraint `uq_candle_key`).
- Stub core services:
  - `BybitClient`, `MarketLoader`, `ValueScanner`, `LevelsCalculator`, `scoring`

## Migrations
- `init-db` вызывает миграции Alembic через код (внутри запускается `alembic upgrade head`).
- Миграции можно выполнить напрямую через Alembic CLI:
  ```bash
  alembic upgrade head
  ```
- Файлы ревизий лежат в `alembic/versions`.
- Когда что использовать:
  - `init-db` — для стандартного сценария запуска проекта через единый CLI.
  - `alembic upgrade head` — для прямого управления миграциями (например, в CI, отладке или ручном администрировании БД).

## Local setup verification
Before running database-dependent commands (for example `init-db`, `sync-symbols`, `load`), verify packaging in a clean virtual environment so metadata/configuration errors fail fast.

```bash
python -m venv .venv-packaging-check
source .venv-packaging-check/bin/activate
python -m pip install --upgrade pip
pip install -e .
```

If `pip install -e .` succeeds, the project packaging metadata is valid and you can continue with DB setup.

## Quick start
```bash
# 1) Fail fast on packaging issues in a clean environment
python -m venv .venv-packaging-check
source .venv-packaging-check/bin/activate
python -m pip install --upgrade pip
pip install -e .
deactivate

# 2) Then run database-dependent bootstrap commands
python main.py init-db
python main.py sync-symbols --market-type linear
python main.py load --symbols ALL --intervals 60
python main.py scan --strategy grid --top 30
python main.py levels --symbol BTCUSDT --interval 120
python main.py analyze --symbol BTCUSDT --intervals 60 240
```

`load --symbols ALL` берёт список инструментов из таблицы `symbols`, поэтому перед первой загрузкой обязательно выполните `sync-symbols` (иначе данные могут не загрузиться).

## Запуск CLI
CLI можно запускать двумя способами:

```bash
python main.py <command>
```

```bash
bybit-tool <command>
```

Команда `bybit-tool` появляется после установки пакета и берётся из секции `pyproject.toml`:

```toml
[project.scripts]
bybit-tool = "main:app"
```

## CLI cheatsheet
```bash
python main.py load --symbols BTCUSDT ETHUSDT --intervals 15 60 --market-type linear
```
Загружает исторические свечи для выбранных символов и таймфреймов в таблицу `candles`.

```bash
python main.py scan --interval 60 --candles-limit 500 --market-type linear
```
Запускает сканер инструментов на указанном таймфрейме и выводит ранжированный список кандидатов.

```bash
python main.py levels --symbol BTCUSDT --interval 60 --export-csv ./artifacts/btc_levels.csv
```
Считает уровни поддержки/сопротивления и сохраняет CSV-файл для дальнейшего импорта (например, в TradingView).

```bash
python main.py analyze --symbol BTCUSDT --intervals 15 60 240 --market-type linear
```
Строит сводный аналитический отчёт по инструменту сразу на нескольких таймфреймах.

```bash
python main.py scheduler --once --market-type linear
```
Выполняет один проход планировщика (без фонового цикла) и завершает работу после загрузки данных.

```bash
python main.py self-test --quick --no-artifacts
```
Запускает быстрый набор самопроверок без сохранения диагностических артефактов на диск.

```bash
python main.py db-check
```
Проверяет целостность и консистентность данных/связей в базе.

```bash
python main.py db-stats
```
Показывает агрегированную статистику по свечам: объёмы, диапазон дат и последние значения.

```bash
python main.py candles --symbol BTCUSDT --interval 60 --limit 10
```
Выводит последние N свечей по инструменту и таймфрейму для быстрой ручной проверки.
