from app.core.report_builder import collect_market_metrics


def test_collect_market_metrics_uses_indicator_values_when_scan_field_missing():
    metrics = collect_market_metrics(
        nearest_levels={"primary_interval": "60", "latest_close": 101.5},
        scanner_summary={"status": "ok", "price": 102.0, "rsi": 48.2},
        indicator_snapshot={
            "60": {
                "status": "ok",
                "source": "indicator_values",
                "adx": 22.7,
                "atr_pct": 1.8,
            }
        },
    )

    assert metrics["price"] == 102.0
    assert metrics["adx"] == 22.7
    assert metrics["rsi"] == 48.2
    assert metrics["data_sources"]["price"] == "scan_result"
    assert metrics["data_sources"]["adx"] == "indicator_values"
    assert metrics["data_sources"]["rsi"] == "scan_result"


def test_collect_market_metrics_uses_candle_close_for_price_fallback():
    metrics = collect_market_metrics(
        nearest_levels={"primary_interval": "60", "latest_close": 99.1},
        scanner_summary={"status": "ok", "adx": 19.0},
        indicator_snapshot={"60": {"status": "ok", "source": "indicator_values", "rsi": 44.0}},
    )

    assert metrics["price"] == 99.1
    assert metrics["rsi"] == 44.0
    assert metrics["adx"] == 19.0
    assert metrics["data_sources"]["price"] == "candles.close"
