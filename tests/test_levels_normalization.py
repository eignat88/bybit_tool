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
    # BOS/FVG weighting should stay between source strengths and lean toward BOS.
    assert 65.0 > normalized[0].cluster_strength > 60.0


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


def test_percentile_monotonicity():
    calc = LevelsCalculator()
    clusters = [
        LevelResult(100.0, "support", "bos", "a", 0, cluster_strength=10.0),
        LevelResult(101.0, "support", "bos", "b", 0, cluster_strength=20.0),
        LevelResult(102.0, "support", "bos", "c", 0, cluster_strength=30.0),
        LevelResult(103.0, "support", "bos", "d", 0, cluster_strength=40.0),
    ]

    scored = calc._apply_percentile_scoring(clusters)
    ordered = sorted(scored, key=lambda x: x.raw_cluster_strength)

    assert ordered[0].cluster_strength <= ordered[1].cluster_strength <= ordered[2].cluster_strength <= ordered[3].cluster_strength


def test_percentile_median_is_near_50():
    calc = LevelsCalculator()
    clusters = [
        LevelResult(200.0, "support", "bos", "a", 0, cluster_strength=10.0),
        LevelResult(201.0, "support", "bos", "b", 0, cluster_strength=20.0),
        LevelResult(202.0, "support", "bos", "c", 0, cluster_strength=30.0),
        LevelResult(203.0, "support", "bos", "d", 0, cluster_strength=40.0),
        LevelResult(204.0, "support", "bos", "e", 0, cluster_strength=50.0),
    ]

    scored = calc._apply_percentile_scoring(clusters)
    median_cluster = sorted(scored, key=lambda x: x.raw_cluster_strength)[2]
    assert 49.0 <= median_cluster.cluster_strength <= 51.0


def test_percentile_small_samples():
    calc = LevelsCalculator()

    one = calc._apply_percentile_scoring(
        [LevelResult(100.0, "support", "bos", "", 0, cluster_strength=42.0)]
    )
    assert one[0].percentile_rank == 100.0
    assert one[0].cluster_strength == 100.0

    two = calc._apply_percentile_scoring(
        [
            LevelResult(100.0, "support", "bos", "", 0, cluster_strength=10.0),
            LevelResult(101.0, "support", "bos", "", 0, cluster_strength=20.0),
        ]
    )
    two_sorted = sorted(two, key=lambda x: x.raw_cluster_strength)
    assert two_sorted[0].percentile_rank == 0.0
    assert two_sorted[1].percentile_rank == 100.0

    three = calc._apply_percentile_scoring(
        [
            LevelResult(100.0, "support", "bos", "", 0, cluster_strength=10.0),
            LevelResult(101.0, "support", "bos", "", 0, cluster_strength=20.0),
            LevelResult(102.0, "support", "bos", "", 0, cluster_strength=30.0),
        ]
    )
    three_sorted = sorted(three, key=lambda x: x.raw_cluster_strength)
    assert three_sorted[1].percentile_rank == 50.0


def test_weighted_cluster_score_for_bos_and_fvg_matches_expected_average():
    calc = LevelsCalculator()
    cluster = [
        LevelResult(100.0, "support", "bos", "", 80.0),
        LevelResult(100.03, "support", "fvg", "", 60.0),
    ]

    score = calc._weighted_cluster_score(cluster)
    expected = ((80.0 * 0.9) + (60.0 * 0.5)) / (0.9 + 0.5)
    assert score == expected


def test_choch_does_not_get_artificial_score_boost_from_multiplier():
    calc = LevelsCalculator()
    candles = [make_candle(i, 100 + i, 102 + i, 98 + i, 101 + i) for i in range(60)]
    raw = [
        LevelResult(110.0, "resistance", "choch", "", 70.0),
        LevelResult(110.03, "resistance", "fvg", "", 60.0),
    ]

    normalized = calc._normalize_levels(raw, candles, atr=1.0)

    assert len(normalized) == 1
    baseline_weighted = ((70.0 * 1.0) + (60.0 * 0.5)) / (1.0 + 0.5)
    assert normalized[0].cluster_strength < 100.0
    assert normalized[0].cluster_strength < baseline_weighted * 2
