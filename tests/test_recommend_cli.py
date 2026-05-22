from __future__ import annotations

from typer.testing import CliRunner

from app.cli.commands import app


class _FakeResult:
    def scalar_one_or_none(self):
        return None


class _FakeSession:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, *_args, **_kwargs):
        return _FakeResult()

    def add(self, *_args, **_kwargs):  # pragma: no cover
        raise AssertionError("add should not be called when analysis report is absent")

    def commit(self):  # pragma: no cover
        raise AssertionError("commit should not be called when analysis report is absent")


def test_recommend_without_analysis_report_exits_gracefully(monkeypatch):
    monkeypatch.setattr("app.cli.commands.SessionLocal", lambda: _FakeSession())

    runner = CliRunner()
    result = runner.invoke(app, ["recommend", "BTCUSDT"])

    assert result.exit_code == 0
    assert "No analysis report found." in result.stdout
    assert "python main.py analyze BTCUSDT --market-type linear --recommend" in result.stdout
    assert "Traceback" not in result.stdout


def test_recommend_backward_compatible_without_market_type_column(monkeypatch, tmp_path):
    import json
    from datetime import datetime, timezone

    import sqlalchemy as sa
    from sqlalchemy.orm import sessionmaker

    from app.core.recommendation_builder import RecommendationResult

    db_path = tmp_path / "compat.sqlite3"
    engine = sa.create_engine(f"sqlite:///{db_path}", future=True)

    with engine.begin() as conn:
        conn.execute(sa.text("""
            CREATE TABLE analysis_reports (
                id INTEGER PRIMARY KEY,
                symbol VARCHAR(30) NOT NULL,
                timeframe_set VARCHAR(64) NOT NULL,
                report_json TEXT NOT NULL,
                created_at DATETIME NOT NULL
            )
        """))
        conn.execute(sa.text("""
            CREATE TABLE bot_recommendations (
                id INTEGER PRIMARY KEY,
                symbol VARCHAR(30) NOT NULL,
                strategy_type VARCHAR(32) NOT NULL,
                params_json TEXT NOT NULL,
                confidence FLOAT NOT NULL,
                created_at DATETIME,
                source_report_id INTEGER
            )
        """))
        conn.execute(
            sa.text("INSERT INTO analysis_reports (id, symbol, timeframe_set, report_json, created_at) VALUES (1, :symbol, :timeframe_set, :report_json, :created_at)"),
            {"symbol": "BTCUSDT", "timeframe_set": "15", "report_json": json.dumps({"ok": True}), "created_at": datetime.now(timezone.utc)},
        )

    Session = sessionmaker(bind=engine, future=True)
    monkeypatch.setattr("app.cli.commands.SessionLocal", Session)
    monkeypatch.setattr(
        "app.cli.commands.RecommendationBuilder.build",
        lambda *_args, **_kwargs: RecommendationResult(status="ok", strategy_type="grid", params={"x": 1}, confidence=0.73),
    )

    runner = CliRunner()
    result = runner.invoke(app, ["recommend", "BTCUSDT", "--market-type", "linear"])

    assert result.exit_code == 0
    assert "recommendation_id=" in result.stdout

    with engine.connect() as conn:
        rows = conn.execute(sa.text("SELECT symbol, strategy_type, confidence FROM bot_recommendations")).fetchall()
    assert len(rows) == 1
    assert rows[0][0] == "BTCUSDT"
    assert rows[0][1] == "grid"
