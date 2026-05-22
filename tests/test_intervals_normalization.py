from app.core.intervals import normalize_intervals


def test_normalize_intervals_equivalent_input_formats() -> None:
    normalized_list, timeframe_set_list = normalize_intervals(["D", "240", "60"])
    normalized_csv, timeframe_set_csv = normalize_intervals(["D,240,60"])

    assert normalized_list == ["D", "240", "60"]
    assert normalized_csv == normalized_list
    assert timeframe_set_list == timeframe_set_csv == "D,240,60"
