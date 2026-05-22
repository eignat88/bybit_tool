from app.core.recommendation_builder import RecommendationBuilder


def _report(*, trend: str, events: list[dict], strongest_support: dict | None, strongest_resistance: dict | None):
    return {
        "market_structure": {"60": {"trend_regime": trend}},
        "nearest_levels": {"primary_interval": "60"},
        "levels_summary": {
            "60": {
                "recent_structure_events": events,
                "strongest_support": strongest_support,
                "strongest_resistance": strongest_resistance,
            }
        },
        "recommendation_basis": {
            "eligible_for_recommendation": True,
            "candidate_strategy": "trend_follow",
            "confidence_score": 0.77,
            "suggested_bot_params": {"reference_interval": "60"},
        },
    }


def test_valid_long_when_bullish_structure_and_strong_support():
    builder = RecommendationBuilder()
    payload = _report(
        trend="trend_up",
        events=[{"type": "BOS", "side": "bullish"}],
        strongest_support={"level_price": 95.0, "strength_score": 0.8},
        strongest_resistance={"level_price": 105.0, "strength_score": 0.3},
    )
    result = builder.build(payload)
    assert result.status == "ok"


def test_valid_short_when_bearish_structure_and_strong_resistance():
    builder = RecommendationBuilder()
    payload = _report(
        trend="trend_down",
        events=[{"type": "CHOCH", "side": "bearish"}],
        strongest_support={"level_price": 95.0, "strength_score": 0.3},
        strongest_resistance={"level_price": 105.0, "strength_score": 0.8},
    )
    result = builder.build(payload)
    assert result.status == "ok"


def test_conflict_between_trend_and_structure_returns_skip():
    builder = RecommendationBuilder()
    payload = _report(
        trend="trend_up",
        events=[{"type": "BOS", "side": "bearish"}],
        strongest_support={"level_price": 95.0, "strength_score": 0.8},
        strongest_resistance={"level_price": 105.0, "strength_score": 0.8},
    )
    result = builder.build(payload)
    assert result.status == "skip"
    assert result.reason == "direction_not_confirmed"
