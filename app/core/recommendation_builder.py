from __future__ import annotations

from dataclasses import dataclass
from typing import Any


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

        if not basis.get("eligible_for_recommendation", False):
            return RecommendationResult(status="skip", reason="not_eligible")

        candidate_strategy = basis.get("candidate_strategy") or "grid"
        confidence = float(basis.get("confidence_score", 0.0))
        return RecommendationResult(
            status="ok",
            strategy_type=str(candidate_strategy),
            params={"source": "analysis_report"},
            confidence=confidence,
        )
