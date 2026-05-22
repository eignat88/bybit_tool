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
