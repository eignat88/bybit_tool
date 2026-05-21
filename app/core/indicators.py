from __future__ import annotations

from dataclasses import dataclass
from math import sqrt


@dataclass
class IndicatorSet:
    atr_pct: float
    rsi: float
    adx: float
    vwap_deviation_pct: float
    bb_width_pct: float


def _sma(values: list[float]) -> float:
    return sum(values) / len(values)


def _std(values: list[float]) -> float:
    mean = _sma(values)
    variance = sum((v - mean) ** 2 for v in values) / len(values)
    return sqrt(variance)


def calculate_indicators(
    highs: list[float],
    lows: list[float],
    closes: list[float],
    volumes: list[float],
    *,
    atr_period: int = 14,
    rsi_period: int = 14,
    adx_period: int = 14,
    bb_period: int = 20,
) -> IndicatorSet:
    if not closes:
        raise ValueError("No candles provided")

    atr = _atr(highs, lows, closes, period=atr_period)
    rsi = _rsi(closes, period=rsi_period)
    adx = _adx(highs, lows, closes, period=adx_period)
    vwap_deviation_pct = _vwap_deviation_pct(closes, volumes)
    bb_width_pct = _bb_width_pct(closes, period=bb_period)
    close = closes[-1]
    atr_pct = (atr / close * 100.0) if close else 0.0
    return IndicatorSet(
        atr_pct=atr_pct,
        rsi=rsi,
        adx=adx,
        vwap_deviation_pct=vwap_deviation_pct,
        bb_width_pct=bb_width_pct,
    )


def _atr(highs: list[float], lows: list[float], closes: list[float], *, period: int) -> float:
    trs: list[float] = []
    for i in range(1, len(closes)):
        tr = max(highs[i] - lows[i], abs(highs[i] - closes[i - 1]), abs(lows[i] - closes[i - 1]))
        trs.append(tr)
    if len(trs) < period:
        raise ValueError("Insufficient candles for ATR")
    return _sma(trs[-period:])


def _rsi(closes: list[float], *, period: int) -> float:
    if len(closes) < period + 1:
        raise ValueError("Insufficient candles for RSI")
    changes = [closes[i] - closes[i - 1] for i in range(1, len(closes))]
    gains = [max(c, 0.0) for c in changes]
    losses = [abs(min(c, 0.0)) for c in changes]
    avg_gain = _sma(gains[-period:])
    avg_loss = _sma(losses[-period:])
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100.0 - (100.0 / (1.0 + rs))


def _adx(highs: list[float], lows: list[float], closes: list[float], *, period: int) -> float:
    if len(closes) < period + 1:
        raise ValueError("Insufficient candles for ADX")
    trs: list[float] = []
    plus_dm: list[float] = []
    minus_dm: list[float] = []
    for i in range(1, len(closes)):
        up_move = highs[i] - highs[i - 1]
        down_move = lows[i - 1] - lows[i]
        plus_dm.append(up_move if up_move > down_move and up_move > 0 else 0.0)
        minus_dm.append(down_move if down_move > up_move and down_move > 0 else 0.0)
        tr = max(highs[i] - lows[i], abs(highs[i] - closes[i - 1]), abs(lows[i] - closes[i - 1]))
        trs.append(tr)
    atr = _sma(trs[-period:])
    if atr == 0:
        return 0.0
    plus_di = (_sma(plus_dm[-period:]) / atr) * 100.0
    minus_di = (_sma(minus_dm[-period:]) / atr) * 100.0
    denom = plus_di + minus_di
    if denom == 0:
        return 0.0
    return (abs(plus_di - minus_di) / denom) * 100.0


def _vwap_deviation_pct(closes: list[float], volumes: list[float]) -> float:
    total_vol = sum(volumes)
    if total_vol <= 0:
        return 0.0
    vwap = sum(c * v for c, v in zip(closes, volumes, strict=True)) / total_vol
    last = closes[-1]
    if vwap == 0:
        return 0.0
    return ((last - vwap) / vwap) * 100.0


def _bb_width_pct(closes: list[float], *, period: int, std_mult: float = 2.0) -> float:
    if len(closes) < period:
        raise ValueError("Insufficient candles for Bollinger Bands")
    window = closes[-period:]
    ma = _sma(window)
    if ma == 0:
        return 0.0
    stdev = _std(window)
    upper = ma + (std_mult * stdev)
    lower = ma - (std_mult * stdev)
    return ((upper - lower) / ma) * 100.0
