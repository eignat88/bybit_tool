from datetime import UTC, datetime, timedelta

from app.core.indicators import calculate_bollinger_bands
from app.core.spot_scan_export import export_spot_scan_csv, export_spot_scan_xlsx
from app.core.spot_screener import SpotScanRow, calculate_volume_24h, resolve_signal


def test_bollinger_and_percent_b() -> None:
    closes = [float(i) for i in range(1, 31)]
    bb = calculate_bollinger_bands(closes, period=20, mult=2.0)
    assert bb.upper > bb.mid > bb.lower
    assert bb.percent_b is not None


def test_volume_24h_for_2h() -> None:
    now = datetime.now(UTC)
    open_times = [now + timedelta(hours=2 * i) for i in range(20)]
    volumes = [1.0] * 20
    v24, used = calculate_volume_24h(volumes, open_times)
    assert used == 12
    assert v24 == 12.0


def test_signal_resolution() -> None:
    assert resolve_signal(True, False, False, False) == ("long", 4)
    assert resolve_signal(False, True, False, False) == ("short", 3)


def test_sorting_and_export(tmp_path) -> None:
    rows = [
        SpotScanRow("A", "2h", 1, 1, 20, 60, 1, 2, 0, 0.5, 1, False, False, True, False, "trend_up", 2, 200, 12),
        SpotScanRow("B", "2h", 1, 1, 30, 20, 1, 2, 0, 0.1, 1, True, False, False, False, "long", 4, 200, 12),
    ]
    rows.sort(key=lambda r: (-r.signal_rank, r.rsi, -r.volume_24h))
    assert rows[0].symbol == "B"

    csv_path = export_spot_scan_csv(rows, tmp_path / "out.csv")
    assert csv_path.exists()
    try:
        xlsx_path = export_spot_scan_xlsx(rows, tmp_path / "out.xlsx")
        assert xlsx_path.exists()
    except ModuleNotFoundError:
        pass
