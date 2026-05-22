from datetime import datetime, timedelta, UTC
from types import SimpleNamespace

from app.core.levels_calculator import LevelResult, LevelsCalculator


def make_candle(idx: int, open_p: float, high: float, low: float, close: float, volume: float = 1000.0):
    return SimpleNamespace(
        open_time=datetime(2026, 1, 1, tzinfo=UTC) + timedelta(hours=idx),
        open=open_p,
        high=high,
        low=low,
        close=close,
        volume=volume,
    )


def test_cluster_merge_respects_source_priority():
    calc = LevelsCalculator()
    candles = [make_candle(i, 100 + i, 102 + i, 98 + i, 101 + i) for i in range(40)]
    raw = [
        LevelResult(100.0, "support", "fvg", "", 52),
        LevelResult(100.05, "support", "bos", "", 61),
    ]

    normalized = calc._normalize_levels(raw, candles, atr=1.0)

    assert len(normalized) == 1
    assert normalized[0].source_type == "bos"
    assert normalized[0].cluster_size == 2


def test_fvg_filters_reject_small_gap():
    calc = LevelsCalculator()
    assert calc._fvg_passes_filters(
        gap=calc.FVG_MIN_GAP_SIZE - 0.1,
        atr=100,
        displacement=100,
        avg_range=50,
        candle_volume=2000,
        avg_volume=1000,
    ) is False


def test_weighted_merge_prioritizes_bos_over_fvg_score():
    calc = LevelsCalculator()
    candles = [make_candle(i, 100 + i, 102 + i, 98 + i, 101 + i) for i in range(60)]
    raw = [
        LevelResult(110.0, "support", "fvg", "", 80),
        LevelResult(110.04, "support", "bos", "", 65),
    ]

    normalized = calc._normalize_levels(raw, candles, atr=1.0)

    assert len(normalized) == 1
    # BOS/FVG weighting should keep merged level stronger than BOS-only signal
    assert normalized[0].cluster_strength > 65.0


def test_diminishing_returns_and_distance_penalty_reduce_aggressive_scores():
    calc = LevelsCalculator()
    candles = [make_candle(i, 100 + i, 102 + i, 98 + i, 101 + i) for i in range(80)]

    compact_cluster = [
        LevelResult(200.0, "resistance", "bos", "", 68),
        LevelResult(200.03, "resistance", "choch", "", 72),
        LevelResult(200.05, "resistance", "fvg", "", 58),
    ]
    wide_cluster = [
        LevelResult(300.0, "resistance", "bos", "", 68),
        LevelResult(300.14, "resistance", "choch", "", 72),
        LevelResult(300.28, "resistance", "fvg", "", 58),
    ]

    compact = calc._normalize_levels(compact_cluster, candles, atr=1.0)[0]
    wide = calc._normalize_levels(wide_cluster, candles, atr=1.0)[0]

    assert compact.cluster_strength < 100.0
    assert wide.cluster_strength < compact.cluster_strength
