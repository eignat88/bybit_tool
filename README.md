# Bybit Market Decision System

CLI-инструмент для сбора рыночных данных Bybit, хранения их в PostgreSQL, расчёта индикаторов, уровней поддержки/сопротивления, построения аналитических отчётов и формирования торговых рекомендаций для ботов.

## Implemented now
- Unified CLI entrypoint (`main.py`) with commands:
  - `init-db` — инициализация схемы БД через миграции Alembic.
  - `migrate-db` — применение миграций Alembic до актуальной версии схемы.
  - `load` — загрузка исторических свечей по выбранным символам/таймфреймам в БД.
  - `load-all` — синхронизация всех доступных USDT-символов с Bybit и загрузка свечей по ним.
  - `sync-symbols` — синхронизация справочника торговых инструментов с Bybit.
  - `db-stats` — агрегированная статистика по свечам в БД (объёмы, диапазон дат, последние значения).
  - `candles` — вывод последних N свечей по конкретному инструменту и интервалу.
  - `scheduler` — периодический запуск загрузки свечей по расписанию (15m/1h/4h/1d).
  - `scan` — ранжирование инструментов по стратегии (например, grid) для поиска торговых кандидатов.
  - `indicators` — расчёт и сохранение технических индикаторов по символам и таймфреймам.
  - `levels` — расчёт уровней поддержки/сопротивления с опциональным экспортом в CSV для TradingView.
  - `analyze` — построение сводного аналитического отчёта по инструменту и нескольким таймфреймам.
  - `recommend` — построение и сохранение торговой рекомендации на основе `analysis_report`, `scan_results`, `levels`, `candles` и `indicator_values`.
  - `db-check` — валидация целостности и консистентности данных/объектов в БД.
  - `precheck-report-json` — проверка корректности JSON в `analysis_reports.report_json` перед миграцией/проверкой JSONB.
  - `self-test` — запуск встроенного smoke/self-test набора проверок проекта.
  - `seed-dev-data` — быстрая загрузка тестовых dev-данных (BTC/ETH, 15m/1h) для локальной разработки.

- SQLAlchemy data model:
  - `symbols` — справочник торговых инструментов Bybit.
  - `candles` — исторические OHLCV-свечи.
  - `scan_runs` — запуски сканера.
  - `scan_results` — результаты ранжирования инструментов по стратегии.
  - `levels` — рассчитанные уровни поддержки/сопротивления и структурные события.
  - `analysis_reports` — JSONB-отчёты по инструментам и наборам таймфреймов.
  - `indicator_values` — рассчитанные значения технических индикаторов.
  - `bot_recommendations` — сохранённые рекомендации для торговых ботов.
  - `api_request_log` — журнал запросов к API/внешним сервисам.

## Migrations
- `init-db` вызывает миграции Alembic через код (внутри запускается `alembic upgrade head`).
- `migrate-db` — отдельная CLI-команда для применения миграций до `head`.
- Миграции можно выполнить напрямую через Alembic CLI:
  ```bash
  alembic upgrade head
  ```
- Файлы ревизий лежат в `alembic/versions`.

## Quick start
```bash
python main.py init-db
python main.py sync-symbols --market-type linear
python main.py load --symbols BTCUSDT,ETHUSDT,SOLUSDT --intervals 15,60,240 --market-type linear
python main.py load-all --intervals 60,240 --market-type linear
python main.py indicators --symbols BTCUSDT,ETHUSDT,SOLUSDT --interval 60 --market-type linear
python main.py scan --strategy grid --top 30 --interval 60 --market-type linear --candles-limit 120
python main.py levels BTCUSDT --interval 60 --market-type linear
python main.py analyze BTCUSDT --intervals D,H4,H1 --market-type linear --recommend
```

## Indicators
```bash
python main.py indicators --symbols BTCUSDT --interval 60 --market-type linear --limit 300
```

Команда рассчитывает и сохраняет в `indicator_values` значения:
- `atr_pct`
- `rsi`
- `adx`
- `vwap_deviation_pct`
- `bb_width_pct`

Минимальное количество свечей для расчёта — `30`.
Если истории недостаточно, символ получает статус `skipped` с причиной `insufficient_history`.

