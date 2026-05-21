from __future__ import annotations

INTERVAL_TO_MS: dict[str, int] = {
    "1": 60_000,
    "3": 180_000,
    "5": 300_000,
    "15": 900_000,
    "30": 1_800_000,
    "60": 3_600_000,
    "120": 7_200_000,
    "240": 14_400_000,
    "360": 21_600_000,
    "720": 43_200_000,
    "D": 86_400_000,
    "W": 604_800_000,
}


def validate_intervals_csv(intervals: str) -> list[str]:
    interval_list = [item.strip().upper() for item in intervals.split(",") if item.strip()]
    if not interval_list:
        raise ValueError("intervals must not be empty")

    unsupported = [item for item in interval_list if item not in INTERVAL_TO_MS]
    if unsupported:
        raise ValueError(f"Unsupported intervals: {','.join(unsupported)}")
    return interval_list
