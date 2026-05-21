from app.core.indicators import IndicatorSet


SCORING_VERSION = "v1"


def calculate_grid_score(indicators: IndicatorSet) -> float:
    atr_component = _score_range(indicators.atr_pct, target=2.5, tolerance=2.0)
    rsi_component = _score_range(indicators.rsi, target=50.0, tolerance=20.0)
    adx_component = _score_inverted(indicators.adx, low=15.0, high=45.0)
    vwap_component = _score_inverted(abs(indicators.vwap_deviation_pct), low=0.5, high=5.0)
    bb_component = _score_range(indicators.bb_width_pct, target=6.0, tolerance=5.0)

    score = (
        atr_component * 0.25
        + rsi_component * 0.2
        + adx_component * 0.25
        + vwap_component * 0.15
        + bb_component * 0.15
    )
    return round(max(0.0, min(100.0, score)), 2)


def _score_range(value: float, *, target: float, tolerance: float) -> float:
    distance = abs(value - target)
    if distance >= tolerance:
        return 0.0
    return 100.0 * (1.0 - distance / tolerance)


def _score_inverted(value: float, *, low: float, high: float) -> float:
    if value <= low:
        return 100.0
    if value >= high:
        return 0.0
    span = high - low
    return 100.0 * (1.0 - ((value - low) / span))


def tier_from_score(score: float) -> str:
    if score >= 80:
        return "A"
    if score >= 65:
        return "B"
    if score >= 50:
        return "C"
    return "D"
