from __future__ import annotations

import json
from types import SimpleNamespace

from typer.testing import CliRunner

from app.cli.commands import app


class _FakeExecuteResult:
    def __init__(self, *, first=None, scalar=None, scalars=None):
        self._first = first
        self._scalar = scalar
        self._scalars = scalars

    def first(self):
        return self._first

    def scalar_one_or_none(self):
        return self._scalar

    def scalars(self):
        return self

    def all(self):
        return self._scalars or []


class _FakeSession:
    def __init__(self, close_price: float | None):
        self.close_price = close_price

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, _stmt):
        if self.close_price is None:
            return _FakeExecuteResult(first=None)
        return _FakeExecuteResult(first=(self.close_price,))


def _level(level_price: float, level_type: str, strength: float = 1.0, source: str = "swing"):
    return SimpleNamespace(
        level_price=level_price,
        level_type=level_type,
        source_type=source,
        strength_score=strength,
    )


def test_levels_show_and_sorting(monkeypatch):
    monkeypatch.setattr("app.cli.commands.SessionLocal", lambda: _FakeSession(close_price=100.0))
    monkeypatch.setattr(
        "app.cli.commands.LevelsCalculator.calculate",
        lambda *_args, **_kwargs: [
            _level(90, "support"),
            _level(99, "support"),
            _level(108, "resistance"),
            _level(102, "resistance"),
        ],
    )

    runner = CliRunner()
    result = runner.invoke(app, ["levels", "BTCUSDT", "--show"]) 

    assert result.exit_code == 0
    # supports: nearest to price first from below
    assert result.stdout.index("price=99.000000") < result.stdout.index("price=90.000000")
    # resistances: nearest to price first from above
    assert result.stdout.index("price=102.000000") < result.stdout.index("price=108.000000")


def test_levels_nearest_output_with_missing_sides(monkeypatch):
    monkeypatch.setattr("app.cli.commands.SessionLocal", lambda: _FakeSession(close_price=100.0))
    monkeypatch.setattr(
        "app.cli.commands.LevelsCalculator.calculate",
        lambda *_args, **_kwargs: [_level(98, "support")],
    )

    runner = CliRunner()
    result = runner.invoke(app, ["levels", "BTCUSDT", "--nearest"])

    assert result.exit_code == 0
    assert "nearest_support=98.000000" in result.stdout
    assert "nearest_resistance=n/a" in result.stdout


def test_levels_json_payload_and_distance_sign(monkeypatch):
    monkeypatch.setattr("app.cli.commands.SessionLocal", lambda: _FakeSession(close_price=100.0))
    monkeypatch.setattr(
        "app.cli.commands.LevelsCalculator.calculate",
        lambda *_args, **_kwargs: [
            _level(95, "support"),
            _level(105, "resistance"),
        ],
    )

    runner = CliRunner()
    result = runner.invoke(app, ["levels", "BTCUSDT", "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout.split("\nBy source_type:")[0])
    assert set(payload.keys()) == {
        "symbol",
        "interval",
        "current_price",
        "nearest_support",
        "nearest_resistance",
    }
    assert payload["symbol"] == "BTCUSDT"
    assert payload["interval"] == "120"
    assert payload["current_price"] == 100.0
    assert payload["nearest_support"]["distance_pct"] < 0
    assert payload["nearest_resistance"]["distance_pct"] > 0


def test_levels_edge_cases_no_candles_no_levels(monkeypatch):
    monkeypatch.setattr("app.cli.commands.SessionLocal", lambda: _FakeSession(close_price=None))
    monkeypatch.setattr("app.cli.commands.LevelsCalculator.calculate", lambda *_args, **_kwargs: [])

    runner = CliRunner()
    result = runner.invoke(app, ["levels", "BTCUSDT", "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["current_price"] == 0.0
    assert payload["nearest_support"] is None
    assert payload["nearest_resistance"] is None
