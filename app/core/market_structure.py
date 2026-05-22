from __future__ import annotations

from dataclasses import dataclass
from statistics import mean, pstdev

from app.core.intervals import INTERVAL_TO_MS, normalize_intervals

TF_ALIASES: dict[str, str] = {
    "M1": "1",
    "M3": "3",
    "M5": "5",
    "M15": "15",
    "M30": "30",
    "H1": "60",
    "H2": "120",
    "H4": "240",
    "H6": "360",
    "H12": "720",
    "D1": "D",
    "1D": "D",
    "W1": "W",
    "1W": "W",
}


@dataclass(slots=True)
class MarketStructureSnapshot:
    timeframe: str
    trend_regime: str
    swing_state: str
    volatility_state: str
    latest_close: float
    returns_volatility_pct: float



def parse_timeframes_csv(timeframes_csv: str) -> list[str]:
    raw = [item.strip().upper() for item in timeframes_csv.split(",") if item.strip()]
    if not raw:
        raise ValueError("intervals/timeframes must not be empty")

    mapped = [TF_ALIASES.get(tf, tf) for tf in raw]
    try:
        normalized, _ = normalize_intervals(mapped)
    except ValueError as exc:
        raise ValueError(str(exc).replace("Unsupported intervals", "Unsupported intervals/timeframes")) from exc
    return normalized



def build_market_structure(timeframe: str, candles: list[dict[str, float]]) -> MarketStructureSnapshot:
    if len(candles) < 30:
        raise ValueError(f"Not enough candles for {timeframe}: need >= 30, got {len(candles)}")

    closes = [float(c["close"]) for c in candles]
    highs = [float(c["high"]) for c in candles]
    lows = [float(c["low"]) for c in candles]

    last_close = closes[-1]
    fast_ma = mean(closes[-10:])
    slow_ma = mean(closes[-30:])

    if fast_ma > slow_ma * 1.002:
        trend_regime = "bullish"
    elif fast_ma < slow_ma * 0.998:
        trend_regime = "bearish"
    else:
        trend_regime = "sideways"

    prev_high, cur_high = max(highs[-20:-10]), max(highs[-10:])
    prev_low, cur_low = min(lows[-20:-10]), min(lows[-10:])
    if cur_high > prev_high and cur_low > prev_low:
        swing_state = "HH/HL"
    elif cur_high < prev_high and cur_low < prev_low:
        swing_state = "LL/LH"
    elif cur_high > prev_high and cur_low <= prev_low:
        swing_state = "HH/LH"
    else:
        swing_state = "LL/HL"

    returns = [(closes[idx] / closes[idx - 1] - 1.0) * 100 for idx in range(1, len(closes)) if closes[idx - 1] != 0]
    recent_vol = pstdev(returns[-20:]) if len(returns) >= 20 else pstdev(returns)
    baseline_vol = pstdev(returns)

    if recent_vol > baseline_vol * 1.25:
        volatility_state = "high"
    elif recent_vol < baseline_vol * 0.8:
        volatility_state = "low"
    else:
        volatility_state = "normal"

    return MarketStructureSnapshot(
        timeframe=timeframe,
        trend_regime=trend_regime,
        swing_state=swing_state,
        volatility_state=volatility_state,
        latest_close=last_close,
        returns_volatility_pct=round(recent_vol, 4),
    )
