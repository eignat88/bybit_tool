from __future__ import annotations

from types import SimpleNamespace

from typer.testing import CliRunner

from app.cli.commands import app


class _FakeExec:
    def __init__(self, *, scalar=None, scalars=None):
        self._scalar = scalar
        self._scalars = scalars or []

    def scalar_one_or_none(self):
        return self._scalar

    def scalars(self):
        return self

    def all(self):
        return self._scalars


class _FakeSession:
    def __init__(self, *, report_rows=None, scan=None, candle=None, levels=None):
        self.report_rows = report_rows or []
        self.scan = scan
        self.candle = candle
        self.levels = levels or []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, stmt):
        text = str(stmt)
        if "FROM analysis_reports" in text:
            return _FakeExec(scalars=self.report_rows)
        if "FROM scan_results" in text:
            return _FakeExec(scalar=self.scan)
        if "FROM candles" in text:
            return _FakeExec(scalar=self.candle)
        if "FROM levels" in text:
            return _FakeExec(scalars=self.levels)
        return _FakeExec()


def _mk_report(trend: str = "uptrend", risk: str = "low"):
    return SimpleNamespace(
        report_json={
            "market_type": "linear",
            "timeframes": ["60", "240"],
            "market_structure": {"60": {"trend_regime": trend}},
            "risk_summary": {"overall_risk": risk},
        }
    )


def test_context_has_required_sections(monkeypatch):
    fake_session = _FakeSession(
        report_rows=[_mk_report()],
        scan=SimpleNamespace(price=101.0, atr_pct=1.2, adx=21.0, rsi=48.0, tier="A"),
        levels=[
            SimpleNamespace(level_price=97.0, level_type="support"),
            SimpleNamespace(level_price=106.0, level_type="resistance"),
        ],
    )
    monkeypatch.setattr("app.cli.commands.SessionLocal", lambda: fake_session)
    monkeypatch.setattr("app.cli.commands.normalize_intervals", lambda value: (["240", "60"], "240,60"))
    monkeypatch.setattr(
        "app.cli.commands.find_nearest_levels",
        lambda **_kwargs: {
            "primary_interval": "60",
            "nearest_support": {"level_price": 97.0, "distance_pct": -3.96},
            "nearest_resistance": {"level_price": 106.0, "distance_pct": 4.95},
        },
    )
    monkeypatch.setattr(
        "app.cli.commands.build_trade_scenarios",
        lambda **_kwargs: {"status": "ok", "buy_zone": "95-98", "tp_zones": [105], "long_breakout": None, "invalidation": None},
    )
    monkeypatch.setattr(
        "app.cli.commands.RecommendationBuilder.build",
        lambda *_args, **_kwargs: SimpleNamespace(status="ok", reason="ok"),
    )

    result = CliRunner().invoke(app, ["context", "BTCUSDT", "--intervals", "60,240"])
    assert result.exit_code == 0
    for section in ["Symbol/Price", "Trend", "Nearest levels", "Risk", "Scenarios", "Decision", "Reason"]:
        assert section in result.stdout


def test_context_fallbacks_with_incomplete_data(monkeypatch):
    fake_session = _FakeSession(report_rows=[], scan=None, candle=None, levels=[])
    monkeypatch.setattr("app.cli.commands.SessionLocal", lambda: fake_session)
    monkeypatch.setattr("app.cli.commands.normalize_intervals", lambda value: (["240", "60"], "240,60"))
    monkeypatch.setattr(
        "app.cli.commands.find_nearest_levels",
        lambda **_kwargs: {"primary_interval": "60", "nearest_support": None, "nearest_resistance": None},
    )
    monkeypatch.setattr(
        "app.cli.commands.build_trade_scenarios",
        lambda **_kwargs: {"status": "insufficient_data", "buy_zone": None, "tp_zones": []},
    )

    result = CliRunner().invoke(app, ["context", "BTCUSDT", "--intervals", "60,240"])
    assert result.exit_code == 0
    assert "price=n/a status=insufficient_data reason=no_price_available" in result.stdout
    assert "status=insufficient_data reason=no_levels_found_for_primary_interval" in result.stdout
    assert "- overall: insufficient_data" in result.stdout
    assert "- insufficient_data" in result.stdout
    assert "- analysis_report_missing" in result.stdout


def test_context_default_intervals_are_split_before_normalize(monkeypatch):
    fake_session = _FakeSession(report_rows=[], scan=None, candle=None, levels=[])
    monkeypatch.setattr("app.cli.commands.SessionLocal", lambda: fake_session)

    captured = {}

    def _fake_normalize(value):
        captured["value"] = value
        return (["D", "240", "60"], "D,240,60")

    monkeypatch.setattr("app.cli.commands.normalize_intervals", _fake_normalize)
    monkeypatch.setattr(
        "app.cli.commands.find_nearest_levels",
        lambda **_kwargs: {"primary_interval": "60", "nearest_support": None, "nearest_resistance": None},
    )
    monkeypatch.setattr(
        "app.cli.commands.build_trade_scenarios",
        lambda **_kwargs: {"status": "insufficient_data", "buy_zone": None, "tp_zones": []},
    )

    result = CliRunner().invoke(app, ["context", "BTCUSDT", "--market-type", "linear"])
    assert result.exit_code == 0
    assert captured["value"] == ["D", "240", "60"]


def test_context_cli_intervals_csv_are_split_before_normalize(monkeypatch):
    fake_session = _FakeSession(report_rows=[], scan=None, candle=None, levels=[])
    monkeypatch.setattr("app.cli.commands.SessionLocal", lambda: fake_session)

    captured = {}

    def _fake_normalize(value):
        captured["value"] = value
        return (["240", "60"], "240,60")

    monkeypatch.setattr("app.cli.commands.normalize_intervals", _fake_normalize)
    monkeypatch.setattr(
        "app.cli.commands.find_nearest_levels",
        lambda **_kwargs: {"primary_interval": "60", "nearest_support": None, "nearest_resistance": None},
    )
    monkeypatch.setattr(
        "app.cli.commands.build_trade_scenarios",
        lambda **_kwargs: {"status": "insufficient_data", "buy_zone": None, "tp_zones": []},
    )

    result = CliRunner().invoke(app, ["context", "BTCUSDT", "--intervals", "240,60", "--market-type", "linear"])
    assert result.exit_code == 0
    assert captured["value"] == ["240", "60"]
