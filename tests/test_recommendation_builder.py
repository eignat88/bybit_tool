from __future__ import annotations

import json
from datetime import datetime, timezone

import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.core.recommendation_builder import build_recommendation


def _mk_db(tmp_path):
    db_path = tmp_path / 'rec.sqlite3'
    engine = sa.create_engine(f"sqlite:///{db_path}", future=True)
    with engine.begin() as conn:
        conn.execute(sa.text("""CREATE TABLE analysis_reports (id INTEGER PRIMARY KEY, symbol VARCHAR(30), timeframe_set VARCHAR(64), report_json TEXT, created_at DATETIME)"""))
        conn.execute(sa.text("""CREATE TABLE scan_results (id INTEGER PRIMARY KEY, run_id INTEGER, symbol VARCHAR(30), price FLOAT, atr_pct FLOAT, rsi FLOAT, adx FLOAT, vwap_deviation_pct FLOAT, bb_width_pct FLOAT, grid_score FLOAT, tier VARCHAR(2))"""))
        conn.execute(sa.text("""CREATE TABLE levels (id INTEGER PRIMARY KEY, symbol VARCHAR(30), market_type VARCHAR(10), interval VARCHAR(10), level_price FLOAT, level_type VARCHAR(30), source_type VARCHAR(30), description VARCHAR(250), strength_score FLOAT, cluster_id VARCHAR(64), normalized_price FLOAT, cluster_strength FLOAT, merged_from_count INTEGER, is_cluster_primary BOOLEAN, event_open_time DATETIME, event_age_candles FLOAT)"""))
        conn.execute(sa.text("""CREATE TABLE indicator_values (id INTEGER PRIMARY KEY, symbol VARCHAR(30), interval VARCHAR(10), open_time DATETIME, indicator_name VARCHAR(64), value FLOAT, calc_version VARCHAR(24))"""))
        conn.execute(sa.text("""CREATE TABLE candles (id INTEGER PRIMARY KEY, symbol VARCHAR(30), market_type VARCHAR(10), interval VARCHAR(10), open_time DATETIME, open FLOAT, high FLOAT, low FLOAT, close FLOAT, volume FLOAT, turnover FLOAT, created_at DATETIME)"""))
        conn.execute(sa.text("""CREATE TABLE bot_recommendations (id INTEGER PRIMARY KEY, symbol VARCHAR(30), strategy_type VARCHAR(32), params_json TEXT, confidence FLOAT, created_at DATETIME, source_report_id INTEGER, market_type VARCHAR(10))"""))
    return engine


def test_build_recommendation_skip_without_levels(tmp_path):
    engine = _mk_db(tmp_path)
    with Session(engine) as db:
        db.execute(sa.text("INSERT INTO scan_results (symbol, price, rsi, adx, grid_score, tier) VALUES ('BTCUSDT', 100, 50, 10, 60, 'A')"))
        db.commit()
        rec = build_recommendation(db, 'BTCUSDT', 'linear', ['60'])
    assert rec.strategy_type == 'skip'
    assert 0.0 <= rec.confidence <= 1.0


def test_build_recommendation_grid_and_params(tmp_path):
    engine = _mk_db(tmp_path)
    with Session(engine) as db:
        db.execute(sa.text("INSERT INTO scan_results (id, symbol, price, rsi, adx, grid_score, tier) VALUES (1, 'BTCUSDT', 100, 50, 10, 60, 'A')"))
        db.execute(sa.text("INSERT INTO levels (symbol, market_type, interval, level_price, level_type, source_type, description, strength_score) VALUES ('BTCUSDT','linear','60',95,'support','x','',0.8)"))
        db.execute(sa.text("INSERT INTO levels (symbol, market_type, interval, level_price, level_type, source_type, description, strength_score) VALUES ('BTCUSDT','linear','60',105,'resistance','x','',0.8)"))
        db.execute(sa.text("INSERT INTO indicator_values (symbol, interval, open_time, indicator_name, value, calc_version) VALUES ('BTCUSDT','60',:ot,'adx',10,'v1')"),{"ot":datetime.now(timezone.utc)})
        db.commit()
        rec = build_recommendation(db, 'BTCUSDT', 'linear', ['60'])
        payload = json.loads(rec.params_json)
    assert rec.strategy_type == 'grid'
    for key in ['symbol','market_type','strategy_type','timeframes','current_price','source','scanner','levels','recommendation','reasons','warnings']:
        assert key in payload
