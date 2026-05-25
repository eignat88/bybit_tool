from app.core.trade_scenarios import build_trade_scenarios


def test_trade_scenarios_builds_full_template():
    result = build_trade_scenarios(
        current_price=100.0,
        nearest_support=95.0,
        nearest_resistance=105.0,
        support_levels=[90.0, 95.0],
        resistance_levels=[105.0, 110.0, 115.0, 120.0],
        trend_context="trend_up",
        risk_context="medium",
        breakout_buffer_pct=0.1,
        buy_zone_width_pct=0.5,
        support_invalidation_buffer_pct=0.2,
        tp_levels_count=3,
    )

    assert result["status"] == "ok"
    assert result["long_breakout"]["trigger_price"] == 105.105
    assert result["buy_zone"]["low"] == 94.525
    assert result["invalidation"]["trigger_price"] == 94.81
    assert result["tp_zones"] == [105.0, 110.0, 115.0]


def test_trade_scenarios_degrades_softly_when_levels_missing():
    result = build_trade_scenarios(
        current_price=None,
        nearest_support=None,
        nearest_resistance=105.0,
        resistance_levels=[105.0],
        tp_levels_count=3,
    )

    assert result["status"] == "partial"
    assert "current_price_unavailable" in result["warnings"]
    assert "nearest_support_unavailable" in result["warnings"]
    assert "limited_tp_levels" in result["warnings"]
    assert result["buy_zone"] is None
    assert result["tp_zones"] == [105.0]