Пример ожидаемого вывода:
```text
symbol=BTCUSDT interval=60 market_type=linear open_time=... indicators_saved=5 status=ok
  atr_pct=...
  rsi=...
  adx=...
  vwap_deviation_pct=...
  bb_width_pct=...

symbols_requested=...
symbols_processed=...
symbols_skipped=...
symbols_failed=...
indicators_saved_total=...
elapsed_time_sec=...
```

## Recommendations

### Вариант 1. Отдельная команда
```bash
python main.py recommend BTCUSDT --intervals D,H4,H1 --market-type linear
```

Строит торговую рекомендацию на основе последнего подходящего `analysis_report` и связанных рыночных данных.

Источники данных:
- `analysis_reports`
- `scan_results`
- `candles`
- `levels`
- `indicator_values`

Результат сохраняется в:
- `bot_recommendations`

Пример вывода:
```text
Recommendation saved: id=...
market_type=linear
source_report_id=...
symbol=BTCUSDT
strategy_type=grid
confidence=0.85
```

### Вариант 2. Через `analyze --recommend`
```bash
python main.py analyze BTCUSDT --intervals D,H4,H1 --market-type linear --recommend
```

Команда сначала строит `analysis_report`, затем сразу формирует и сохраняет `bot_recommendation` на его основе.

### Поддерживаемые `strategy_type`
- `grid` — используется для диапазонного рынка при достаточном `grid_score`, наличии поддержки/сопротивления и низком ADX.
- `range_trade` — используется при боковом рынке, низком ADX, RSI в нейтральной зоне и наличии диапазона.
- `trend_follow` — используется при выраженном тренде и подтверждении трендового режима в `analysis_report`.
- `skip` — используется, если данных недостаточно или условия для сделки не подтверждены.

`confidence` задаётся в диапазоне `0.0 .. 1.0`.

### Пример `bot_recommendations.params_json`
```json
{
  "symbol": "BTCUSDT",
  "market_type": "linear",
  "strategy_type": "grid",
  "timeframes": ["D", "H4", "H1"],
  "current_price": 81000.0,
  "source": {
    "analysis_report_id": 123,
    "scan_result_id": 456
  },
  "scanner": {
    "grid_score": 65.5,
    "tier": "A",
    "atr_pct": 2.1,
    "rsi": 52.0,
    "adx": 18.0,
    "vwap_deviation_pct": 0.5,
    "bb_width_pct": 3.2
  },
  "levels": {
    "nearest_support": 80000.0,
    "nearest_resistance": 82500.0,
    "support_count": 5,
    "resistance_count": 4,
    "strong_levels_count": 3
  },
  "recommendation": {
    "strategy_type": "grid",
    "confidence": 0.85,
    "direction": "trend_up",
    "lower_bound": 80000.0,
    "upper_bound": 82500.0,
    "range_width_pct": 3.08,
    "risk_level": "medium"
  },
  "reasons": [
    "grid_score >= 55",
    "ADX < 25",
    "support and resistance found"
  ],
  "warnings": []
}
```

## What can be queried now
- список торговых инструментов;
- исторические свечи OHLCV;
- последние цены и объёмы;
- статистику наполнения БД;
- технические индикаторы;
- кандидатов под стратегию grid;
- уровни поддержки/сопротивления;
- структурные события BOS/CHOCH;
- сводные `analysis_reports`;
- рекомендации для торговых ботов;
- причины и предупреждения по рекомендации.

## CLI cheatsheet
```bash
python main.py migrate-db
python main.py load --symbols BTCUSDT ETHUSDT --intervals 15 60 --market-type linear
python main.py candles BTCUSDT 60 --tail 10 --market-type linear
python main.py indicators --symbols BTCUSDT --interval 60 --market-type linear --limit 300
python main.py scan --strategy grid --top 30 --interval 60 --market-type linear --candles-limit 120
python main.py levels BTCUSDT --interval 60 --market-type linear
python main.py analyze BTCUSDT --intervals D,H4,H1 --market-type linear --recommend
python main.py recommend BTCUSDT --intervals D,H4,H1 --market-type linear
python main.py precheck-report-json --limit 100
python main.py db-check
python main.py db-stats
python main.py self-test --quick --no-artifacts
```
