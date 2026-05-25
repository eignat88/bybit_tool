from __future__ import annotations

from typing import Any

from app.config.settings import settings


def _round(value: float | None) -> float | None:
    if value is None:
        return None
    return round(float(value), 6)


def build_trade_scenarios(
    *,
    current_price: float | None,
    nearest_support: float | None,
    nearest_resistance: float | None,
    support_levels: list[float] | None = None,
    resistance_levels: list[float] | None = None,
    trend_context: str | None = None,
    risk_context: str | None = None,
    breakout_buffer_pct: float | None = None,
    buy_zone_width_pct: float | None = None,
    support_invalidation_buffer_pct: float | None = None,
    tp_levels_count: int | None = None,
) -> dict[str, Any]:
    breakout_buffer = (
        float(breakout_buffer_pct)
        if breakout_buffer_pct is not None
        else float(settings.trade_scenarios_breakout_buffer_pct)
    )
    buy_zone_width = (
        float(buy_zone_width_pct) if buy_zone_width_pct is not None else float(settings.trade_scenarios_buy_zone_width_pct)
    )
    support_invalidation_buffer = (
        float(support_invalidation_buffer_pct)
        if support_invalidation_buffer_pct is not None
        else float(settings.trade_scenarios_support_invalidation_buffer_pct)
    )
    tp_count = int(tp_levels_count) if tp_levels_count is not None else int(settings.trade_scenarios_tp_levels_count)
    tp_count = max(1, tp_count)

    supports = sorted({float(x) for x in (support_levels or [])})
    resistances = sorted({float(x) for x in (resistance_levels or [])})

    next_supports = [lv for lv in supports if nearest_support is None or lv < nearest_support]
    next_resistances = [lv for lv in resistances if nearest_resistance is None or lv > nearest_resistance]

    breakout_trigger = None
    retest_zone = None
    if nearest_resistance is not None:
        breakout_trigger = nearest_resistance * (1.0 + breakout_buffer / 100.0)
        retest_zone = {
            "low": nearest_resistance * (1.0 - buy_zone_width / 100.0),
            "high": nearest_resistance * (1.0 + buy_zone_width / 100.0),
        }

    buy_zone = None
    invalidation = None
    if nearest_support is not None:
        buy_zone = {
            "low": nearest_support * (1.0 - buy_zone_width / 100.0),
            "high": nearest_support * (1.0 + buy_zone_width / 100.0),
        }
        invalidation = nearest_support * (1.0 - support_invalidation_buffer / 100.0)

    entry_reference = current_price
    candidate_tps = [lv for lv in [nearest_resistance, *next_resistances] if lv is not None]
    if entry_reference is not None:
        candidate_tps = [lv for lv in candidate_tps if lv > entry_reference]
    tp_zones = [_round(level) for level in candidate_tps[:tp_count]]

    warnings: list[str] = []
    if current_price is None:
        warnings.append("current_price_unavailable")
    if nearest_support is None:
        warnings.append("nearest_support_unavailable")
    if nearest_resistance is None:
        warnings.append("nearest_resistance_unavailable")
    if len(tp_zones) < tp_count:
        warnings.append("limited_tp_levels")

    return {
        "status": "partial" if warnings else "ok",
        "context": {
            "trend": trend_context,
            "risk": risk_context,
        },
        "params": {
            "breakout_buffer_pct": breakout_buffer,
            "buy_zone_width_pct": buy_zone_width,
            "support_invalidation_buffer_pct": support_invalidation_buffer,
            "tp_levels_count": tp_count,
        },
        "long_breakout": {
            "trigger_price": _round(breakout_trigger),
            "retest_zone": None
            if retest_zone is None
            else {"low": _round(retest_zone["low"]), "high": _round(retest_zone["high"])},
        },
        "buy_zone": None if buy_zone is None else {"low": _round(buy_zone["low"]), "high": _round(buy_zone["high"])},
        "invalidation": {
            "trigger_price": _round(invalidation),
            "rule": "loss_of_nearest_support",
        },
        "tp_zones": tp_zones,
        "next_levels": {
            "supports": [_round(x) for x in reversed(next_supports[:3])],
            "resistances": [_round(x) for x in next_resistances[:3]],
        },
        "warnings": warnings,
    }
