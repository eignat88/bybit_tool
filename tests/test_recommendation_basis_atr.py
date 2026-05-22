from app.core.report_builder import build_recommendation_basis
from app.core.scoring import MAX_ATR_PCT, MIN_ATR_PCT


def _payload(atr_pct: float):
    return build_recommendation_basis(
        risk_summary={"data_quality": "ok", "overall_risk": "low", "trend_strength": "weak", "scanner_risk": "low"},
        nearest_levels={
            "latest_close": 100.0,
            "nearest_support": {"level_price": 95.0},
            "nearest_resistance": {"level_price": 105.0},
            "primary_interval": "60",
            "atr_pct": atr_pct,
        },
        levels_summary={"60": {"has_bos": False}},
    )


def test_atr_on_min_boundary_is_eligible():
    result = _payload(MIN_ATR_PCT)
    assert result["eligible_for_recommendation"] is True


def test_atr_on_max_boundary_is_eligible():
    result = _payload(MAX_ATR_PCT)
    assert result["eligible_for_recommendation"] is True


def test_atr_below_min_is_blocked_with_reason():
    result = _payload(MIN_ATR_PCT - 0.01)
    assert result["eligible_for_recommendation"] is False
    assert any("below" in x and "atr_pct" in x for x in result["blocking_factors"])


def test_atr_above_max_is_blocked_with_reason():
    result = _payload(MAX_ATR_PCT + 0.01)
    assert result["eligible_for_recommendation"] is False
    assert any("above" in x and "atr_pct" in x for x in result["blocking_factors"])
