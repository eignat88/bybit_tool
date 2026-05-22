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
