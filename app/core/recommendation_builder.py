from __future__ import annotations

from dataclasses import dataclass
from typing import Any

ALLOWED_STRUCTURE_EVENTS = {"bos", "choch"}
EVENT_WINDOW = 5
MIN_CONFIDENCE_TO_ACT = 0.6


@dataclass(slots=True)
class RecommendationResult:
    status: str
    reason: str | None = None
    strategy_type: str | None = None
    params: dict[str, Any] | None = None
    confidence: float | None = None


class RecommendationBuilder:
    """Build trading recommendation from analysis payload."""

    def build(self, report_payload: dict[str, Any] | None) -> RecommendationResult:
        if not report_payload:
            return RecommendationResult(status="skip", reason="no_analysis_report")

        basis = report_payload.get("recommendation_basis")
        if not isinstance(basis, dict):
            return RecommendationResult(status="skip", reason="no_recommendation_basis")

        direction = self._read_direction(report_payload, basis)
        if direction is None:
            return RecommendationResult(status="skip", reason="no_direction")

        if not self._direction_confirmed(report_payload, basis, direction):
            return RecommendationResult(status="skip", reason="direction_not_confirmed")

        if not basis.get("eligible_for_recommendation", False):
            return RecommendationResult(status="skip", reason="not_eligible")

        candidate_strategy = str(basis.get("candidate_strategy") or "grid")
        confidence = float(basis.get("confidence_score", 0.0))

        actionable_strategies = {"grid", "range", "trend", "trend_follow"}
        if candidate_strategy in actionable_strategies and confidence < MIN_CONFIDENCE_TO_ACT:
            return RecommendationResult(
                status="skip",
                reason="low_confidence",
                strategy_type="skip",
                confidence=confidence,
            )

        suggested_params = basis.get("suggested_bot_params")
        params: dict[str, Any] = {"source": "analysis_report"}
        if isinstance(suggested_params, dict):
            params.update(suggested_params)
        return RecommendationResult(
            status="ok",
            strategy_type=candidate_strategy,
            params=params,
            confidence=confidence,
        )

    def _read_direction(self, report_payload: dict[str, Any], basis: dict[str, Any]) -> str | None:
        reference_interval = ((basis.get("suggested_bot_params") or {}).get("reference_interval")) or (
            (report_payload.get("nearest_levels") or {}).get("primary_interval")
        )
        market_structure = report_payload.get("market_structure")
        if not isinstance(market_structure, dict) or reference_interval is None:
            return None
        trend = (market_structure.get(str(reference_interval)) or {}).get("trend_regime")
        return trend if trend in {"trend_up", "trend_down"} else None

    def _direction_confirmed(self, report_payload: dict[str, Any], basis: dict[str, Any], direction: str) -> bool:
        expected_event_side = "bullish" if direction == "trend_up" else "bearish"
        expected_level_key = "strongest_support" if direction == "trend_up" else "strongest_resistance"

        reference_interval = ((basis.get("suggested_bot_params") or {}).get("reference_interval")) or (
            (report_payload.get("nearest_levels") or {}).get("primary_interval")
        )
        levels_summary = (report_payload.get("levels_summary") or {}).get(str(reference_interval), {})
        recent_events = levels_summary.get("recent_structure_events") or []

        valid_events = [
            e
            for e in recent_events[-EVENT_WINDOW:]
            if isinstance(e, dict)
            and str(e.get("type", "")).lower() in ALLOWED_STRUCTURE_EVENTS
            and str(e.get("side", "")).lower() == expected_event_side
        ]
        has_structure_confirmation = len(valid_events) > 0

        strong_level = levels_summary.get(expected_level_key)
        has_level_confirmation = isinstance(strong_level, dict) and (strong_level.get("strength_score") is not None)
        return has_structure_confirmation and has_level_confirmation
