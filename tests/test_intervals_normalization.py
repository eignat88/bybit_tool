from app.core.intervals import normalize_intervals
from app.cli.commands import _prepare_intervals


def test_normalize_intervals_equivalent_input_formats() -> None:
    normalized_list, timeframe_set_list = normalize_intervals(["D", "240", "60"])
    normalized_csv, timeframe_set_csv = normalize_intervals(["D,240,60"])

    assert normalized_list == ["D", "240", "60"]
    assert normalized_csv == normalized_list
    assert timeframe_set_list == timeframe_set_csv == "D,240,60"


def test_prepare_intervals_single_value_string() -> None:
    assert _prepare_intervals("60") == ["60"]


def test_prepare_intervals_csv_string() -> None:
    assert _prepare_intervals("240,60") == ["240", "60"]


def test_prepare_intervals_mixed_csv_string() -> None:
    assert _prepare_intervals("D,240,60") == ["D", "240", "60"]
